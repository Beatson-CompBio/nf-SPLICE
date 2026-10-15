"""Review-event attribution models separating public and private identity."""

from __future__ import annotations

import re
from enum import Enum

from pydantic import Field, field_validator

from nf_splice.domain.authoring import DomainModel, NonEmptyString

_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


class ChangeOrigin(str, Enum):
    """Interface or process from which a draft change originated."""

    MANUAL_CLI = "manual_cli"
    MANUAL_TUI = "manual_tui"
    EXTERNAL_EDIT = "external_edit"
    AGENT_SUGGESTION = "agent_suggestion"
    AGENT_PROPOSED_BATCH = "agent_proposed_batch"
    AUTOMATION = "automation"
    MIGRATION = "migration"
    DISCOVERY = "discovery"


class ApprovalStatus(str, Enum):
    """Whether a human approved the change, or which policy applied it."""

    APPROVED = "approved"
    PROPOSED = "proposed"
    REJECTED = "rejected"
    AUTOMATION_POLICY = "automation_policy"
    NOT_REQUIRED = "not_required"


class ActorKind(str, Enum):
    """Kind of party responsible for a change."""

    HUMAN = "human"
    AUTOMATION = "automation"
    AGENT = "agent"
    UNATTRIBUTED = "unattributed"


class Actor(DomainModel):
    """A public-safe actor label; never carries an e-mail address."""

    label: NonEmptyString
    kind: ActorKind = ActorKind.HUMAN

    @field_validator("label")
    @classmethod
    def _no_contact_details(cls, value: str) -> str:
        if _EMAIL.search(value):
            raise ValueError("public actor labels must not contain e-mail addresses")
        return value


UNATTRIBUTED = Actor(label="unattributed", kind=ActorKind.UNATTRIBUTED)


class ReviewEvent(DomainModel):
    """Public-safe record of one explicit review or change event.

    The timestamp is captured when the event happens and stored with the
    event, so later renders never change it.
    """

    id: NonEmptyString
    at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    layer: NonEmptyString
    action: NonEmptyString
    pointers: tuple[str, ...] = ()
    origin: ChangeOrigin
    approval: ApprovalStatus
    actor: Actor
    approved_by: Actor | None = None
    tool: NonEmptyString
    tool_version: NonEmptyString
    before_sha256: str | None = None
    after_sha256: str | None = None
    source_revision: str | None = None
