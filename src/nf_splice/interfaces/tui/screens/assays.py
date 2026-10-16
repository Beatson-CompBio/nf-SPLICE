"""Assay capabilities: which assays the pipeline can process.

Browse the SPLICE vocabulary's assays with their exact entity types and every
modality path, see the assays the repository names, and declare or remove
capabilities. Each change is written to the draft at once through the same
service as the CLI and agents, so leaving the step never loses a selection.
"""

from __future__ import annotations

from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Input, Label, Select, Static, Switch

from nf_splice.catalogue import (
    CatalogueError,
    EntityType,
    ResolvedCapability,
    default_catalogue,
)
from nf_splice.inspectors.assays import detect_assay_candidates
from nf_splice.interfaces.tui.screens._common import issue_lines
from nf_splice.interfaces.tui.state import WizardSnapshot
from nf_splice.interfaces.tui.widgets import StepView
from nf_splice.layers.bundle import (
    EVIDENCE,
    add_assay_capability,
    declared_capabilities,
    remove_assay_capability,
)


def _badge(kind: EntityType) -> str:
    """An entity-type badge. Texts are shown as plain ``Text``, never markup."""
    return f"[{kind.value}]"


def _path(capability: ResolvedCapability, index: int) -> str:
    return " > ".join(
        f"{item.label} {_badge(item.entity_type)}" for item in capability.paths[index]
    )


def declared_tree(repository: Any) -> str:
    """Declared capabilities grouped under every modality they belong to."""
    catalogue = default_catalogue()
    grouped: dict[str, list[str]] = {}
    for entry in declared_capabilities(repository):
        try:
            item = catalogue.resolve_reference(entry)
        except CatalogueError as error:
            grouped.setdefault("Needs attention", []).append(f"  {entry}: {error}")
            continue
        for path in item.paths:
            modality = f"{path[-1].label} {_badge(path[-1].entity_type)}"
            middle = " > ".join(entity.label for entity in reversed(path[1:-1]))
            grouped.setdefault(modality, []).append(
                f"  {item.assay.label} {_badge(item.assay.entity_type)} "
                f"({item.key}; {entry.get('evidence', 'no evidence')})"
                + (f"  via {middle}" if middle else "")
            )
    if not grouped:
        return "No assay capability is declared yet."
    return "\n".join(
        line for modality in sorted(grouped) for line in (modality, *grouped[modality])
    )


class AssaysView(StepView):
    step_id = "assays"
    explanation = (
        "Declare every assay this pipeline can process across its supported "
        "routes, not only what one example run used. An assay (ASSAY_METHOD or "
        "ASSAY_TYPE) belongs to one or more modalities; poly(A) RNA-seq is an "
        "assay method under Transcriptomics, not a modality. Accepting FASTQ "
        "does not by itself establish a library preparation."
    )

    def compose(self) -> ComposeResult:
        yield Static("Declared capabilities, by modality", classes="heading")
        yield Static("", id="assays-declared", classes="section")
        yield Static("Assays named in the repository", classes="heading")
        yield Static("", id="assays-candidates", classes="section")
        yield Static("Vocabulary", classes="heading")
        with Horizontal(classes="row"):
            yield Switch(value=False, id="assays-all")
            yield Label("Include assay concepts without a platform registration")
        yield DataTable(id="assays-table")
        yield Static("", id="assays-detail", classes="section")
        yield Select(
            [(item, item) for item in EVIDENCE],
            value="asserted",
            allow_blank=False,
            id="assays-evidence",
        )
        yield Input(
            placeholder="why the pipeline supports this assay (required)",
            id="assays-rationale",
        )
        yield Input(
            placeholder="evidence locations path:line, comma separated",
            id="assays-sources",
        )
        with Horizontal(classes="row"):
            yield Button(
                "Declare highlighted assay", id="assays-add", variant="primary"
            )
            yield Button("Remove highlighted assay", id="assays-remove")
        yield Static("", id="assays-issues", classes="issues")

    def setup(self) -> None:
        table = self.query_one("#assays-table", DataTable)
        table.add_columns("", "reference", "assay", "type", "modalities", "deployment")
        table.cursor_type = "row"

    def _rows(self) -> tuple[ResolvedCapability, ...]:
        everything = self.query_one("#assays-all", Switch).value
        found = default_catalogue().assays(registered_only=not everything)
        return tuple(
            sorted(found, key=lambda item: (item.paths[0][-1].label, item.assay.label))
        )

    def _declared_keys(self) -> set[str]:
        catalogue = default_catalogue()
        keys = set()
        for entry in declared_capabilities(self.wizard.repository):
            try:
                keys.add(catalogue.resolve_reference(entry).key)
            except CatalogueError:
                continue
        return keys

    def refresh_view(self, snapshot: WizardSnapshot) -> None:
        repository = snapshot.repository
        self.query_one("#assays-declared", Static).update(
            Text(declared_tree(repository))
        )
        candidates = detect_assay_candidates(repository)
        self.query_one("#assays-candidates", Static).update(
            Text(
                "\n".join(
                    f"{item.key}: {item.label} [{item.entity_type}] at "
                    f"{', '.join(item.locations[:3])}"
                    for item in candidates
                )
                or "No assay is named in the repository's documentation or schema."
            )
        )
        table = self.query_one("#assays-table", DataTable)
        cursor = table.cursor_row
        table.clear()
        declared = self._declared_keys()
        for item in self._rows():
            deployment = ""
            if item.registration is not None:
                deployment = "current" if item.registration.current else "registered"
            table.add_row(
                "x" if item.key in declared else "",
                item.key,
                item.assay.label,
                item.assay.entity_type.value,
                ", ".join(sorted({path[-1].label for path in item.paths})),
                deployment,
                key=item.key,
            )
        if table.row_count:
            table.move_cursor(row=min(max(cursor, 0), table.row_count - 1))
        self._show_detail()
        self.query_one("#assays-issues", Static).update(
            issue_lines(repository, "bundle")
        )

    def _highlighted(self) -> ResolvedCapability | None:
        table = self.query_one("#assays-table", DataTable)
        if not table.row_count:
            return None
        key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        return next((item for item in self._rows() if item.key == key), None)

    def _show_detail(self) -> None:
        item = self._highlighted()
        if item is None:
            text = ""
        else:
            lines = [
                f"{item.assay.label} {_badge(item.assay.entity_type)} "
                f"(entity {item.assay.entity_id})"
            ]
            lines += [
                f"  path: {_path(item, index)}" for index in range(len(item.paths))
            ]
            if item.registration is not None:
                lines.append(
                    f"  registered as {item.registration.code}; deployment support "
                    "(current) does not limit what a pipeline may declare"
                )
            text = "\n".join(lines)
        self.query_one("#assays-detail", Static).update(Text(text))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._show_detail()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "assays-all":
            self.refresh_view(self.wizard.snapshot)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        app = self.wizard
        item = self._highlighted()
        if event.button.id not in {"assays-add", "assays-remove"}:
            return
        event.stop()
        if item is None:
            app.set_status("Highlight an assay first.", error=True)
            return
        if event.button.id == "assays-remove":
            app.perform(
                f"Removing {item.key}",
                lambda: remove_assay_capability(
                    app.repository, item.key, app.change_context()
                ),
            )
            return
        rationale = self.query_one("#assays-rationale", Input).value.strip()
        if not rationale:
            app.set_status("Say why the pipeline supports this assay.", error=True)
            return
        evidence = str(self.query_one("#assays-evidence", Select).value)
        sources = tuple(
            part.strip()
            for part in self.query_one("#assays-sources", Input).value.split(",")
            if part.strip()
        )
        app.perform(
            f"Declaring {item.key}",
            lambda: add_assay_capability(
                app.repository,
                item.key,
                app.change_context(),
                evidence=evidence,
                rationale=rationale,
                sources=sources,
            ),
        )

    def unsaved(self) -> dict[str, str]:
        return {
            "rationale": self.query_one("#assays-rationale", Input).value,
            "sources": self.query_one("#assays-sources", Input).value,
        }

    def restore(self, values: dict[str, str]) -> None:
        if values.get("rationale"):
            self.query_one("#assays-rationale", Input).value = values["rationale"]
        if values.get("sources"):
            self.query_one("#assays-sources", Input).value = values["sources"]
