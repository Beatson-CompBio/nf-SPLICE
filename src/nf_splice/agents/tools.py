"""Deterministic, typed nf-splice tools exposed to agents.

Every tool calls the same services as the CLI and TUI. Read-only tools never
write; proposing tools validate a change and store it as a pending proposal
without touching any file; only a human approval (outside the model) turns a
proposal into an attributed draft edit.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from nf_splice.agents.policy import AgentPolicy, PolicyViolation
from nf_splice.domain import OutputCandidate, ReviewedOutput
from nf_splice.domain.audit import Actor, ActorKind, ApprovalStatus, ChangeOrigin
from nf_splice.drafts import PatchOp
from nf_splice.inspectors.containers import classify_reference
from nf_splice.layers import ChangeContext, LayerError
from nf_splice.layers.base import edit_draft, layer_spec, read_layer
from nf_splice.layers.bundle import set_identity_fields
from nf_splice.layers.components import pending_components
from nf_splice.layers.inputs import set_access
from nf_splice.layers.outputs import (
    accept_output,
    candidate_evidence,
    pending_candidates,
    reject_output,
)
from nf_splice.layers.provenance import analyse_ro_crate
from nf_splice.services.audit import make_event, record_private, redact
from nf_splice.services.lifecycle import plan_promotion, validate_bundle
from nf_splice.services.workspace import inspect_layer, workspace_status
from nf_splice.vocabulary import GLOSSARY

_LAYERS = [
    "bundle",
    "inputs",
    "outputs",
    "components",
    "execution-profiles",
    "provenance",
]
_MAX_TEXT = 6000


class ProposalStatus(str, Enum):
    """Lifecycle of an agent proposal."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    APPLIED = "applied"
    FAILED = "failed"


@dataclass(slots=True)
class Proposal:
    """A validated, not-yet-applied change suggested by an agent."""

    id: str
    kind: str
    layer: str
    title: str
    rationale: str
    payload: dict[str, Any]
    diff: str
    provider: str
    status: ProposalStatus = ProposalStatus.PENDING
    approved_by: str | None = None
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "layer": self.layer,
            "title": self.title,
            "rationale": self.rationale,
            "payload": self.payload,
            "diff": self.diff,
            "provider": self.provider,
            "status": self.status.value,
            "approved_by": self.approved_by,
            "note": self.note,
        }

    @classmethod
    def from_json(cls, data: Mapping[str, Any]) -> Proposal:
        return cls(
            id=str(data["id"]),
            kind=str(data["kind"]),
            layer=str(data["layer"]),
            title=str(data["title"]),
            rationale=str(data["rationale"]),
            payload=dict(data["payload"]),
            diff=str(data["diff"]),
            provider=str(data["provider"]),
            status=ProposalStatus(data["status"]),
            approved_by=data.get("approved_by"),
            note=str(data.get("note", "")),
        )


@dataclass(slots=True)
class ProposalBook:
    """Pending proposals, optionally persisted outside the repository."""

    path: Path | None = None
    proposals: dict[str, Proposal] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | None) -> ProposalBook:
        book = cls(path=path)
        if path is not None and path.is_file():
            for item in json.loads(path.read_text(encoding="utf-8")):
                proposal = Proposal.from_json(item)
                book.proposals[proposal.id] = proposal
        return book

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.write_text(
            json.dumps([item.to_json() for item in self.proposals.values()], indent=2),
            encoding="utf-8",
        )

    def add(self, proposal: Proposal) -> Proposal:
        self.proposals.setdefault(proposal.id, proposal)
        self.save()
        return self.proposals[proposal.id]

    def get(self, identifier: str) -> Proposal:
        if identifier not in self.proposals:
            raise LayerError(f"unknown proposal {identifier!r}")
        return self.proposals[identifier]


def _proposal_id(kind: str, layer: str, payload: Mapping[str, Any]) -> str:
    digest = hashlib.sha256(
        json.dumps([kind, layer, payload], sort_keys=True, default=str).encode()
    ).hexdigest()
    return f"proposal-{digest[:12]}"


def _clip(value: Any) -> Any:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= _MAX_TEXT:
        return json.loads(redact(text))
    return {"truncated": True, "preview": redact(text[:_MAX_TEXT])}


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """One structured tool: name, description, JSON input schema, handler."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Callable[[Mapping[str, Any]], dict[str, Any]]


class AgentToolbox:
    """The only interface between a model and nf-splice."""

    def __init__(
        self,
        repository: str | Path,
        policy: AgentPolicy,
        book: ProposalBook | None = None,
        *,
        provider: str = "agent",
    ) -> None:
        self.repository = Path(repository).resolve()
        self.policy = policy
        self.book = book or ProposalBook()
        self.provider = provider
        self.log: list[dict[str, Any]] = []
        layer = {"type": "string", "enum": _LAYERS}
        self._tools: dict[str, ToolSpec] = {
            spec.name: spec
            for spec in (
                ToolSpec(
                    "workspace_status",
                    "Layer states and warnings (read-only).",
                    _obj({}),
                    self._status,
                ),
                ToolSpec(
                    "inspect_draft",
                    "Per-field issues of one draft (read-only).",
                    _obj({"layer": layer}, ["layer"]),
                    self._inspect,
                ),
                ToolSpec(
                    "read_draft",
                    "Parsed content of one draft (read-only, redacted).",
                    _obj({"layer": layer}, ["layer"]),
                    self._read,
                ),
                ToolSpec(
                    "list_output_candidates",
                    "Pending output candidates with evidence.",
                    _obj({}),
                    self._outputs,
                ),
                ToolSpec(
                    "list_component_candidates",
                    "Pending components and open problems.",
                    _obj({}),
                    self._components,
                ),
                ToolSpec(
                    "preview_promotion",
                    "Blockers and changed files of a publication plan.",
                    _obj({"layer": {"type": ["string", "null"]}}),
                    self._preview,
                ),
                ToolSpec(
                    "validate_bundle",
                    "Validate the published bundle (read-only).",
                    _obj({}),
                    self._validate,
                ),
                ToolSpec(
                    "classify_container",
                    "Classify a container reference offline.",
                    _obj({"reference": {"type": "string"}}, ["reference"]),
                    self._classify,
                ),
                ToolSpec(
                    "analyse_ro_crate",
                    "RO-Crate structural and identity findings.",
                    _obj({}),
                    self._crate,
                ),
                ToolSpec(
                    "explain_term",
                    "Precise SPLICE meaning of a vocabulary term.",
                    _obj({"term": {"type": "string"}}, ["term"]),
                    self._explain,
                ),
                ToolSpec(
                    "propose_patch",
                    "Propose JSON-pointer patch operations (never writes).",
                    _obj(
                        {
                            "layer": layer,
                            "operations": {
                                "type": "array",
                                "items": {"type": "object"},
                            },
                            "rationale": {"type": "string"},
                        },
                        ["layer", "operations", "rationale"],
                    ),
                    self._propose_patch,
                ),
                ToolSpec(
                    "propose_output_review",
                    "Propose accepting/rejecting an output candidate.",
                    _obj(
                        {
                            "candidate_id": {"type": "string"},
                            "action": {"type": "string", "enum": ["accept", "reject"]},
                            "output": {"type": "object"},
                            "reason": {"type": "string"},
                            "rationale": {"type": "string"},
                        },
                        ["candidate_id", "action", "rationale"],
                    ),
                    self._propose_output,
                ),
                ToolSpec(
                    "propose_access",
                    "Propose parameter editors; needs human approval.",
                    _obj(
                        {
                            "parameters": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "editable_by": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "enum": ["user", "platform", "agent"],
                                },
                            },
                            "rationale": {"type": "string"},
                        },
                        ["parameters", "editable_by", "rationale"],
                    ),
                    self._propose_access,
                ),
                ToolSpec(
                    "propose_identity",
                    "Propose identity values (never writes).",
                    _obj(
                        {
                            "changes": {"type": "object"},
                            "rationale": {"type": "string"},
                        },
                        ["changes", "rationale"],
                    ),
                    self._propose_identity,
                ),
                ToolSpec(
                    "apply_approved_proposal",
                    "Apply a proposal a human has already approved.",
                    _obj({"proposal_id": {"type": "string"}}, ["proposal_id"]),
                    self._apply,
                ),
            )
        }

    # ------------------------------------------------------------ mediation

    def schemas(self) -> list[dict[str, Any]]:
        """JSON tool schemas for the tools permitted in the current mode."""
        from nf_splice.agents.policy import MODE_TOOLS

        allowed = MODE_TOOLS[self.policy.mode]
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "input_schema": spec.input_schema,
            }
            for spec in self._tools.values()
            if spec.name in allowed
        ]

    def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        """Run one tool through policy; failures are returned, never raised."""
        entry: dict[str, Any] = {
            "provider": self.provider,
            "tool": name,
            "arguments": _clip(dict(arguments)),
        }
        try:
            if name not in self._tools:
                raise PolicyViolation(f"unknown tool {name!r}")
            self.policy.check(name, arguments)
            result = self._tools[name].handler(arguments)
        except PolicyViolation as error:
            result = {"success": False, "denied": True, "issues": [str(error)]}
            self._audit_denial(name, str(error))
        except (LayerError, ValidationError, ValueError, KeyError, TypeError) as error:
            result = {"success": False, "issues": [redact(str(error))]}
        entry["outcome"] = (
            "denied"
            if result.get("denied")
            else ("ok" if result.get("success") else "failed")
        )
        if result.get("proposal_id"):
            entry["proposal_id"] = result["proposal_id"]
        self.log.append(entry)
        clipped: dict[str, Any] = _clip(result)
        return clipped

    def _audit_denial(self, tool: str, reason: str) -> None:
        event = make_event(
            layer="agent",
            action=f"denied:{tool}",
            origin=ChangeOrigin.AGENT_SUGGESTION,
            approval=ApprovalStatus.REJECTED,
            actor=Actor(label=self.provider, kind=ActorKind.AGENT),
        )
        record_private(self.repository, event)
        del reason

    def _agent_context(self, approved_by: Actor | None = None) -> ChangeContext:
        return ChangeContext(
            actor=Actor(label=self.provider, kind=ActorKind.AGENT),
            origin=ChangeOrigin.AGENT_SUGGESTION,
            approved=approved_by is not None,
            approved_by=approved_by,
        )

    # ------------------------------------------------------------ read-only

    def _status(self, _arguments: Mapping[str, Any]) -> dict[str, Any]:
        status = workspace_status(self.repository).to_json()
        status.pop("repository", None)
        return {"success": True, "data": status}

    def _inspect(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "success": True,
            "data": inspect_layer(self.repository, str(arguments["layer"])),
        }

    def _read(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        state = read_layer(self.repository, layer_spec(str(arguments["layer"])).name)
        if state.draft is None:
            return {
                "success": False,
                "issues": [str(state.error or "draft is missing")],
            }
        return {"success": True, "data": state.draft.data}

    def _outputs(self, _arguments: Mapping[str, Any]) -> dict[str, Any]:
        candidates = [
            item.model_dump(mode="json")
            | {
                "evidence": [
                    entry["provenance"]["location"]
                    for entry in candidate_evidence(self.repository, item.id)
                ]
            }
            for item in pending_candidates(self.repository)
        ]
        return {
            "success": True,
            "candidate_ids": [item["id"] for item in candidates],
            "data": candidates,
        }

    def _components(self, _arguments: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "success": True,
            "data": [
                {
                    "id": item.id,
                    "versions": list(item.versions),
                    "proposed_sources": dict(item.proposed_sources),
                    "problems": list(item.problems),
                }
                for item in pending_components(self.repository)
            ],
        }

    def _preview(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        plan = plan_promotion(self.repository, arguments.get("layer"))
        document = plan.to_json()
        for change in document["changes"]:
            change["diff"] = change["diff"][:1500]
        return {"success": True, "data": document}

    def _validate(self, _arguments: Mapping[str, Any]) -> dict[str, Any]:
        report = validate_bundle(self.repository)
        return {
            "success": report.valid,
            "issues": [item.to_json() for item in report.issues],
        }

    def _classify(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "success": True,
            "data": classify_reference(str(arguments["reference"])).value,
        }

    def _crate(self, _arguments: Mapping[str, Any]) -> dict[str, Any]:
        analysis = analyse_ro_crate(self.repository)
        return {"success": True, "data": [item.to_json() for item in analysis.findings]}

    def _explain(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        term = str(arguments["term"]).lower()
        if term not in GLOSSARY:
            return {
                "success": False,
                "issues": [f"unknown term; known: {sorted(GLOSSARY)}"],
            }
        return {"success": True, "data": GLOSSARY[term]}

    # ------------------------------------------------------------ proposals

    def _record(
        self,
        kind: str,
        layer: str,
        title: str,
        rationale: str,
        payload: dict[str, Any],
        diff: str,
    ) -> dict[str, Any]:
        proposal = self.book.add(
            Proposal(
                id=_proposal_id(kind, layer, payload),
                kind=kind,
                layer=layer,
                title=title,
                rationale=rationale,
                payload=payload,
                diff=diff,
                provider=self.provider,
            )
        )
        return {
            "success": True,
            "requires_approval": True,
            "proposal_id": proposal.id,
            "diff": diff[:3000],
        }

    def _propose_patch(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        layer = layer_spec(str(arguments["layer"])).name
        operations = [PatchOp.from_json(item) for item in arguments["operations"]]
        planned = edit_draft(
            self.repository, layer, operations, self._agent_context(), write=False
        )
        payload = {"operations": [item.to_json() for item in operations]}
        return self._record(
            "patch",
            layer,
            f"Edit {layer} draft",
            str(arguments["rationale"]),
            payload,
            planned.diff,
        )

    def _propose_output(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        candidate_id = str(arguments["candidate_id"])
        known: dict[str, OutputCandidate] = {
            item.id: item for item in pending_candidates(self.repository)
        }
        if candidate_id not in known:
            raise LayerError(
                f"unknown or already reviewed output candidate {candidate_id!r}"
            )
        if arguments["action"] == "accept":
            output = ReviewedOutput.model_validate(arguments.get("output") or {})
            payload: dict[str, Any] = {
                "candidate_id": candidate_id,
                "action": "accept",
                "output": output.model_dump(mode="json"),
            }
            diff = f"accept {candidate_id} as output {output.key!r}"
        else:
            reason = str(arguments.get("reason") or "").strip()
            if not reason:
                raise LayerError("a rejection proposal needs a reason")
            payload = {
                "candidate_id": candidate_id,
                "action": "reject",
                "reason": reason,
            }
            diff = f"reject {candidate_id}: {reason}"
        return self._record(
            "output_review",
            "outputs",
            f"{payload['action']} {known[candidate_id].suggested_key}",
            str(arguments["rationale"]),
            payload,
            diff,
        )

    def _propose_access(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        names = [str(item) for item in arguments["parameters"]]
        principals = [str(item) for item in arguments["editable_by"]]
        planned = set_access(
            self.repository, names, principals, self._agent_context(), write=False
        )
        payload = {"parameters": names, "editable_by": principals}
        return self._record(
            "access",
            "inputs",
            f"Access for {', '.join(names)}",
            str(arguments["rationale"]),
            payload,
            planned.diff,
        )

    def _propose_identity(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        changes = dict(arguments["changes"])
        planned = set_identity_fields(
            self.repository, changes, self._agent_context(), write=False
        )
        return self._record(
            "identity",
            "bundle",
            "Identity values",
            str(arguments["rationale"]),
            {"changes": changes},
            planned.diff,
        )

    # ------------------------------------------------------------ application

    def _apply(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        proposal = self.book.get(str(arguments["proposal_id"]))
        if (
            proposal.status is not ProposalStatus.APPROVED
            or proposal.approved_by is None
        ):
            raise PolicyViolation(f"proposal {proposal.id} is not approved by a human")
        apply_proposal(
            self.repository,
            proposal,
            Actor(label=proposal.approved_by),
            provider=self.provider,
        )
        self.book.save()
        return {
            "success": proposal.status.value == ProposalStatus.APPLIED.value,
            "proposal_id": proposal.id,
            "issues": [proposal.note] if proposal.note else [],
        }


def apply_proposal(
    repository: Path, proposal: Proposal, approver: Actor, *, provider: str
) -> None:
    """Apply one proposal with agent origin and a separate human approver."""
    context = ChangeContext(
        actor=Actor(label=provider, kind=ActorKind.AGENT),
        origin=ChangeOrigin.AGENT_SUGGESTION,
        approved=True,
        approved_by=approver,
    )
    try:
        payload = proposal.payload
        if proposal.kind == "patch":
            edit_draft(
                repository,
                proposal.layer,
                [PatchOp.from_json(item) for item in payload["operations"]],
                context,
                action="agent_patch",
            )
        elif proposal.kind == "output_review" and payload["action"] == "accept":
            accept_output(
                repository, payload["candidate_id"], payload["output"], context
            )
        elif proposal.kind == "output_review":
            reject_output(
                repository, payload["candidate_id"], payload["reason"], context
            )
        elif proposal.kind == "access":
            set_access(
                repository, payload["parameters"], payload["editable_by"], context
            )
        elif proposal.kind == "identity":
            set_identity_fields(repository, payload["changes"], context)
        else:
            raise LayerError(f"unknown proposal kind {proposal.kind!r}")
    except (LayerError, ValueError) as error:
        proposal.status = ProposalStatus.FAILED
        proposal.note = redact(str(error))
        return
    proposal.status = ProposalStatus.APPLIED
    proposal.approved_by = approver.label


def _obj(
    properties: dict[str, Any], required: list[str] | None = None
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }
