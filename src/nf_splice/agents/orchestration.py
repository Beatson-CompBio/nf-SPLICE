"""Inspect -> propose -> validate -> human review, over any provider."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nf_splice.agents.policy import AgentPolicy
from nf_splice.agents.protocol import (
    AgentContext,
    AgentEvent,
    AgentMode,
    AgentProvider,
    EventKind,
    SessionLimits,
)
from nf_splice.agents.tools import (
    AgentToolbox,
    Proposal,
    ProposalBook,
    ProposalStatus,
    apply_proposal,
)
from nf_splice.domain.audit import Actor, ActorKind
from nf_splice.layers import LayerError
from nf_splice.services.workspace import workspace_status
from nf_splice.vocabulary import GLOSSARY


class ConsentRequired(PermissionError):
    """Raised before any repository context is sent to a remote model."""


SYSTEM_RULES = """You help a developer author a SPLICE workflow bundle with nf-splice.
Rules:
- You can only use the nf_splice tools. You cannot run shell commands, read
  arbitrary files or access the network.
- Read-only tools inspect drafts; propose_* tools validate a change and store
  a pending proposal. Nothing you propose changes any file until a human
  approves it. Never claim that a change was approved or applied.
- Explain evidence and uncertainty; scientific meaning is for the human to
  decide. Never invent identifiers, checksums, URLs or people.
- Vocabulary: {vocabulary}
"""


def system_prompt(repository: Path) -> str:
    """Bounded context: rules plus layer states only (no file contents)."""
    status = workspace_status(repository)
    layers = ", ".join(f"{item.layer}={item.state.value}" for item in status.artifacts)
    vocabulary = "; ".join(f"{key}: {value}" for key, value in GLOSSARY.items())
    return SYSTEM_RULES.format(vocabulary=vocabulary) + f"Current layers: {layers}.\n"


@dataclass(slots=True)
class AgentRunResult:
    """Everything that happened in one agent run (the visible action log)."""

    events: list[AgentEvent] = field(default_factory=list)
    log: list[dict[str, Any]] = field(default_factory=list)
    proposals: list[Proposal] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "events": [
                {"kind": item.kind.value, "text": item.text, "data": dict(item.data)}
                for item in self.events
            ],
            "log": self.log,
            "proposals": [item.to_json() for item in self.proposals],
        }


async def run_agent(
    repository: str | Path,
    provider: AgentProvider,
    prompt: str,
    *,
    mode: AgentMode,
    book: ProposalBook,
    allow_remote: bool = False,
    limits: SessionLimits | None = None,
) -> AgentRunResult:
    """Run one bounded agent session; proposals are never applied here."""
    root = Path(repository).resolve()
    if mode is AgentMode.OFF:
        raise PermissionError("agent mode is off")
    capabilities = provider.capabilities
    if capabilities.remote and not allow_remote:
        raise ConsentRequired(
            f"{capabilities.name} sends bounded repository context to a remote "
            "model; pass explicit consent (--allow-remote-model)"
        )
    before = set(book.proposals)
    toolbox = AgentToolbox(
        root, AgentPolicy(repository=root, mode=mode), book, provider=capabilities.name
    )
    selected = limits or SessionLimits()
    session = provider.start(
        AgentContext(
            repository=root,
            mode=mode,
            tools=toolbox,
            system_prompt=system_prompt(root),
            limits=selected,
        )
    )
    result = AgentRunResult()

    async def consume() -> None:
        async for event in session.run(prompt):
            result.events.append(event)

    try:
        await asyncio.wait_for(consume(), timeout=selected.timeout_seconds)
    except TimeoutError:
        await session.cancel()
        result.events.append(AgentEvent(EventKind.ERROR, "agent session timed out"))
    result.log = list(toolbox.log)
    result.proposals = [
        book.proposals[item] for item in book.proposals if item not in before
    ]
    return result


def approve(
    repository: str | Path,
    book: ProposalBook,
    proposal_id: str,
    approver: Actor,
    *,
    apply: bool = True,
) -> Proposal:
    """Human approval (never callable by a model); optionally apply now."""
    if approver.kind is not ActorKind.HUMAN:
        raise PermissionError("only a human actor can approve agent proposals")
    proposal = book.get(proposal_id)
    if proposal.status not in {ProposalStatus.PENDING, ProposalStatus.APPROVED}:
        raise LayerError(f"proposal {proposal_id} is {proposal.status.value}")
    proposal.status = ProposalStatus.APPROVED
    proposal.approved_by = approver.label
    if apply:
        apply_proposal(
            Path(repository).resolve(), proposal, approver, provider=proposal.provider
        )
    book.save()
    return proposal


def reject(book: ProposalBook, proposal_id: str, reason: str) -> Proposal:
    """Record a human rejection of an agent proposal."""
    proposal = book.get(proposal_id)
    proposal.status = ProposalStatus.REJECTED
    proposal.note = reason
    book.save()
    return proposal


def proposal_book_path(session_directory: Path, repository: Path) -> Path:
    """Non-authoritative proposal storage outside the published bundle."""
    from nf_splice.interfaces.tui.state import repository_key

    return session_directory / f"agent-{repository_key(repository)}.json"


def dumps(result: AgentRunResult) -> str:
    return json.dumps(result.to_json(), indent=2, ensure_ascii=False, default=str)
