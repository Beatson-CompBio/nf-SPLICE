"""Actor attribution, public/private separation and the private audit store."""

from __future__ import annotations

import datetime
import json
import stat
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from nf_splice.cli import app
from nf_splice.domain import Actor, ActorKind, ApprovalStatus, ChangeOrigin
from nf_splice.services.audit import (
    GitIdentity,
    make_event,
    read_private,
    record_private,
    redact,
    resolve_actor,
    suggest_git_identity,
)

runner = CliRunner()


def _clock() -> datetime.datetime:
    return datetime.datetime(2026, 10, 15, 9, 30, 5, tzinfo=datetime.timezone.utc)


def test_actor_resolution_never_requires_git_configuration() -> None:
    assert resolve_actor(environment={}).kind is ActorKind.UNATTRIBUTED
    assert resolve_actor("Ada", environment={}).label == "Ada"
    assert resolve_actor(environment={"NF_SPLICE_ACTOR": "Lab"}).label == "Lab"
    ci = resolve_actor(environment={"GITHUB_ACTIONS": "true", "GITHUB_ACTOR": "bot"})
    assert (ci.label, ci.kind) == ("ci:bot", ActorKind.AUTOMATION)
    with pytest.raises(ValidationError, match="e-mail"):
        Actor(label="ada@example.org")


def test_git_identity_is_only_a_suggestion(tmp_path: Path) -> None:
    assert suggest_git_identity(tmp_path) is None
    subprocess.run(("git", "init", "-q", str(tmp_path)), check=True)
    subprocess.run(
        ("git", "-C", str(tmp_path), "config", "user.email", "ada@example.org"),
        check=True,
    )
    subprocess.run(
        ("git", "-C", str(tmp_path), "config", "user.name", "Ada"), check=True
    )
    suggestion = suggest_git_identity(tmp_path)
    assert suggestion == GitIdentity(name="Ada", email="ada@example.org")
    assert resolve_actor(environment={}).kind is ActorKind.UNATTRIBUTED


def test_events_capture_time_once_and_carry_no_contact_details() -> None:
    event = make_event(
        layer="bundle",
        action="confirm",
        origin=ChangeOrigin.AGENT_ASSISTED,
        approval=ApprovalStatus.APPROVED,
        actor=Actor(label="claude", kind=ActorKind.AGENT),
        approved_by=Actor(label="Ada"),
        pointers=("/pipeline/name",),
        clock=_clock,
    )
    assert event.at == "2026-10-15T09:30:05Z"
    assert event == make_event(
        layer="bundle",
        action="confirm",
        origin=ChangeOrigin.AGENT_ASSISTED,
        approval=ApprovalStatus.APPROVED,
        actor=Actor(label="claude", kind=ActorKind.AGENT),
        approved_by=Actor(label="Ada"),
        pointers=("/pipeline/name",),
        clock=_clock,
    )
    assert "@" not in event.model_dump_json()
    assert event.origin is ChangeOrigin.AGENT_ASSISTED
    assert event.approved_by is not None and event.approved_by.label == "Ada"


def test_private_store_is_owner_only_outside_the_repository(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    environment = {"NF_SPLICE_AUDIT_DIR": str(tmp_path / "audit")}
    event = make_event(
        layer="outputs",
        action="accept",
        origin=ChangeOrigin.MANUAL_CLI,
        approval=ApprovalStatus.APPROVED,
        actor=Actor(label="Ada"),
        clock=_clock,
    )
    result = record_private(
        repository,
        event,
        contact=GitIdentity("Ada Lovelace", "ada@example.org"),
        environment=environment,
    )
    assert result.stored, result.warning
    files = list((tmp_path / "audit").iterdir())
    assert len(files) == 1
    assert stat.S_IMODE(files[0].stat().st_mode) == 0o600
    assert stat.S_IMODE((tmp_path / "audit").stat().st_mode) == 0o700
    assert not any(repository.iterdir())

    redacted = read_private(repository, environment=environment)
    assert "ada@example.org" not in json.dumps(redacted)
    full = read_private(repository, redacted=False, environment=environment)
    assert full[0]["private_contact"]["email"] == "ada@example.org"

    inside = record_private(
        repository,
        event,
        environment={"NF_SPLICE_AUDIT_DIR": str(repository / "audit")},
    )
    assert not inside.stored and "inside the repository" in str(inside.warning)
    blocked = tmp_path / "blocked"
    blocked.write_text("not a directory", encoding="utf-8")
    failure = record_private(
        repository, event, environment={"NF_SPLICE_AUDIT_DIR": str(blocked)}
    )
    assert not failure.stored and failure.warning


def test_redaction_removes_secrets_and_emails() -> None:
    text = "token=abc123 ghp_" + "a" * 30 + " mail ada@example.org"
    cleaned = redact(text)
    assert "abc123" not in cleaned and "ghp_" not in cleaned
    assert "ada@example.org" not in cleaned


def test_audit_cli_reports_identity_without_publishing_email(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["audit", "identity", "--repository", str(tmp_path), "--json"],
        env={"NF_SPLICE_ACTOR": "Ada"},
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["actor"] == {"label": "Ada", "kind": "human"}
    shown = runner.invoke(app, ["audit", "show", "--repository", str(tmp_path)])
    assert shown.exit_code == 0
    assert json.loads(shown.output) == {"records": []}
