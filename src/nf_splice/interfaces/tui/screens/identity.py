"""Pipeline identity, authors, funders and publication consent."""

from __future__ import annotations

import json
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Input, Label, Static, Switch

from nf_splice.domain.identity import PIPELINE_FIELD_ORDER
from nf_splice.interfaces.tui.screens._common import issue_lines
from nf_splice.interfaces.tui.state import WizardSnapshot
from nf_splice.interfaces.tui.widgets import FilePanel, StepView
from nf_splice.layers import confirm_values
from nf_splice.layers.base import load_review_state, read_layer
from nf_splice.layers.bundle import (
    set_identity_fields,
    unreviewed_detected_values,
)

#: Scalar fields edited with one input each, driven by the domain field order.
SCALAR_FIELDS = tuple(
    name
    for name in PIPELINE_FIELD_ORDER
    if name not in {"authors", "funders", "keywords", "citation", "assay_capabilities"}
)


class IdentityView(StepView):
    step_id = "identity"
    explanation = (
        "Identity is reused by every published contract. Values detected from "
        "nextflow.config, Git, CITATION.cff, README or RO-Crate are prefilled but "
        "need your confirmation. Maintainer contacts are published only with "
        "explicit consent."
    )

    def compose(self) -> ComposeResult:
        yield FilePanel("bundle")
        yield Static("Detected evidence", classes="heading")
        yield Static("", id="identity-evidence", classes="section")
        for name in SCALAR_FIELDS:
            yield Input(placeholder=name.replace("_", " "), id=f"identity-{name}")
        yield Input(placeholder="keywords (comma separated)", id="identity-keywords")
        yield Input(placeholder="citation DOI", id="identity-doi")
        yield Static("Authors (ordered)", classes="heading")
        yield DataTable(id="identity-authors")
        with Horizontal(classes="row"):
            yield Input(placeholder="author name", id="author-name")
            yield Input(placeholder="affiliation", id="author-affiliation")
            yield Input(placeholder="ORCID URL", id="author-orcid")
            yield Button("Add author", id="author-add")
            yield Button("Remove selected", id="author-remove")
        yield Static(
            "Funders: name|award id per line in the field below", classes="heading"
        )
        yield Input(placeholder="Funder name|award id; ...", id="identity-funders")
        with Horizontal(classes="row"):
            yield Switch(value=False, id="identity-publish-contacts")
            yield Label("I approve publishing maintainer contacts in bundle.json")
        with Horizontal(classes="row"):
            yield Button("Save identity", id="identity-save", variant="primary")
            yield Button("Confirm detected values", id="identity-confirm")
        yield Static("", id="identity-issues", classes="issues")

    def setup(self) -> None:
        table = self.query_one("#identity-authors", DataTable)
        table.add_columns("name", "type", "affiliation", "orcid", "role")
        table.cursor_type = "row"

    def _draft(self) -> dict[str, Any]:
        state = read_layer(self.wizard.repository, "bundle")
        if state.draft is None or not isinstance(state.draft.data, dict):
            return {}
        return dict(state.draft.data.get("pipeline") or {})

    def refresh_view(self, snapshot: WizardSnapshot) -> None:
        pipeline = self._draft()
        for name in SCALAR_FIELDS:
            value = pipeline.get(name)
            self.query_one(f"#identity-{name}", Input).value = (
                "" if value is None else str(value)
            )
        self.query_one("#identity-keywords", Input).value = ", ".join(
            pipeline.get("keywords") or []
        )
        citation = pipeline.get("citation") or {}
        self.query_one("#identity-doi", Input).value = str(citation.get("doi") or "")
        self.query_one("#identity-funders", Input).value = "; ".join(
            f"{item.get('name')}|{item.get('award_id') or ''}"
            for item in pipeline.get("funders") or []
        )
        table = self.query_one("#identity-authors", DataTable)
        table.clear()
        for index, author in enumerate(pipeline.get("authors") or []):
            table.add_row(
                author.get("name"),
                author.get("type", "person"),
                author.get("affiliation") or "",
                author.get("orcid") or "",
                author.get("role") or "",
                key=f"author-{index}",
            )
        evidence = (
            load_review_state(snapshot.repository, "bundle").document.get("evidence")
            or []
        )
        self.query_one("#identity-evidence", Static).update(
            "\n".join(
                f"{item['field']}: {json.dumps(item['value'])} ({item['location']})"
                for item in evidence
            )
            or "No identity evidence was detected."
        )
        self.query_one("#identity-issues", Static).update(
            issue_lines(snapshot.repository, "bundle")
        )

    def _authors(self) -> list[dict[str, str]]:
        table = self.query_one("#identity-authors", DataTable)
        authors = []
        for row_key in table.rows:
            name, kind, affiliation, orcid, role = table.get_row(row_key)
            author = {"name": str(name), "type": str(kind)}
            for key, value in (
                ("affiliation", affiliation),
                ("orcid", orcid),
                ("role", role),
            ):
                if str(value):
                    author[key] = str(value)
            authors.append(author)
        return authors

    def collected(self) -> dict[str, Any]:
        """Changed identity values only, for a targeted patch."""
        current = self._draft()
        changes: dict[str, Any] = {}
        for name in SCALAR_FIELDS:
            text = self.query_one(f"#identity-{name}", Input).value.strip()
            value = text or None
            if value != current.get(name):
                changes[name] = value
        keywords = [
            item.strip()
            for item in self.query_one("#identity-keywords", Input).value.split(",")
            if item.strip()
        ]
        if keywords != (current.get("keywords") or []):
            changes["keywords"] = keywords
        doi = self.query_one("#identity-doi", Input).value.strip()
        citation = current.get("citation") or {}
        if doi != str(citation.get("doi") or ""):
            changes["citation"] = (
                {**citation, "doi": doi}
                if doi
                else ({k: v for k, v in citation.items() if k != "doi"} or None)
            )
        funders = []
        for chunk in self.query_one("#identity-funders", Input).value.split(";"):
            name, _sep, award = chunk.partition("|")
            if name.strip():
                funders.append(
                    {"name": name.strip()}
                    | ({"award_id": award.strip()} if award.strip() else {})
                )
        if funders != (current.get("funders") or []):
            changes["funders"] = funders
        authors = self._authors()
        if authors != (current.get("authors") or []):
            changes["authors"] = authors
        if self.query_one("#identity-publish-contacts", Switch).value:
            changes["maintainers_publication_approved"] = True
        return changes

    def on_button_pressed(self, event: Button.Pressed) -> None:
        app = self.wizard
        button = event.button.id
        if button == "author-add":
            event.stop()
            name = self.query_one("#author-name", Input).value.strip()
            if not name:
                app.set_status("An author needs a name.", error=True)
                return
            table = self.query_one("#identity-authors", DataTable)
            table.add_row(
                name,
                "person",
                self.query_one("#author-affiliation", Input).value.strip(),
                self.query_one("#author-orcid", Input).value.strip(),
                "",
                key=f"author-new-{len(table.rows)}",
            )
            for widget in ("#author-name", "#author-affiliation", "#author-orcid"):
                self.query_one(widget, Input).value = ""
        elif button == "author-remove":
            event.stop()
            table = self.query_one("#identity-authors", DataTable)
            if table.row_count:
                row_key = table.coordinate_to_cell_key(table.cursor_coordinate).row_key
                table.remove_row(row_key)
        elif button == "identity-save":
            event.stop()
            changes = self.collected()
            if not changes:
                app.set_status("No identity changes to save.")
                return
            app.perform(
                "Saving identity",
                lambda: set_identity_fields(
                    app.repository, changes, app.change_context()
                ),
            )
        elif button == "identity-confirm":
            event.stop()
            pending = list(unreviewed_detected_values(app.repository))
            if not pending:
                app.set_status("No detected values await confirmation.")
                return
            app.perform(
                "Confirming detected values",
                lambda: confirm_values(
                    app.repository, "bundle", pending, app.change_context()
                ),
            )

    def unsaved(self) -> dict[str, str]:
        return {
            name: self.query_one(f"#identity-{name}", Input).value
            for name in SCALAR_FIELDS
        }

    def restore(self, values: dict[str, str]) -> None:
        for name, value in values.items():
            if name in SCALAR_FIELDS and value:
                self.query_one(f"#identity-{name}", Input).value = value
