"""Guided AI provider set-up, from the workspace.

The same provider services as ``nf-splice provider``: diagnose, select,
save a key, sign in with ChatGPT and run the one-tool connection test.
Nothing here is a second registry or sign-in mechanism. The connection test
sends no repository content, needs the person's explicit consent for a
remote model, and its pass is what makes Assisted and Autonomous
integration available (:mod:`nf_splice.agents.providers.readiness`).
Consent to send *repository* context is still asked separately, in the AI
dock, before the first real request.
"""

from __future__ import annotations

import asyncio
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, Input, Select, Static

from nf_splice.interfaces.tui.modals import Dialog
from nf_splice.interfaces.tui.widgets import plain

#: Providers a person can set up here (``scripted`` is for tests only).
CHOICES = ("claude", "openai", "codex", "opencode")
#: Providers that take an API key saved by nf-splice.
KEYED = ("claude", "openai")


def _status_text(name: str) -> tuple[str, bool]:
    """Readiness, the diagnosis and the next step; and whether it is remote."""
    from nf_splice.agents.providers import diagnose
    from nf_splice.agents.providers.readiness import assess

    readiness = assess(name)
    lines = [readiness.summary()]
    remote = True
    try:
        diagnosis = diagnose(name)
    except Exception as error:  # a broken adapter must not close the dialog
        return "\n".join([*lines, f"Cannot diagnose {name}: {error}"]), remote
    remote = not diagnosis.inference.startswith("local")
    lines.append(f"Sign-in: {diagnosis.auth_method}")
    lines.append(f"Runs: {diagnosis.inference} · billing: {diagnosis.billing}")
    for check in diagnosis.checks:
        lines.append(f"{'✓' if check.ok else '✕'} {check.name}: {check.detail}")
    for item in diagnosis.guidance:
        lines.append(f"Next: {item}")
    if readiness.level.value == "unverified":
        lines.append("Next: Save and test the connection below.")
    return "\n".join(lines), remote


class ProviderSetupDialog(Dialog):
    """Choose, sign in to and test an AI provider; returns True when closed."""

    def __init__(self) -> None:
        super().__init__()
        from nf_splice.agents.providers import selected

        name, _model = selected()
        self._name: str = name if name is not None and name in CHOICES else CHOICES[0]
        self._remote = True
        self._busy = False

    def compose(self) -> ComposeResult:
        from nf_splice.agents.providers import PROVIDERS, selected_model

        with Vertical(classes="dialog dialog-wide", id="setup-dialog"):
            yield Static("AI assistance", classes="dialog-title")
            yield Static(
                "Manual integration never needs AI. Assisted and Autonomous "
                "integration need a provider whose connection test has passed: "
                "one short message that contains no repository content.",
                classes="dialog-text",
            )
            with VerticalScroll(classes="dialog-body"):
                yield Static("Provider", classes="field-label")
                yield Select(
                    [(f"{name}: {PROVIDERS[name].summary}", name) for name in CHOICES],
                    value=self._name,
                    allow_blank=False,
                    id="setup-provider",
                )
                yield Static("Checking…", id="setup-status", classes="notice")
                yield Static("Model", classes="field-label")
                yield Input(
                    selected_model(self._name) or "",
                    placeholder="Blank: the provider's default model",
                    id="setup-model",
                )
                with Vertical(id="setup-key-row"):
                    yield Static("API key", classes="field-label")
                    with Horizontal(classes="row"):
                        yield Input(
                            password=True,
                            placeholder="Paste the key; it is saved owner-only in "
                            "your configuration folder",
                            id="setup-key",
                        )
                        yield Button("Save key", id="setup-save-key")
                yield Button("Sign in with ChatGPT…", id="setup-chatgpt")
                yield Checkbox(
                    "I agree to send one short test message (no repository "
                    "content) to this provider, under its billing",
                    id="setup-consent",
                )
            with Horizontal(classes="dialog-actions"):
                yield Button("Done", id="setup-done")
                yield Button("Save without testing", id="setup-select")
                yield Button(
                    "Save and test connection", id="setup-test", variant="primary"
                )

    def on_mount(self) -> None:
        self._show_provider()

    def on_select_changed(self, event: Select.Changed) -> None:
        from nf_splice.agents.providers import selected_model

        if event.select.id == "setup-provider" and event.value in CHOICES:
            self._name = str(event.value)
            self.query_one("#setup-model", Input).value = (
                selected_model(self._name) or ""
            )
            self._show_provider()

    def _say(self, text: str) -> None:
        self.query_one("#setup-status", Static).update(plain(text))

    def _show_provider(self) -> None:
        name = self._name
        self.query_one("#setup-key-row").display = name in KEYED
        self.query_one("#setup-chatgpt").display = name in {"openai", "codex"}
        self._say(f"Checking {name}…")

        def work() -> None:
            text, remote = _status_text(name)
            self.app.call_from_thread(self._diagnosed, name, text, remote)

        self.run_worker(work, thread=True, group="setup", exclusive=True)

    def _diagnosed(self, name: str, text: str, remote: bool) -> None:
        if name != self._name:
            return
        self._remote = remote
        self.query_one("#setup-consent").display = remote
        self._say(text)

    def _model(self) -> str:
        return self.query_one("#setup-model", Input).value.strip()

    def _save_selection(self) -> None:
        from nf_splice.agents.providers import select

        select(self._name, self._model())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        identifier = event.button.id or ""
        if identifier == "setup-done":
            self.dismiss(True)
        elif self._busy:
            self.notify("Wait for the current step to finish.", severity="warning")
        elif identifier == "setup-save-key":
            self._save_key()
        elif identifier == "setup-chatgpt":
            self._chatgpt()
        elif identifier == "setup-select":
            self._save_selection()
            self._show_provider()
            self.notify(f"Saved {self._name}; it is not verified until tested.")
        elif identifier == "setup-test":
            self._test()

    def _save_key(self) -> None:
        from nf_splice import credentials

        field = self.query_one("#setup-key", Input)
        value = field.value.strip()
        field.value = ""
        if not value:
            self.notify("Paste a key first.", severity="warning")
            return
        credentials.store_api_key(self._name, value)
        if self._name == "openai":
            self.notify(
                "Saved. OpenAI uses a key only in API-key mode (metered billing), "
                "chosen with `nf-splice provider auth openai --use api-key --yes`."
            )
        else:
            self.notify("Saved the key owner-only in your configuration folder.")
        self._show_provider()

    def _chatgpt(self) -> None:
        from nf_splice.agents.providers import openai_auth

        self._busy = True
        self._say("Opening your browser to sign in with ChatGPT…")

        def announce(text: str) -> None:
            self.app.call_from_thread(self._say, text)

        def work() -> None:
            try:
                record = openai_auth.sign_in(announce=announce)
                message = f"Signed in: {openai_auth.account_label(record)}."
            except Exception as error:
                message = f"Sign-in did not complete: {error}"
            self.app.call_from_thread(self._finished, message)

        self.run_worker(work, thread=True, group="setup-sign-in")

    def _finished(self, message: str) -> None:
        self._busy = False
        self.notify(message)
        self._show_provider()

    def _test(self) -> None:
        if self._remote and not self.query_one("#setup-consent", Checkbox).value:
            self.notify(
                "Tick the consent box first: the test sends one message to a "
                "remote model.",
                severity="warning",
            )
            return
        self._save_selection()
        name, model = self._name, self._model() or None
        consent = self.query_one("#setup-consent", Checkbox).value
        self._busy = True
        self._say(f"Testing {name}: one short message, no repository content…")

        def work() -> None:
            self.app.call_from_thread(self._finished, _run_test(name, model, consent))

        self.run_worker(work, thread=True, group="setup-test")


def _run_test(name: str, model: str | None, consent: bool) -> str:
    """The same connection test as `nf-splice provider test` (in a worker)."""
    from nf_splice.agents.protocol import require_consent
    from nf_splice.agents.providers import provider_for
    from nf_splice.agents.providers.check import tool_call_check
    from nf_splice.agents.providers.readiness import (
        clear_verification,
        record_verification,
    )

    try:
        provider = provider_for(name, model=model)
        require_consent(provider, consent)
        result: dict[str, Any] = asyncio.run(tool_call_check(provider, model))
    except Exception as error:
        clear_verification(name)
        return f"The connection test could not run: {error}"
    if result.get("passed"):
        record_verification(name, model)
        return f"{name}: the connection test passed. AI integration is available."
    clear_verification(name)
    return f"{name}: the connection test failed: {result.get('detail')}"
