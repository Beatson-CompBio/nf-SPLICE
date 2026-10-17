"""Mediation of every tool call a provider makes during one turn.

The toolbox decides, for each call: is the tool offered in this turn, are the
arguments valid, is the permission granted, is the budget left, and does the
call observe, stage (assisted planning) or execute (approved or autonomous
work)? Every call and its outcome is logged; failures are returned to the
model as structured results, never raised.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]
from pydantic import ValidationError

from nf_splice.agents.operations import (
    CONTROL_SCHEMAS,
    OPERATIONS,
    Operation,
    OperationContext,
    describe,
)
from nf_splice.agents.permissions import ExecutionPolicy, PolicyViolation
from nf_splice.agents.review_scope import (
    Coverage,
    coverage,
    suggested_calls,
    unsupported_citations,
)
from nf_splice.agents.sandbox import Sandbox
from nf_splice.agents.state import PlannedOperation, Usage, now
from nf_splice.layers import ChangeContext, LayerError
from nf_splice.services.audit import redact
from nf_splice.services.containers import ContainerServiceError
from nf_splice.services.lifecycle import LifecycleError

_MAX_RESULT = 12_000


class ToolMode(str, Enum):
    """What draft and build operations do in this turn."""

    OBSERVE = "observe"
    STAGE = "stage"
    EXECUTE = "execute"


@dataclass(slots=True)
class TurnOutcome:
    """What a provider turn produced, as recorded by the toolbox."""

    staged: list[PlannedOperation] = field(default_factory=list)
    proposal: dict[str, Any] | None = None
    assessment: dict[str, Any] | None = None
    blockers: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    executed: list[str] = field(default_factory=list)
    denied: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    budget_exhausted: bool = False
    #: What the model actually inspected, recorded from its tool calls.
    inspected: list[str] = field(default_factory=list)
    review: dict[str, Any] | None = None
    notices: list[str] = field(default_factory=list)


#: Read tools that look at the pipeline itself (not only at a draft). A
#: review must have used at least one of them.
SOURCE_INSPECTIONS = frozenset(
    {
        "read_source",
        "search_source",
        "analyse_routes",
        "parameter_usage",
        "component_inventory",
        "analyse_execution",
        "analyse_ro_crate",
        "validate_ro_crate",
        "assess_assays",
        "list_example_outputs",
        "reconcile_example_outputs",
        "read_config",
    }
)


def inspection(
    name: str, arguments: Mapping[str, Any], result: Mapping[str, Any]
) -> str:
    """A factual, compact record of one read call and what it returned."""
    data = result.get("data") if isinstance(result.get("data"), Mapping) else {}
    if name == "read_source":
        lines = data.get("lines") if isinstance(data, Mapping) else None
        span = (
            f"{lines[0]}-{lines[1]}"
            if isinstance(lines, list) and len(lines) == 2
            else "?"
        )
        return f"read_source {arguments.get('path')}:{span}"
    if name == "search_source":
        matches = data.get("matches") if isinstance(data, Mapping) else None
        count = len(matches) if isinstance(matches, list) else 0
        return (
            f"search_source /{arguments.get('pattern')}/ in "
            f"{arguments.get('glob') or '*'} ({count} match(es))"
        )
    detail = ", ".join(
        f"{key}={arguments[key]}"
        for key in ("layer", "name", "config", "example", "path")
        if arguments.get(key) is not None
    )
    return f"{name}({detail})" if detail else name


def _clip(value: Any) -> Any:
    text = json.dumps(value, ensure_ascii=False, default=str)
    if len(text) <= _MAX_RESULT:
        return json.loads(redact(text))
    return {"truncated": True, "preview": redact(text[:_MAX_RESULT])}


class SessionToolbox:
    """The only interface between a provider and nf-splice in a turn."""

    def __init__(
        self,
        *,
        root: Path,
        policy: ExecutionPolicy,
        mode: ToolMode,
        operations: set[str],
        controls: set[str],
        change: ChangeContext,
        usage: Usage,
        stage_layer: str | None = None,
        examples: list[Path] | None = None,
        session_directory: Path | None = None,
        sandbox: Sandbox | None = None,
        log: Callable[[dict[str, Any]], None] | None = None,
        prior_investigation: Sequence[str] = (),
        stage: str | None = None,
        stage_changed: bool = False,
    ) -> None:
        self.root = root
        self.policy = policy
        self.mode = mode
        self.operations = {name for name in operations if name in OPERATIONS}
        self.controls = {name for name in controls if name in CONTROL_SCHEMAS}
        self.change = change
        self.usage = usage
        self.stage_layer = stage_layer
        self.examples = examples or []
        self.session_directory = session_directory
        self.sandbox = sandbox
        self._log = log
        self.prior_investigation = list(prior_investigation)
        self.stage = stage
        self.stage_changed = stage_changed
        self.outcome = TurnOutcome()

    def schemas(self) -> list[dict[str, Any]]:
        offered = [OPERATIONS[name].schema() for name in sorted(self.operations)]
        offered.extend(CONTROL_SCHEMAS[name] for name in sorted(self.controls))
        return offered

    # -------------------------------------------------------- mediation

    def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        arguments = dict(arguments or {})
        record: dict[str, Any] = {
            "at": now(),
            "tool": name,
            "mode": self.mode.value,
            "arguments": _clip(arguments),
        }
        try:
            result = self._dispatch(name, arguments)
        except PolicyViolation as error:
            self.outcome.denied.append(f"{name}: {error}")
            result = {"success": False, "denied": True, "issues": [redact(str(error))]}
        except (
            LayerError,
            LifecycleError,
            ContainerServiceError,
            ValidationError,
            ValueError,
            KeyError,
            TypeError,
            OSError,
        ) as error:
            self.outcome.failures.append(f"{name}: {redact(str(error))}")
            result = {"success": False, "issues": [redact(str(error))]}
        record["outcome"] = (
            "denied"
            if result.get("denied")
            else "staged"
            if result.get("staged")
            else "ok"
            if result.get("success")
            else "failed"
        )
        record["result_sha256"] = hashlib.sha256(
            json.dumps(result, sort_keys=True, default=str).encode()
        ).hexdigest()
        if self._log is not None:
            self._log(record)
        clipped: dict[str, Any] = _clip(result)
        return clipped

    def _dispatch(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self.usage.tool_calls += 1
        if self.usage.tool_calls > self.policy.budgets.max_tool_calls:
            self.outcome.budget_exhausted = True
            raise PolicyViolation(
                "the session's tool-call budget is exhausted; stop and report"
            )
        if name in CONTROL_SCHEMAS:
            if name not in self.controls:
                raise PolicyViolation(f"{name} is not available in this turn")
            self._validate(CONTROL_SCHEMAS[name]["input_schema"], arguments)
            return self._control(name, arguments)
        operation = OPERATIONS.get(name)
        if operation is None:
            raise PolicyViolation(f"unknown tool {name!r}")
        if name not in self.operations:
            raise PolicyViolation(f"{name} is not available in this turn")
        self._validate(operation.input_schema, arguments)
        if (
            operation.layer_argument
            and self.stage_layer is not None
            and arguments.get("layer") != self.stage_layer
        ):
            raise PolicyViolation(
                f"{name} may only change the {self.stage_layer} draft in this stage"
            )
        self.policy.require(operation.permission)
        if operation.kind == "read":
            if self.mode is ToolMode.STAGE and self.sandbox is not None:
                # While planning, reads see the staged changes on the preview copy.
                result = self.sandbox.run(
                    operation,
                    arguments,
                    change=self.change,
                    policy=self.policy,
                    examples=self.examples,
                )
            else:
                result = self._run(operation, arguments)
            if result.get("success"):
                entry = inspection(name, arguments, result)
                if entry not in self.outcome.inspected:
                    self.outcome.inspected.append(entry)
            return result
        if self.mode is ToolMode.OBSERVE:
            raise PolicyViolation(
                f"{name} changes files; this turn is read-only (answer, do not edit)"
            )
        if self.mode is ToolMode.STAGE:
            return self._stage(operation, arguments)
        result = self._run(operation, arguments)
        if result.get("success"):
            self.outcome.executed.append(describe(name, arguments))
        return result

    @staticmethod
    def _validate(schema: dict[str, Any], arguments: Mapping[str, Any]) -> None:
        errors = sorted(
            Draft202012Validator(schema).iter_errors(dict(arguments)),
            key=lambda item: list(item.path),
        )
        if errors:
            raise ValueError(
                "invalid arguments: "
                + "; ".join(
                    "/".join(str(part) for part in item.path) + f": {item.message}"
                    for item in errors[:5]
                )
            )

    def _run(
        self, operation: Operation, arguments: Mapping[str, Any]
    ) -> dict[str, Any]:
        context = OperationContext(
            root=self.root,
            change=self.change,
            policy=self.policy,
            session_directory=self.session_directory,
            examples=self.examples,
        )
        return operation.handler(context, arguments)

    def _stage(self, operation: Operation, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.sandbox is None:
            raise PolicyViolation("staging is not available in this turn")
        before = self.sandbox.diff()
        result = self.sandbox.run(
            operation,
            arguments,
            change=self.change,
            policy=self.policy,
            examples=self.examples,
        )
        if not result.get("success"):
            return result
        self.outcome.staged.append(
            PlannedOperation(
                tool=operation.name,
                arguments=json.loads(json.dumps(arguments, default=str)),
                description=describe(operation.name, arguments),
            )
        )
        after = self.sandbox.diff()
        return {
            "success": True,
            "staged": True,
            "note": "staged for the user's approval; nothing in the repository changed",
            "result": result,
            "preview_diff": after[len(before) :][:4000]
            if after.startswith(before)
            else after[:4000],
        }

    def trace(self) -> list[str]:
        """Everything inspected in this stage, earlier turns included."""
        return [*self.prior_investigation, *self.outcome.inspected]

    def coverage(self) -> Coverage:
        if self.stage is None:
            return Coverage("")
        return coverage(
            self.root, self.stage, self.trace(), examples=bool(self.examples)
        )

    def _require_evidence(self, arguments: Mapping[str, Any], *, review: bool) -> None:
        """Refuse to finish a stage the evidence does not support (ADR-0063)."""
        if self.stage is None:
            return
        trace = self.trace()
        if not any(
            item.split(" ", 1)[0].split("(", 1)[0] in SOURCE_INSPECTIONS
            for item in trace
        ):
            raise PolicyViolation(
                "a review needs evidence: inspect the pipeline itself first "
                "(call review_scope to see what this stage needs)"
            )
        report = self.coverage()
        if report.required_gaps:
            raise PolicyViolation(
                "required evidence for this stage is not inspected yet: "
                + "; ".join(line for line in report.gap_lines() if "(required)" in line)
                + ". Inspect it (review_scope lists the calls), or record a "
                "blocker if it cannot be inspected."
            )
        evidence = [str(item) for item in arguments.get("evidence") or []]
        supported, unsupported = unsupported_citations(evidence, trace)
        if unsupported:
            raise PolicyViolation(
                "the evidence cites files you have not read in this stage: "
                + ", ".join(unsupported[:10])
                + "; read them first, or cite what you did inspect"
            )
        if not supported:
            raise PolicyViolation(
                "cite the evidence for your conclusions: files you read "
                "(path or path:line) or the analyses you ran"
            )
        if not review:
            return
        assessment = arguments.get("draft_assessment") or {}
        if self.stage == "outputs":
            self._require_route_decisions(arguments)
        changed = self.stage_changed or bool(
            self.outcome.staged or self.outcome.executed
        )
        if not changed and not assessment.get("confirmed"):
            raise PolicyViolation(
                "the draft is unchanged: list under draft_assessment.confirmed what "
                "you verified against the evidence, or change the draft"
            )

    def _stage_root(self) -> Path:
        """Where the stage's drafts are: the preview copy while planning."""
        if self.mode is ToolMode.STAGE and self.sandbox is not None:
            return self.sandbox.repository
        return self.root

    def _require_route_decisions(self, arguments: Mapping[str, Any]) -> None:
        """Every uncovered alternative route must be addressed by the review."""
        from nf_splice.services.lifecycle import validate_layer

        issues = validate_layer(self._stage_root(), "outputs").issues
        open_routes = sorted(
            {
                item.message.split(" ", 1)[0]
                for item in issues
                if item.code == "conditional_route_not_covered"
            }
        )
        assessment = arguments.get("draft_assessment") or {}
        text = " ".join(
            str(value)
            for key in ("findings", "uncertainties")
            for value in arguments.get(key) or []
        ) + " ".join(
            str(value) for values in assessment.values() for value in values or []
        )
        unaddressed = [name for name in open_routes if name not in text]
        if unaddressed:
            raise PolicyViolation(
                "these published alternative routes are neither catalogued nor "
                "excluded: " + ", ".join(unaddressed[:20]) + ". Add outputs for "
                "them, exclude them with a reason, or say in findings or "
                "uncertainties why each stays out"
            )

    def _control(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "submit_stage_proposal":
            self._require_evidence(arguments, review=False)
            self.outcome.proposal = arguments
            return {
                "success": True,
                "note": "proposal recorded; the user decides next",
                "staged_operations": len(self.outcome.staged),
            }
        if name == "assess_objection":
            self.outcome.assessment = arguments
            return {"success": True, "note": "assessment recorded"}
        if name == "record_blocker":
            self.outcome.blockers.append(arguments)
            return {"success": True, "note": "blocker recorded"}
        if name == "review_scope":
            report = self.coverage()
            return {
                "success": True,
                "data": report.to_json(),
                "suggested_calls": suggested_calls(report, advisory=True),
            }
        if name == "complete_review":
            self._require_evidence(arguments, review=True)
            self.outcome.review = arguments
            return {
                "success": True,
                "note": "review recorded",
                "advisory_gaps": self.coverage().gap_lines(),
            }
        self.outcome.evidence.append(arguments)
        return {"success": True, "note": "evidence recorded"}
