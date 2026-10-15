"""Least-privilege policy for agent tool calls (fail closed)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from nf_splice.agents.protocol import AgentMode

#: Tools usable in each mode. Write-capable tools never apply changes; the
#: only applying tool requires an explicit human-granted proposal approval.
_READ_ONLY = frozenset(
    {
        "workspace_status",
        "inspect_draft",
        "read_draft",
        "list_output_candidates",
        "list_component_candidates",
        "preview_promotion",
        "validate_bundle",
        "classify_container",
        "analyse_ro_crate",
        "explain_term",
    }
)
_PROPOSING = frozenset(
    {"propose_patch", "propose_output_review", "propose_access", "propose_identity"}
)
_APPLYING = frozenset({"apply_approved_proposal"})
MODE_TOOLS: dict[AgentMode, frozenset[str]] = {
    AgentMode.OFF: frozenset(),
    AgentMode.ASK: _READ_ONLY,
    AgentMode.SUGGEST: _READ_ONLY | _PROPOSING,
    AgentMode.DRAFT: _READ_ONLY | _PROPOSING,
    AgentMode.APPLY: _READ_ONLY | _PROPOSING | _APPLYING,
}
#: Built-in tools of any provider that must never be available.
FORBIDDEN_PROVIDER_TOOLS = (
    "Bash",
    "BashOutput",
    "KillShell",
    "Read",
    "Write",
    "Edit",
    "MultiEdit",
    "NotebookEdit",
    "Glob",
    "Grep",
    "LS",
    "WebFetch",
    "WebSearch",
    "Task",
    "TodoWrite",
)


class PolicyViolation(PermissionError):
    """Raised (and audited) when an agent requests a forbidden action."""


@dataclass(slots=True)
class AgentPolicy:
    """Mode, repository boundary and human-granted approvals."""

    repository: Path
    mode: AgentMode = AgentMode.OFF
    allow_network: bool = False
    approved_proposals: set[str] = field(default_factory=set)

    def check(self, tool: str, arguments: Mapping[str, Any]) -> None:
        """Raise unless ``tool`` is allowed with ``arguments``."""
        if tool not in MODE_TOOLS[self.mode]:
            raise PolicyViolation(
                f"tool {tool!r} is not permitted in agent mode {self.mode.value!r}"
            )
        for key, value in arguments.items():
            if key in {"path", "file", "directory"} and isinstance(value, str):
                self.check_path(value)
        if tool == "apply_approved_proposal":
            identifier = str(arguments.get("proposal_id", ""))
            if identifier not in self.approved_proposals:
                raise PolicyViolation(
                    f"proposal {identifier!r} has no human approval; agents cannot "
                    "approve their own proposals"
                )

    def check_path(self, value: str) -> None:
        """Reject paths outside the authorised repository."""
        pure = PurePosixPath(value)
        if pure.is_absolute() or ".." in pure.parts:
            raise PolicyViolation(
                f"path {value!r} is outside the authorised repository"
            )
        resolved = (self.repository / value).resolve()
        if not resolved.is_relative_to(self.repository.resolve()):
            raise PolicyViolation(f"path {value!r} escapes the repository")


def provider_tool_allowed(name: str, *, server: str = "nf_splice") -> bool:
    """Provider-side guard: only nf-splice structured tools may run."""
    return name.startswith(f"mcp__{server}__") and name not in FORBIDDEN_PROVIDER_TOOLS
