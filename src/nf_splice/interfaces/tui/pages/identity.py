"""Identity: five essential fields, provenance chips and collapsed details."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    Checkbox,
    Collapsible,
    DataTable,
    Input,
    Label,
    Select,
    Static,
    TextArea,
)

from nf_splice.domain.identity import (
    PipelineIdError,
    derive_pipeline_id,
    normalise_orcid,
)
from nf_splice.interfaces.tui.model import WorkspaceModel, bounded
from nf_splice.interfaces.tui.navigation import StepState, Target
from nf_splice.interfaces.tui.pages.base import PageView
from nf_splice.interfaces.tui.widgets import Card, IssueList, plain

ESSENTIAL = (
    ("name", "Pipeline name *"),
    ("id", "Pipeline ID *"),
    ("version", "Version *"),
    ("engine", "Engine *"),
    ("repository_url", "Repository URL *"),
)
CITATION = (
    ("doi", "Citation DOI"),
    ("licence", "Licence (SPDX identifier, e.g. MIT)"),
    ("licence_url", "Licence URL"),
)
MORE = (
    ("title", "Display title"),
    ("release_url", "Release URL"),
    ("documentation_url", "Documentation URL"),
    ("support_url", "Support URL"),
    ("project_url", "Project URL"),
    ("engine_version_min", "Minimum Nextflow version"),
    ("keywords", "Keywords (comma-separated)"),
)
_SOURCE_NAMES = {
    "nextflow.config": "config",
    "CITATION.cff": "CITATION.cff",
    "ro-crate-metadata.json": "RO-Crate",
    "integration_record": "upstream",
    "git_remote": "Git remote",
    "git_tag": "Git tag",
}


class IdentityPage(PageView):
    page_id = "identity"
    form_layer = "bundle"
    help_text = (
        "**Identity** names the pipeline in every published contract. Values "
        "imported from an exact key show their source; you can change any of "
        "them.\n\n**What you decide:** the five essential fields, and a short "
        "description. Authors, citation and links are optional details.\n\n"
        "**Example:** Pipeline name `nf-core/rnaseq`, version `3.27.0`, "
        "repository URL `https://github.com/nf-core/rnaseq`. The ID is derived "
        "from the name; edit it only if you must."
    )

    def __init__(self) -> None:
        super().__init__()
        self._loaded: dict[str, Any] = {}
        self._loaded_consent = False
        self._derived_name = ""
        self._choices: dict[str, str] = {}
        self._authors: list[dict[str, str]] = []

    def body(self) -> ComposeResult:
        yield Static("", id="identity-stale", classes="notice warn")
        with Card(title="Essential details", id="identity-essential"):
            yield IssueList(id="identity-issues")
            for name, label in ESSENTIAL:
                with Horizontal(classes="field-row"):
                    yield Label(label, classes="field-label wide")
                    yield Input(id=f"identity-{name}", classes="field-input")
                    yield Static("", id=f"chip-{name}", classes="source-chip")
            yield Label("Description (recommended)", classes="field-label")
            yield TextArea("", id="identity-description", classes="short-text")
        yield Vertical(id="identity-conflicts")
        with Collapsible(
            title="Authors and contributors", id="identity-authors-section"
        ):
            table: DataTable[Any] = DataTable(id="identity-authors", cursor_type="row")
            yield table
            with Horizontal(classes="row"):
                yield Input(placeholder="Name", id="author-name")
                yield Select(
                    [("Person", "person"), ("Organisation", "organization")],
                    value="person",
                    allow_blank=False,
                    id="author-type",
                )
                yield Input(placeholder="Affiliation", id="author-affiliation")
                yield Input(placeholder="ORCID iD (optional)", id="author-orcid")
            with Horizontal(classes="row"):
                yield Button("Add author", id="author-add")
                yield Button("Remove selected author", id="author-remove")
            yield Static("", id="author-error", classes="field-error")
        with Collapsible(title="Citation and licence", id="identity-citation"):
            for name, label in CITATION:
                yield Label(label, classes="field-label")
                yield Input(id=f"identity-{name}")
        with Collapsible(title="More metadata and project links", id="identity-more"):
            for name, label in MORE:
                yield Label(label, classes="field-label")
                yield Input(id=f"identity-{name}")
        with Collapsible(
            title="Maintainer contacts and consent", id="identity-maintainers"
        ):
            yield Static("", id="identity-maintainer-list", classes="muted")
            yield Checkbox(
                "I approve publishing the maintainers' contact details in bundle.json",
                id="identity-consent",
            )
        with Horizontal(classes="page-actions"):
            yield Static(
                "Changes only affect .splice-local/drafts/bundle.draft.yaml",
                classes="muted",
            )
            yield Button("Browse source files", id="identity-sources")
            yield Button("Save identity", id="identity-save", variant="primary")

    def on_mount(self) -> None:
        table = self.query_one("#identity-authors", DataTable)
        table.add_columns("Name", "Type", "Affiliation", "ORCID")
        self.query_one("#identity-stale").display = False

    # ------------------------------------------------------------ values

    def _values_from(self, pipeline: Mapping[str, Any]) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for name, _label in (*ESSENTIAL, *MORE):
            value = pipeline.get(name)
            if name == "keywords":
                values[name] = ", ".join(str(item) for item in value or [])
            else:
                values[name] = "" if value is None else str(value)
        citation = pipeline.get("citation") or {}
        values["doi"] = (
            str(citation.get("doi") or "") if isinstance(citation, Mapping) else ""
        )
        values["licence"] = str(pipeline.get("licence") or "")
        values["licence_url"] = str(pipeline.get("licence_url") or "")
        values["description"] = str(pipeline.get("description") or "")
        values["authors"] = [
            {
                key: str(item[key])
                for key in ("name", "type", "affiliation", "orcid")
                if item.get(key)
            }
            for item in pipeline.get("authors") or []
            if isinstance(item, Mapping)
        ]
        return values

    def current_values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for name, _label in (*ESSENTIAL, *CITATION, *MORE):
            values[name] = self.query_one(f"#identity-{name}", Input).value.strip()
        values["description"] = self.query_one(
            "#identity-description", TextArea
        ).text.strip()
        values["authors"] = [dict(item) for item in self._authors]
        return values

    def discard_unsaved(self) -> None:
        super().discard_unsaved()
        self._loaded = {}

    def has_unsaved(self) -> bool:
        if not self._loaded:
            return False
        current = self.current_values()
        consent = self.query_one("#identity-consent", Checkbox).value
        return current != self._loaded or consent != self._loaded_consent

    def _fill(self, model: WorkspaceModel) -> None:
        data = model.layer("bundle").data
        values = self._values_from(model.pipeline())
        for name, _label in (*ESSENTIAL, *CITATION, *MORE):
            self.query_one(f"#identity-{name}", Input).value = values.get(name, "")
        self.query_one("#identity-description", TextArea).text = values["description"]
        self._authors = list(values["authors"])
        self._fill_authors()
        self._loaded = self.current_values()
        self._derived_name = self._loaded.get("name", "")
        consent = bool(data.get("maintainers_publication_approved"))
        self.query_one("#identity-consent", Checkbox).value = consent
        self._loaded_consent = consent
        self.loaded_sha = model.layer("bundle").sha256

    def _fill_authors(self) -> None:
        table = self.query_one("#identity-authors", DataTable)
        table.clear()
        for index, author in enumerate(self._authors):
            table.add_row(
                bounded(author.get("name", ""), 50),
                author.get("type", "person"),
                bounded(author.get("affiliation", ""), 50),
                author.get("orcid", ""),
                key=str(index),
            )
        section = self.query_one("#identity-authors-section", Collapsible)
        section.title = f"Authors and contributors ({len(self._authors)})"

    # ------------------------------------------------------------ render

    def refresh_page(self, model: WorkspaceModel) -> None:
        bundle = model.layer("bundle")
        stale_notice = self.query_one("#identity-stale", Static)
        if not self._loaded or not self.has_unsaved():
            self._fill(model)
            stale_notice.display = False
        elif bundle.sha256 != self.loaded_sha:
            stale_notice.update(
                plain(
                    "bundle.draft.yaml changed on disk while you were editing. Your "
                    "unsaved values are kept here; Save will ask before replacing "
                    "anything."
                )
            )
            stale_notice.display = True
        issues = model.identity_issues()
        self.query_one("#identity-issues", IssueList).show(
            (item.severity, f"{item.label}: {item.message}") for item in issues
        )
        self._chips(model)
        self._conflicts(model)
        maintainers = bundle.data.get("maintainers") or []
        self.query_one("#identity-maintainer-list", Static).update(
            plain(
                "\n".join(
                    bounded(f"{item.get('name')} {item.get('email') or ''}".strip(), 80)
                    for item in maintainers
                    if isinstance(item, Mapping)
                )
                or "No maintainers are listed. Contacts are never published "
                "unless you approve it here."
            )
        )

    def tag_text(self, model: WorkspaceModel, state: StepState) -> str:
        errors = [item for item in model.identity_issues() if item.error]
        if errors:
            return f"○ {len(errors)} REQUIRED DETAIL(S) TO COMPLETE"
        return super().tag_text(model, state)

    def _chips(self, model: WorkspaceModel) -> None:
        pipeline = model.pipeline()
        imported: dict[str, list[tuple[str, str]]] = {}
        for item in model.imported:
            imported.setdefault(item.field, []).append((item.value, item.source))
        for name, _label in ESSENTIAL:
            value = pipeline.get(name)
            text = str(value) if value is not None else ""
            chip = "missing"
            if name == "engine" and text:
                chip = "default"
            if name == "id" and text:
                try:
                    derived = derive_pipeline_id(str(pipeline.get("name") or ""))
                except PipelineIdError:
                    derived = ""
                chip = "derived from name" if derived == text else "edited"
            elif text:
                sources = [
                    source for found, source in imported.get(name, []) if found == text
                ]
                if sources:
                    chip = "source: " + ", ".join(
                        sorted({_SOURCE_NAMES.get(item, item) for item in sources})
                    )
                elif imported.get(name):
                    chip = "edited by a person"
                elif chip != "default":
                    chip = "entered"
            mark = "✓" if text else "!"
            self.query_one(f"#chip-{name}", Static).update(plain(f"{mark} {chip}"))

    def _conflicts(self, model: WorkspaceModel) -> None:
        holder = self.query_one("#identity-conflicts", Vertical)
        holder.remove_children()
        pipeline = model.pipeline()
        for pointer, choices in sorted(model.conflicts.items()):
            field = pointer.rsplit("/", 1)[-1]
            if pipeline.get(field) not in (None, "", []):
                continue
            card = Card(title=f"Sources disagree: {field}", classes="conflict")
            holder.mount(card)
            card.mount(
                Static(
                    plain(
                        "Choose one, or type your own value above. Alternatives: "
                        + " | ".join(choices)
                    ),
                    classes="muted",
                )
            )
            row = Horizontal(classes="row")
            card.mount(row)
            for index, choice in enumerate(choices[:2]):
                value = choice.rsplit(" (", 1)[0]
                row.mount(
                    Button(
                        f"Use {bounded(value, 40)}",
                        name=f"conflict-{field}-{index}",
                        classes="compact",
                    )
                )
                self._choices[f"conflict-{field}-{index}"] = value

    def focus_target(self, target: Target) -> None:
        field = target.field or "name"
        if field == "authors":
            self.query_one("#identity-authors-section", Collapsible).collapsed = False
            self.query_one("#author-name", Input).focus()
            return
        if field in {"doi", "citation", "licence", "licence_url"}:
            self.query_one("#identity-citation", Collapsible).collapsed = False
            field = "doi" if field == "citation" else field
        if field in {name for name, _label in MORE}:
            self.query_one("#identity-more", Collapsible).collapsed = False
        if field == "maintainers":
            self.query_one("#identity-maintainers", Collapsible).collapsed = False
            self.query_one("#identity-consent").focus()
            return
        if field == "description":
            self.query_one("#identity-description").focus()
            return
        try:
            self.query_one(f"#identity-{field}", Input).focus()
        except Exception:
            self.query_one("#identity-name", Input).focus()

    # ------------------------------------------------------------ actions

    def on_input_changed(self, event: Input.Changed) -> None:
        """Keep a derived ID in step with the name until someone edits it."""
        if event.input.id != "identity-name" or not event.input.has_focus:
            return
        identifier = self.query_one("#identity-id", Input)
        try:
            previous = (
                derive_pipeline_id(self._derived_name) if self._derived_name else ""
            )
            if identifier.value in ("", previous) and event.value.strip():
                identifier.value = derive_pipeline_id(event.value)
                self._derived_name = event.value
        except PipelineIdError:
            return

    def changes(self) -> dict[str, Any]:
        """Changed fields only, as a targeted patch of the draft."""
        if self.model is None:
            return {}
        pipeline = self.model.pipeline()
        current = self.current_values()
        loaded = self._loaded
        changes: dict[str, Any] = {}
        for name, _label in (*ESSENTIAL, *MORE):
            if current[name] == loaded.get(name):
                continue
            if name == "keywords":
                changes[name] = [
                    item.strip() for item in current[name].split(",") if item.strip()
                ]
            else:
                changes[name] = current[name] or None
        for name in ("licence", "licence_url"):
            if current[name] != loaded.get(name):
                changes[name] = current[name] or None
        if current["description"] != loaded.get("description"):
            changes["description"] = current["description"] or None
        if current["doi"] != loaded.get("doi"):
            citation = dict(pipeline.get("citation") or {})
            if current["doi"]:
                citation["doi"] = current["doi"].removeprefix("https://doi.org/")
            else:
                citation.pop("doi", None)
            changes["citation"] = citation or None
        if current["authors"] != loaded.get("authors"):
            changes["authors"] = current["authors"]
        if self.query_one("#identity-consent", Checkbox).value != self._loaded_consent:
            changes["maintainers_publication_approved"] = self.query_one(
                "#identity-consent", Checkbox
            ).value
        return changes

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.name or event.button.id or ""
        if button == "author-add":
            event.stop()
            self._add_author()
        elif button == "author-remove":
            event.stop()
            table = self.query_one("#identity-authors", DataTable)
            if table.row_count:
                index = int(
                    str(
                        table.coordinate_to_cell_key(
                            table.cursor_coordinate
                        ).row_key.value
                    )
                )
                del self._authors[index]
                self._fill_authors()
        elif button.startswith("conflict-"):
            event.stop()
            field = button.removeprefix("conflict-").rsplit("-", 1)[0]
            value = self._choices.get(button, "")
            try:
                self.query_one(f"#identity-{field}", Input).value = value
            except Exception:
                return
            self.say(f"Chose {value} for {field}; Save identity to write it.")
        elif button == "identity-save":
            event.stop()
            self.save()
        elif button == "identity-sources":
            event.stop()
            self.workspace.action_sources()

    def _add_author(self) -> None:
        name = self.query_one("#author-name", Input).value.strip()
        error = self.query_one("#author-error", Static)
        if not name:
            error.update("An author needs a name.")
            self.query_one("#author-name", Input).focus()
            return
        kind = str(self.query_one("#author-type", Select).value)
        author = {"name": name, "type": kind}
        affiliation = self.query_one("#author-affiliation", Input).value.strip()
        if affiliation:
            author["affiliation"] = affiliation
        orcid_text = self.query_one("#author-orcid", Input).value.strip()
        if orcid_text:
            if kind != "person":
                error.update("An ORCID iD identifies a person, not an organisation.")
                return
            orcid = normalise_orcid(orcid_text)
            if orcid is None:
                error.update(
                    "That is not a valid ORCID iD (16 digits with a check digit, "
                    "e.g. 0000-0002-1825-0097)."
                )
                self.query_one("#author-orcid", Input).focus()
                return
            author["orcid"] = orcid
        error.update("")
        self._authors.append(author)
        self._fill_authors()
        for selector in ("#author-name", "#author-affiliation", "#author-orcid"):
            self.query_one(selector, Input).value = ""
        self.say(f"Added {name}; Save identity to write it.")

    def save(self) -> None:
        changes = self.changes()
        if not changes:
            self.say("No identity changes to save.")
            return
        from nf_splice.layers.bundle import set_identity_fields

        def write() -> Any:
            return set_identity_fields(
                self.workspace.repository, changes, self.workspace.change_context()
            )

        def saved(_result: Any) -> None:
            self._loaded = {}
            self.say("Saved identity in .splice-local/drafts/bundle.draft.yaml", "good")

        self.workspace.write(
            "Saving identity",
            write,
            then=saved,
            page=self,
            layer="bundle",
        )

    def selection_label(self) -> str:
        focused = self.app.focused
        if focused is not None and (focused.id or "").startswith("identity-"):
            return (focused.id or "").removeprefix("identity-")
        return ""
