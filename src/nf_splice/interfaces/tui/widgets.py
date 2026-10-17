"""Shared wizard widgets: progress rail, status line and step view base."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from textual.containers import VerticalScroll
from textual.widgets import Label, ListItem, ListView, Static

from nf_splice.interfaces.tui.state import WizardSnapshot
from nf_splice.interfaces.tui.steps import STEPS, StepStatus, status

if TYPE_CHECKING:
    from nf_splice.interfaces.tui.app import NfSpliceApp

GLYPHS = {
    StepStatus.LOCKED: "·",
    StepStatus.TODO: "○",
    StepStatus.BLOCKED: "!",
    StepStatus.DEFERRED: "»",
    StepStatus.COMPLETE: "✓",
}


class ProgressRail(ListView):
    """Keyboard-navigable checklist of steps with their derived status."""

    def __init__(self, *, id: str | None = None) -> None:
        super().__init__(
            *(
                ListItem(
                    Label(item.title, id=f"rail-label-{item.id}"), id=f"rail-{item.id}"
                )
                for item in STEPS
            ),
            id=id,
        )

    def update_steps(
        self,
        snapshot: WizardSnapshot,
        current: str,
        visited: frozenset[str],
        deferred: frozenset[str],
    ) -> None:
        for item in STEPS:
            state = status(item, snapshot, visited=visited, deferred=deferred)
            marker = "▶ " if item.id == current else "  "
            labels = self.query(f"#rail-label-{item.id}")
            for label in labels:
                assert isinstance(label, Label)
                label.update(f"{marker}{GLYPHS[state]} {item.title}")


class StatusLine(Static):
    """Persistent message line; errors stay until replaced by a success."""

    def show(self, message: str, *, error: bool = False) -> None:
        self.set_class(error, "error")
        self.update(("Error: " if error else "") + message)


class StepView(VerticalScroll):
    """Base class of every step; subclasses render one focused task."""

    step_id: ClassVar[str] = ""
    title: ClassVar[str] = ""
    explanation: ClassVar[str] = ""

    @property
    def wizard(self) -> NfSpliceApp:
        from nf_splice.interfaces.tui.app import NfSpliceApp

        app = self.app
        assert isinstance(app, NfSpliceApp)
        return app

    def on_mount(self) -> None:
        self.setup()
        self.refresh_view(self.wizard.snapshot)
        self.restore(self.wizard.session.unsaved.get(self.step_id, {}))

    def setup(self) -> None:
        """Configure child widgets once they are mounted."""

    def refresh_view(self, snapshot: WizardSnapshot) -> None:
        """Re-render from a freshly derived snapshot."""

    def unsaved(self) -> dict[str, str]:
        """Return half-typed form values to keep in the session."""
        return {}

    def restore(self, values: dict[str, str]) -> None:
        """Restore half-typed form values from the session."""

    def help_text(self) -> str:
        return self.explanation

    @staticmethod
    def table_text(rows: list[list[Any]]) -> str:
        return "\n".join("  ".join(str(cell) for cell in row) for row in rows)


#: Plain-language explanations of common validation codes (Explain errors).
EXPLANATIONS = {
    "unresolved": "A seeded entry still leaves a required field empty. Write "
    "the value into the draft (the form or the YAML file).",
    "missing_required": "A required value is missing. Supply it in the draft.",
    "invalid_value": "A value does not meet the contract (type, format or "
    "allowed values). Correct it at the pointer shown.",
    "syntax": "The YAML file cannot be parsed. Fix it in your editor; nf-splice "
    "never rewrites a file it cannot read.",
    "route_not_covered": "Static analysis found a published route no output "
    "pattern matches. Add an output for it, or list it under excluded_routes "
    "with a reason. This is a warning: it does not block the build.",
    "missing_assay_classification": "No assay is declared. Declare every assay "
    "the pipeline supports; ingestion needs at least one.",
    "identity_not_ready": "This layer needs a valid identity first; fix the "
    "Identity step.",
    "unresolved_component": "A module's container or version could not be "
    "resolved from the source. Resolve it in the draft and remove the item "
    "from 'unresolved'.",
    "section_policy": "A value in a config's parameter section conflicts with "
    "the input access policy.",
    "unsafe_config": "The config contains a secret, a personal path, a literal "
    "account or a test setting. Move it to the deployment's own configuration.",
    "conflicting_evidence": "The repository disagrees about this value; write "
    "the correct one into the draft.",
    "stale_value": "The RO-Crate disagrees with the reviewed identity; correct "
    "the graph in the provenance draft.",
}


_GENERIC = "See the message shown by Validate."


class FilePanel(Static):
    """The file-first actions every layer step offers.

    The YAML draft is the source of truth: open it in an editor, reload it
    after an edit, validate it, preview the file it compiles to and read what
    each issue means. Nothing here waits for candidate decisions.
    """

    DEFAULT_CSS = "FilePanel { height: auto; }"

    def __init__(self, layer: str, *, config: bool = False) -> None:
        super().__init__(id=f"file-{layer}")
        self.draft_layer = layer
        self.config = config

    def compose(self) -> Any:
        from textual.containers import Horizontal
        from textual.widgets import Button

        with Horizontal(classes="row"):
            yield Button("Open YAML", id=f"file-{self.draft_layer}-open")
            if self.config:
                yield Button("Open config", id=f"file-{self.draft_layer}-config")
            yield Button("Reload", id=f"file-{self.draft_layer}-reload")
            yield Button("Validate", id=f"file-{self.draft_layer}-validate")
            yield Button("Preview JSON", id=f"file-{self.draft_layer}-preview")
            yield Button("Explain errors", id=f"file-{self.draft_layer}-explain")
        yield Static("", id=f"file-{self.draft_layer}-output", classes="section")

    @property
    def wizard(self) -> NfSpliceApp:
        from nf_splice.interfaces.tui.app import NfSpliceApp

        app = self.app
        assert isinstance(app, NfSpliceApp)
        return app

    def _show(self, text: str) -> None:
        self.query_one(f"#file-{self.draft_layer}-output", Static).update(text)

    def _edit(self, relative: str) -> None:
        import os
        import shlex
        import subprocess

        path = self.wizard.repository / relative
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
        if not editor:
            self._show(
                f"Edit {path} in any editor (set $VISUAL or $EDITOR to open it "
                "from here), then press Reload."
            )
            return
        with self.wizard.suspend():
            subprocess.run([*shlex.split(editor), str(path)], check=False)
        self.wizard.action_reload()
        self._show(f"Reloaded {relative} after editing.")

    def on_button_pressed(self, event: Any) -> None:
        from nf_splice.layers.base import layer_spec
        from nf_splice.services.lifecycle import validate_layer

        identifier = str(event.button.id or "")
        prefix = f"file-{self.draft_layer}-"
        if not identifier.startswith(prefix):
            return
        event.stop()
        action = identifier.removeprefix(prefix)
        repository = self.wizard.repository
        if action == "open":
            self._edit(layer_spec(self.draft_layer).draft)
        elif action == "config":
            from nf_splice.layers.execution import list_config_drafts

            configs = list_config_drafts(repository)
            if configs:
                self._edit(configs[0])
            else:
                self._show("No authored config exists yet.")
        elif action == "reload":
            self.wizard.action_reload()
            self._show("Reloaded the current files from disk.")
        elif action == "validate":
            validation = validate_layer(repository, self.draft_layer)
            self._show(
                "Valid: ready to publish."
                if validation.ready
                else "\n".join(
                    f"{item.severity.value.upper()} {item.path}#{item.pointer or '/'} "
                    f"[{item.code}] {item.message}"
                    for item in validation.issues
                )
                or "Not ready."
            )
        elif action == "preview":
            validation = validate_layer(repository, self.draft_layer)
            name = next(
                (item for item in validation.files if item.endswith(".json")), None
            )
            if name is None:
                self._show("Nothing to preview until the layer validates.")
            else:
                self._show(
                    f"splice/{name} (preview, not written):\n"
                    + validation.files[name].decode("utf-8")[:6000]
                )
        elif action == "explain":
            validation = validate_layer(repository, self.draft_layer)
            codes = sorted({item.code for item in validation.issues})
            self._show(
                "\n".join(
                    f"{code}: {EXPLANATIONS.get(code, _GENERIC)}" for code in codes
                )
                or "No issues."
            )
