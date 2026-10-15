"""Operation-level permissions and the execution policy of a session.

Every agent tool declares the one permission it needs. A session's policy
lists the permissions the user granted, the budgets that bound the run, and
the example-output roots the agent may read. Repository content can never
widen a policy: there is no tool that changes it.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict, Field


class Permission(str, Enum):
    """What an operation may affect."""

    READ = "read"
    DRAFT_EDIT = "draft_edit"
    BUILD = "build"
    OVERWRITE = "overwrite"
    EXTERNAL_TOOLS = "external_tools"
    RUN_NEXTFLOW = "run_nextflow"
    NETWORK = "network"
    INSTALL = "install"
    PUBLISH_EXTERNAL = "publish_external"
    CREDENTIALS = "credentials"
    HUMAN_CONSENT = "human_consent"


DESCRIPTIONS: dict[Permission, str] = {
    Permission.READ: "inspect the repository, drafts and authorised example output",
    Permission.DRAFT_EDIT: "make reversible, audited edits to splice/drafts/",
    Permission.BUILD: "publish validated drafts into splice/ (transactional)",
    Permission.OVERWRITE: "replace published files that differ or were edited by hand",
    Permission.EXTERNAL_TOOLS: "run an installed external checker such as nf-core",
    Permission.RUN_NEXTFLOW: "let a checker execute Nextflow (never a pipeline run)",
    Permission.NETWORK: "let a checker contact the network",
    Permission.INSTALL: "install software (no agent operation does this)",
    Permission.PUBLISH_EXTERNAL: "upload or publish outside the repository (none do)",
    Permission.CREDENTIALS: "read credentials or secrets (no operation does this)",
    Permission.HUMAN_CONSENT: "decisions only a person can make, such as "
    "publishing maintainers' contact details",
}

#: Granted by default. Assisted sessions still need approval for each stage.
DEFAULT_GRANTS = frozenset({Permission.READ, Permission.DRAFT_EDIT, Permission.BUILD})
#: Grants a user may add explicitly.
GRANTABLE = frozenset(
    {
        Permission.READ,
        Permission.DRAFT_EDIT,
        Permission.BUILD,
        Permission.OVERWRITE,
        Permission.EXTERNAL_TOOLS,
        Permission.RUN_NEXTFLOW,
        Permission.NETWORK,
    }
)
#: Never granted to an agent: nf-splice offers no agent operation for them.
NEVER_GRANTED = frozenset(Permission) - GRANTABLE


class PolicyViolation(PermissionError):
    """An agent requested something the policy does not allow."""


class Budgets(BaseModel):
    """Bounds on one session; the engine stops safely when one is reached."""

    model_config = ConfigDict(extra="forbid")

    max_tool_calls: int = Field(default=300, ge=1, le=5000)
    max_turns_per_step: int = Field(default=30, ge=1, le=200)
    max_stage_attempts: int = Field(default=3, ge=1, le=10)
    turn_timeout_seconds: float = Field(default=600.0, gt=0, le=7200)
    max_budget_usd: float | None = Field(default=None, gt=0)
    model: str | None = None


class ExecutionPolicy(BaseModel):
    """The scope a person approved for a session."""

    model_config = ConfigDict(extra="forbid")

    grants: list[Permission] = Field(
        default_factory=lambda: sorted(DEFAULT_GRANTS, key=lambda item: item.value)
    )
    budgets: Budgets = Field(default_factory=Budgets)
    examples: list[str] = Field(default_factory=list)
    allow_remote_model: bool = False
    approved_by: str | None = None
    approved_at: str | None = None

    def granted(self, permission: Permission) -> bool:
        return permission in self.grants

    def require(self, permission: Permission) -> None:
        if permission in NEVER_GRANTED:
            raise PolicyViolation(
                f"{permission.value}: {DESCRIPTIONS[permission]}; an agent can "
                "never be given this permission"
            )
        if permission not in self.grants:
            raise PolicyViolation(
                f"permission {permission.value!r} ({DESCRIPTIONS[permission]}) was "
                "not granted for this session"
            )


def validate_grants(values: list[str]) -> list[Permission]:
    """Parse user-supplied grants; refuse unknown and never-grantable ones."""
    grants: set[Permission] = set(DEFAULT_GRANTS)
    for value in values:
        try:
            permission = Permission(value)
        except ValueError as error:
            known = ", ".join(sorted(item.value for item in GRANTABLE))
            raise PolicyViolation(
                f"unknown permission {value!r}; grantable: {known}"
            ) from error
        if permission in NEVER_GRANTED:
            raise PolicyViolation(
                f"{permission.value} cannot be granted: {DESCRIPTIONS[permission]}"
            )
        grants.add(permission)
    return sorted(grants, key=lambda item: item.value)


def relative_path(root: Path, value: str) -> Path:
    """Resolve a repository-relative path, refusing escapes and symlink exits."""
    pure = PurePosixPath(value.replace("\\", "/"))
    if not value or pure.is_absolute() or ".." in pure.parts:
        raise PolicyViolation(f"path {value!r} is outside the authorised repository")
    resolved = (root / pure).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise PolicyViolation(f"path {value!r} escapes the repository")
    return resolved
