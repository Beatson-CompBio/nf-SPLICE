"""Provenance: choose how the RO-Crate is prepared, without raw JSON-LD."""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, RadioButton, RadioSet, Static

from nf_splice.interfaces.tui.model import WorkspaceModel, bounded
from nf_splice.interfaces.tui.navigation import StepState, Target
from nf_splice.interfaces.tui.pages.base import PageView
from nf_splice.interfaces.tui.widgets import Card, IssueList, plain

CHOICES = (
    (
        "adopt",
        "Use the pipeline's existing RO-Crate",
        "A copy is reviewed; the original ro-crate-metadata.json is never changed.",
    ),
    (
        "correct",
        "Correct a copy from the confirmed identity",
        "Keeps the existing graph and fixes the values that disagree with Identity.",
    ),
    (
        "regenerate",
        "Create a minimal RO-Crate from the confirmed identity",
        "Generates the required starting graph; review its contents.",
    ),
    (
        "nf-core",
        "Use the nf-core generator (advanced)",
        "Runs nf-core's generator on an isolated copy after you approve external "
        "tools and network use; the result is a candidate to review.",
    ),
)


class ProvenancePage(PageView):
    page_id = "provenance"
    form_layer = "provenance"
    help_text = (
        "**Provenance** describes the workflow's source and authorship as an "
        "RO-Crate graph published with the bundle. You choose how the graph is "
        "prepared; nf-SPLICE adds the bundle's own files when it publishes.\n\n"
        "**Example:** a pipeline with its own ro-crate-metadata.json usually "
        "adopts a copy; if its name or version disagrees with Identity, correct "
        "the copy from the identity."
    )

    def __init__(self) -> None:
        super().__init__()
        self.assessment: dict[str, Any] | None = None
        self._assessed_key = ""

    def body(self) -> ComposeResult:
        with Card(title="Choose how to prepare the RO-Crate"):
            with RadioSet(id="provenance-choice"):
                for key, label, _hint in CHOICES:
                    yield RadioButton(label, id=f"choice-{key}")
            yield Static("", id="provenance-hint", classes="muted")
            yield Static("", id="provenance-current", classes="detail")
            with Horizontal(classes="row"):
                yield Button("Inspect differences", id="provenance-differences")
                yield Button("Open advanced graph editor", id="provenance-yaml")
                yield Button("Check the graph", id="provenance-check")
                yield Button("Apply choice", id="provenance-apply", variant="primary")
        yield IssueList(id="provenance-issues")

    def refresh_page(self, model: WorkspaceModel) -> None:
        self.loaded_sha = model.layer("provenance").sha256
        data = model.layer("provenance").data
        origin = data.get("origin") or data.get("strategy") or "not chosen"
        issues = [
            item
            for item in model.layer("provenance").issues
            if item.code != "identity_not_ready" or not model.layer("bundle").ready
        ]
        self.query_one("#provenance-issues", IssueList).show(
            (item.severity, item.message) for item in issues
        )
        if self._assessed_key != model.key:
            self._assessed_key = model.key
            self.workspace.run_view(
                "provenance",
                lambda: _assess(model.repository),
                self.show_assessment,
            )
        self._current(str(origin))

    def show_assessment(self, assessment: dict[str, Any]) -> None:
        self.assessment = assessment
        self._current(None)

    def _current(self, origin: str | None) -> None:
        if origin is not None:
            self._origin = origin
        origin = getattr(self, "_origin", "not chosen")
        assessment = self.assessment
        lines = [f"Current source: {origin}"]
        identity_ready = bool(self.model and self.model.layer("bundle").ready)
        reasons: dict[str, str] = {}
        if assessment is None:
            lines.append("Assessing the repository's RO-Crate…")
        else:
            root = assessment["root_crate"]
            generator = assessment["generator"]
            recommendation = assessment["recommendation"]
            lines.append(
                "Repository RO-Crate: "
                + ("present" if root["present"] else "none")
                + f" · recommendation: {recommendation['action']}"
            )
            lines.extend(
                f"  {bounded(item, 160)}" for item in recommendation["reasons"][:3]
            )
            if not root["present"]:
                reasons["adopt"] = "the repository has no ro-crate-metadata.json"
                reasons["correct"] = "the repository has no ro-crate-metadata.json"
            if not identity_ready:
                reasons.setdefault("correct", "complete Identity first")
                reasons["regenerate"] = "complete Identity first"
            if not generator["installed"]:
                reasons["nf-core"] = "nf-core is not installed"
            elif not generator["applicable"]:
                reasons["nf-core"] = bounded(generator["reason"], 120)
        for key, label, _hint in CHOICES:
            button = self.query_one(f"#choice-{key}", RadioButton)
            button.disabled = key in reasons
            button.label = label + (
                f"  (unavailable: {reasons[key]})" if key in reasons else ""
            )
        self.query_one("#provenance-current", Static).update(plain("\n".join(lines)))

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        key = (event.pressed.id or "").removeprefix("choice-")
        hint = next((text for name, _label, text in CHOICES if name == key), "")
        self.query_one("#provenance-hint", Static).update(plain(hint))

    def tag_text(self, model: WorkspaceModel, state: StepState) -> str:
        return super().tag_text(model, state)

    def focus_target(self, target: Target) -> None:
        self.query_one("#provenance-choice", RadioSet).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.id or ""
        if button == "provenance-yaml":
            event.stop()
            self.workspace.open_draft("provenance")
        elif button == "provenance-differences":
            event.stop()
            self._differences()
        elif button == "provenance-check":
            event.stop()
            self._check()
        elif button == "provenance-apply":
            event.stop()
            self._apply()

    def _differences(self) -> None:
        assessment = self.assessment
        if assessment is None:
            self.say("Still assessing the RO-Crate; try again in a moment.")
            return
        findings = assessment["root_crate"]["findings"]
        draft = assessment["draft"]
        lines = ["Repository RO-Crate findings (against the confirmed identity):"]
        for item in findings:
            lines.append(
                f"- {item.get('severity')}: {item.get('pointer') or '/'} "
                f"{item.get('message')}"
            )
        if not findings:
            lines.append("- none: it agrees with the identity")
        lines.append("")
        lines.append(f"Draft graph (origin: {draft.get('origin') or 'unknown'}):")
        lines.extend(f"- error: {item}" for item in draft["errors"])
        lines.extend(f"- warning: {item}" for item in draft["warnings"])
        if not draft["errors"] and not draft["warnings"]:
            lines.append("- validates")
        self.workspace.view_text("RO-Crate differences", "\n".join(lines))

    def _check(self) -> None:
        def show(result: dict[str, Any]) -> None:
            structural = result["structural"]
            text = [
                result["statement"],
                "",
                f"Structural checks: {structural['status']}",
                *(f"- {item}" for item in structural["errors"]),
                f"Standards ({result['standards']['name']}): "
                f"{result['standards']['status']} ({result['standards']['reason']})",
            ]
            self.workspace.view_text("RO-Crate checks", "\n".join(text))

        from nf_splice.services.crate_review import check_crate

        root = self.workspace.repository
        self.workspace.run_view("crate-check", lambda: check_crate(root), show)

    def _apply(self) -> None:
        pressed = self.query_one("#provenance-choice", RadioSet).pressed_button
        if pressed is None:
            self.say("Choose how to prepare the RO-Crate first.", "warn")
            return
        key = (pressed.id or "").removeprefix("choice-")
        from nf_splice.layers.provenance import (
            choose_include,
            generate_minimal,
            generate_with_nf_core,
            prepare_enrichment,
        )

        root = self.workspace.repository
        if key == "nf-core":
            from nf_splice.interfaces.tui.modals import ConfirmDialog

            def approved(result: Any) -> None:
                if result:
                    self.workspace.write(
                        "Running the nf-core RO-Crate generator",
                        lambda: generate_with_nf_core(
                            root, self.workspace.change_context(), approve=True
                        ),
                        then=lambda _r: self.say(
                            "Generated a candidate graph; review it.", "good"
                        ),
                        page=self,
                        layer="provenance",
                    )

            self.app.push_screen(
                ConfirmDialog(
                    "Run the nf-core generator?",
                    "This runs the installed nf-core tool on an isolated copy below "
                    ".splice-local/tmp/ and may use the network. The pipeline is not "
                    "changed. The result replaces the draft graph as a candidate to "
                    "review.",
                    confirm="Approve and run",
                ),
                approved,
            )
            return
        action = {
            "adopt": choose_include,
            "correct": prepare_enrichment,
            "regenerate": generate_minimal,
        }[key]
        label = next(text for name, text, _hint in CHOICES if name == key)
        self.workspace.write(
            label,
            lambda: action(root, self.workspace.change_context()),
            then=lambda _r: self.say(f"Done: {label.lower()}.", "good"),
            page=self,
            layer="provenance",
        )


def _assess(root: Any) -> dict[str, Any]:
    from nf_splice.services.crate_review import assess_crate

    return assess_crate(root)
