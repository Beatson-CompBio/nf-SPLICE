"""The `nf-splice provider` commands: selection, diagnosis and auth choices."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from typer.testing import CliRunner

from nf_splice import credentials
from nf_splice.cli import app

runner = CliRunner()


def test_list_shows_every_provider_and_billing_route() -> None:
    result = runner.invoke(app, ["provider", "list", "--json"])
    assert result.exit_code == 0, result.output
    rows = {row["name"]: row for row in json.loads(result.output)["providers"]}
    assert {"claude", "openai", "scripted"} <= set(rows)
    assert not any(row["selected"] for row in rows.values())
    assert "Console" in rows["claude"]["billing"]
    assert "ChatGPT" in rows["openai"]["auth"]


def test_doctor_reports_missing_credentials_without_secrets() -> None:
    result = runner.invoke(app, ["provider", "doctor", "--json"])
    assert result.exit_code == 0, result.output
    found = {item["provider"]: item for item in json.loads(result.output)["providers"]}
    assert found["scripted"]["ready"] is True
    assert found["claude"]["authenticated"] is False
    assert any("Console" in line for line in found["claude"]["guidance"])
    assert found["openai"]["authenticated"] is False


def test_saved_key_is_owner_only_and_never_printed(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["provider", "auth", "claude", "--api-key"], input="sk-ant-secret-1\n"
    )
    assert result.exit_code == 0, result.output
    assert "sk-ant-secret-1" not in result.output
    stored = credentials.config_directory() / "keys" / "claude.json"
    assert stat.S_IMODE(stored.stat().st_mode) == 0o600
    doctor = runner.invoke(app, ["provider", "doctor", "claude", "--json"])
    assert "sk-ant-secret-1" not in doctor.output
    assert json.loads(doctor.output)["providers"][0]["authenticated"] is True
    assert str(credentials.config_directory()).startswith(
        os.environ["NF_SPLICE_CONFIG_DIR"]
    )


def test_select_persists_and_api_billing_needs_confirmation() -> None:
    result = runner.invoke(app, ["provider", "select", "openai", "--model", "gpt-x"])
    assert result.exit_code == 0, result.output
    assert credentials.preferences()["provider"] == "openai"
    assert credentials.preferences()["openai_model"] == "gpt-x"
    refused = runner.invoke(app, ["provider", "auth", "openai", "--use", "api-key"])
    assert refused.exit_code == 2 and "bills" in refused.output
    assert credentials.preferences().get("openai_auth") is None
    chosen = runner.invoke(
        app, ["provider", "auth", "openai", "--use", "api-key", "--yes"]
    )
    assert chosen.exit_code == 0
    assert credentials.preferences()["openai_auth"] == "api-key"


def test_session_needs_an_explicit_provider(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["--user", "Ada", "session", "start", "--repository", str(tmp_path)],
    )
    assert result.exit_code == 2
    assert "provider select" in result.output


def test_test_command_requires_remote_consent() -> None:
    result = runner.invoke(app, ["provider", "test", "claude"])
    assert result.exit_code == 2
    assert "allow-remote-model" in result.output
