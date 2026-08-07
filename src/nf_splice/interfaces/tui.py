"""Textual application shell over a shared workspace snapshot."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.coordinate import Coordinate
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    ListItem,
    ListView,
    Select,
    Static,
)

from nf_splice.domain import (
    EnvironmentUse,
    InputClassification,
    OutputCategory,
    OutputEntityType,
    OutputFormat,
    OutputScope,
    OutputStage,
    ReviewedAuthor,
    ReviewedOutput,
)
from nf_splice.services import (
    ApplicationService,
    AuthoringOperationError,
    LayerSummary,
    OutputReviewError,
    WorkspaceSnapshot,
    load_repository_document,
    merge_outputs,
    split_output,
    unresolved_component_candidates,
    unresolved_execution_profiles,
    unresolved_input_candidates,
    unresolved_output_candidates,
    unresolved_provenance_candidates,
)


def _display_name(value: str) -> str:
    return value.replace("_", " ").title()


class NfSpliceApp(App[None]):
    """Navigable workspace over shared inspection and review services."""

    TITLE = "nf-splice"
    SUB_TITLE = "SPLICE integration workspace"
    CSS = """
    #repository { height: auto; padding: 1 2; background: $primary-background; }
    #workspace { height: 1fr; }
    #layers { width: 30; border-right: solid $primary; }
    #details { width: 1fr; padding: 1 2; }
    #candidate-table { height: 10; margin-bottom: 1; }
    #input-table, #component-table, #profile-table, #provenance-table {
        height: 8; margin-bottom: 1;
    }
    #review-form { height: auto; display: none; border: solid $primary; padding: 1; }
    #review-form Input, #review-form Select { margin-bottom: 1; }
    #review-actions { height: auto; }
    .section { margin-bottom: 1; }
    .heading { text-style: bold; color: $accent; }
    """

    def __init__(
        self,
        snapshot: WorkspaceSnapshot,
        repository_root: str | Path | None = None,
        service: ApplicationService | None = None,
    ) -> None:
        super().__init__()
        self.snapshot = snapshot
        self.repository_root = (
            Path(repository_root).resolve() if repository_root is not None else None
        )
        self.service = service or ApplicationService()
        self._candidate_ids: list[str] = []
        self._input_candidate_ids: list[str] = []
        self._component_candidate_ids: list[str] = []
        self._profile_candidate_ids: list[str] = []
        self._provenance_candidate_ids: list[str] = []

    def compose(self) -> ComposeResult:
        """Compose a summary with keyboard-navigable integration layers."""
        inspection = self.snapshot.inspection
        revision = inspection.repository_revision or "not detected"
        yield Header()
        yield Static(
            f"Repository: {inspection.root}\n"
            f"Revision: {revision}\n"
            f"SPLICE tree: {inspection.splice_tree.state.value}\n"
            f"Evidence: {len(inspection.evidence)}",
            id="repository",
        )
        with Horizontal(id="workspace"):
            yield ListView(
                *(
                    ListItem(Label(_display_name(layer.name)))
                    for layer in self.snapshot.layers
                ),
                id="layers",
            )
            with VerticalScroll(id="details"):
                yield Static("Integration status", classes="heading")
                yield Static(
                    self._integration_text(), id="integration", classes="section"
                )
                yield Static("Selected layer", classes="heading")
                yield Static("", id="layer-detail", classes="section")
                yield Static("Warnings", classes="heading")
                yield Static(self._warnings_text(), id="warnings", classes="section")
                with Horizontal(id="migration-actions"):
                    yield Button("Preview legacy migration", id="preview-migration")
                    yield Button(
                        "Apply legacy migration",
                        id="apply-migration",
                        variant="warning",
                    )
                yield Static("", id="migration-summary", classes="section")
                yield Static("Evidence", classes="heading")
                yield Static(self._evidence_text(), id="evidence", classes="section")
                yield Static("Output review", classes="heading")
                yield DataTable(id="candidate-table")
                with VerticalScroll(id="review-form"):
                    yield Static("", id="candidate-evidence", classes="section")
                    yield Input(placeholder="Stable key", id="output-key")
                    yield Input(placeholder="Title", id="output-title")
                    yield Input(placeholder="Description", id="output-description")
                    yield Select(
                        [
                            (item.value.replace("_", " ").title(), item.value)
                            for item in OutputCategory
                        ],
                        prompt="Category",
                        id="output-category",
                    )
                    yield Select(
                        [(item.value, item.value) for item in OutputFormat],
                        prompt="Format",
                        id="output-format",
                    )
                    yield Select(
                        [(item.value, item.value) for item in OutputScope],
                        prompt="Scope",
                        id="output-scope",
                    )
                    yield Select(
                        [(item.value, item.value) for item in OutputEntityType],
                        prompt="Entity type",
                        id="output-entity",
                    )
                    yield Select(
                        [(item.value, item.value) for item in OutputStage],
                        prompt="Optional pipeline stage",
                        id="output-stage",
                    )
                    yield Input(
                        placeholder="Anchored path pattern", id="output-pattern"
                    )
                    yield Input(
                        placeholder="Optional labels as name=value pairs",
                        id="output-labels",
                    )
                    yield Input(
                        placeholder="Reject reason / merge candidate IDs",
                        id="review-detail",
                    )
                    with Horizontal(id="review-actions"):
                        yield Button("Preview", id="preview-output", variant="primary")
                        yield Button("Accept", id="accept-output", variant="success")
                        yield Button("Reject", id="reject-output", variant="error")
                        yield Button("Merge", id="merge-output")
                        yield Button("Split patterns", id="split-output")
                    yield Static("", id="review-summary", classes="section")
                yield Static("Input review", classes="heading")
                yield DataTable(id="input-table")
                with VerticalScroll(id="input-review-form"):
                    yield Select(
                        [
                            (_display_name(item.value), item.value)
                            for item in InputClassification
                        ],
                        prompt="Parameter classification",
                        id="input-classification",
                    )
                    yield Input(placeholder="Type override", id="input-type")
                    yield Input(
                        placeholder="Description override", id="input-description"
                    )
                    yield Button(
                        "Save input classification",
                        id="save-input",
                        variant="success",
                    )
                yield Static("Component review", classes="heading")
                yield DataTable(id="component-table")
                with VerticalScroll(id="component-review-form"):
                    yield Input(placeholder="Selected version", id="component-version")
                    yield Input(
                        placeholder="Selected container URI", id="component-container"
                    )
                    yield Button(
                        "Accept component", id="accept-component", variant="success"
                    )
                yield Static("Execution profile review", classes="heading")
                yield DataTable(id="profile-table")
                with VerticalScroll(id="profile-review-form"):
                    yield Select(
                        [(item.value.title(), item.value) for item in EnvironmentUse],
                        prompt="Supported use",
                        id="profile-use",
                    )
                    yield Input(
                        placeholder="Support description", id="profile-description"
                    )
                    yield Input(placeholder="Selected executor", id="profile-executor")
                    yield Input(
                        placeholder="Selected container engine", id="profile-engine"
                    )
                    yield Input(
                        placeholder="Comma-separated config sources",
                        id="profile-config-sources",
                    )
                    yield Input(placeholder="Unsupported reason", id="profile-reason")
                    with Horizontal(id="profile-actions"):
                        yield Button(
                            "Select profile", id="select-profile", variant="success"
                        )
                        yield Button(
                            "Reject profile", id="reject-profile", variant="error"
                        )
                yield Static("RO-Crate provenance review", classes="heading")
                yield DataTable(id="provenance-table")
                with VerticalScroll(id="provenance-review-form"):
                    yield Input(
                        placeholder="Comma-separated author names",
                        id="provenance-authors",
                    )
                    yield Input(
                        placeholder="Comma-separated licence identifiers",
                        id="provenance-licenses",
                    )
                    yield Input(
                        placeholder="Publication date (YYYY-MM-DD)",
                        id="provenance-published",
                    )
                    yield Input(
                        placeholder="Source revision (detected if blank)",
                        id="provenance-revision",
                    )
                    yield Button(
                        "Select provenance strategy",
                        id="select-provenance",
                        variant="success",
                    )
        yield Footer()

    def on_mount(self) -> None:
        """Select and focus the first integration layer."""
        layer_list = self.query_one("#layers", ListView)
        layer_list.index = 0
        layer_list.focus()
        self._show_layer(0)
        self._refresh_candidates()
        self._refresh_input_candidates()
        self._refresh_component_candidates()
        self._refresh_profile_candidates()
        self._refresh_provenance_candidates()

    def on_list_view_highlighted(self, event: ListView.Highlighted) -> None:
        """Update layer detail when keyboard navigation changes selection."""
        if event.list_view.id == "layers" and event.list_view.index is not None:
            self._show_layer(event.list_view.index)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Populate the shared review form from the highlighted candidate."""
        if event.data_table.id == "candidate-table":
            self._show_candidate(event.cursor_row)
        elif event.data_table.id == "input-table":
            self._show_input_candidate(event.cursor_row)
        elif event.data_table.id == "component-table":
            self._show_component_candidate(event.cursor_row)
        elif event.data_table.id == "profile-table":
            self._show_profile_candidate(event.cursor_row)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Apply review actions using the same service functions as the CLI."""
        if event.button.id == "save-input":
            self._save_input_review()
            return
        if event.button.id == "accept-component":
            self._save_component_review()
            return
        if event.button.id in {"select-profile", "reject-profile"}:
            self._save_profile_review(reject=event.button.id == "reject-profile")
            return
        if event.button.id == "select-provenance":
            self._save_provenance_review()
            return
        if event.button.id in {"preview-migration", "apply-migration"}:
            if self.repository_root is None:
                self.notify(
                    "No repository is available for migration.", severity="error"
                )
                return
            try:
                result = (
                    self.service.apply_state_migration(self.repository_root)
                    if event.button.id == "apply-migration"
                    else self.service.plan_state_migration(self.repository_root)
                )
            except (OSError, ValueError) as error:
                self.notify(str(error), severity="error", timeout=5)
                return
            lines = [
                f"{item.kind.value}: {item.source.name} -> "
                f"splice/{item.destination.name}"
                for item in result.changes
            ]
            self.query_one("#migration-summary", Static).update(
                "\n".join(lines) if lines else "No legacy state detected."
            )
            if event.button.id == "apply-migration":
                self.snapshot = self.service.inspect(self.repository_root)
                self.query_one("#warnings", Static).update(self._warnings_text())
                self.notify(
                    "Legacy migration applied; source files were preserved."
                    if result.wrote
                    else "Canonical state is already byte-identical."
                )
            else:
                self.notify("Migration preview prepared; no files changed.")
            return
        if event.button.id not in {
            "preview-output",
            "accept-output",
            "reject-output",
            "merge-output",
            "split-output",
        }:
            return
        table = self.query_one("#candidate-table", DataTable)
        if self.repository_root is None or table.cursor_row >= len(self._candidate_ids):
            self.notify("No persisted output candidate is selected.", severity="error")
            return
        candidate_id = self._candidate_ids[table.cursor_row]
        try:
            if event.button.id == "preview-output":
                preview = ReviewedOutput.model_validate(self._reviewed_output())
                self.query_one("#review-summary", Static).update(
                    f"Ready to save {preview.key}: {preview.category.value}; "
                    f"{', '.join(item.value for item in preview.formats)}; "
                    f"{', '.join(preview.path_patterns)}"
                )
                self.notify("Review summary prepared; choose an action to save.")
                return
            if event.button.id == "reject-output":
                reason = self.query_one("#review-detail", Input).value.strip()
                self.service.reject_output(self.repository_root, candidate_id, reason)
            elif event.button.id == "merge-output":
                related = [
                    item.strip()
                    for item in self.query_one("#review-detail", Input).value.split(",")
                    if item.strip()
                ]
                merge_outputs(
                    self.repository_root,
                    list(dict.fromkeys([candidate_id, *related])),
                    self._reviewed_output(),
                )
            elif event.button.id == "split-output":
                split_definition = self._reviewed_output()
                patterns = split_definition["path_patterns"]
                if not isinstance(patterns, list) or len(patterns) < 2:
                    raise OutputReviewError(
                        "Split patterns requires two comma-separated path patterns."
                    )
                split_output(
                    self.repository_root,
                    candidate_id,
                    [
                        {
                            **split_definition,
                            "key": f"{split_definition['key']}_{index}",
                            "path_patterns": [pattern],
                        }
                        for index, pattern in enumerate(patterns, start=1)
                    ],
                )
            else:
                self.service.accept_output(
                    self.repository_root, candidate_id, self._reviewed_output()
                )
        except (OSError, ValueError, AuthoringOperationError) as error:
            self.notify(str(error), severity="error", timeout=5)
            return
        self.notify("Canonical output review saved.")
        self.snapshot = self.service.inspect(self.repository_root)
        self._refresh_candidates()

    def _refresh_input_candidates(self) -> None:
        table = self.query_one("#input-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Parameter", "Group", "Needs review")
        self._input_candidate_ids = []
        if self.repository_root is None:
            self.query_one("#input-review-form").display = False
            return
        try:
            document = load_repository_document(self.repository_root)
        except (OSError, AuthoringOperationError):
            self.query_one("#input-review-form").display = False
            return
        candidates = unresolved_input_candidates(document)
        for candidate in candidates:
            self._input_candidate_ids.append(candidate.id)
            table.add_row(
                candidate.name,
                candidate.group,
                ", ".join(candidate.unresolved_fields),
            )
        self.query_one("#input-review-form").display = bool(candidates)
        if candidates:
            table.cursor_coordinate = Coordinate(0, 0)
            self._show_input_candidate(0)

    def _show_input_candidate(self, row: int) -> None:
        if self.repository_root is None or row >= len(self._input_candidate_ids):
            return
        document = load_repository_document(self.repository_root)
        candidates = {item.id: item for item in unresolved_input_candidates(document)}
        candidate = candidates[self._input_candidate_ids[row]]
        parameter_type = candidate.schema_fragment.get("type")
        description = candidate.schema_fragment.get("description")
        self.query_one("#input-type", Input).value = (
            parameter_type if isinstance(parameter_type, str) else ""
        )
        self.query_one("#input-description", Input).value = (
            description if isinstance(description, str) else ""
        )
        self.query_one("#input-classification", Select).clear()

    def _save_input_review(self) -> None:
        table = self.query_one("#input-table", DataTable)
        if self.repository_root is None or table.cursor_row >= len(
            self._input_candidate_ids
        ):
            self.notify("No input parameter is selected.", severity="error")
            return
        selected = self.query_one("#input-classification", Select).value
        if selected is Select.NULL:
            self.notify("Select an input classification.", severity="error")
            return
        try:
            self.service.review_input(
                self.repository_root,
                self._input_candidate_ids[table.cursor_row],
                str(selected),
                type_override=self.query_one("#input-type", Input).value.strip()
                or None,
                description_override=self.query_one(
                    "#input-description", Input
                ).value.strip()
                or None,
            )
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="error", timeout=5)
            return
        self.snapshot = self.service.inspect(self.repository_root)
        self._refresh_input_candidates()
        self.notify("Canonical input classification saved.")

    def _refresh_component_candidates(self) -> None:
        table = self.query_one("#component-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Component", "Versions", "Containers")
        self._component_candidate_ids = []
        if self.repository_root is None:
            self.query_one("#component-review-form").display = False
            return
        try:
            document = load_repository_document(self.repository_root)
        except (OSError, AuthoringOperationError):
            self.query_one("#component-review-form").display = False
            return
        candidates = unresolved_component_candidates(document)
        for candidate in candidates:
            self._component_candidate_ids.append(candidate.id)
            table.add_row(
                candidate.name,
                ", ".join(candidate.versions) or "not detected",
                str(len(candidate.container_uris)),
            )
        self.query_one("#component-review-form").display = bool(candidates)
        if candidates:
            table.cursor_coordinate = Coordinate(0, 0)
            self._show_component_candidate(0)

    def _show_component_candidate(self, row: int) -> None:
        if self.repository_root is None or row >= len(self._component_candidate_ids):
            return
        document = load_repository_document(self.repository_root)
        candidates = {
            item.id: item for item in unresolved_component_candidates(document)
        }
        candidate = candidates[self._component_candidate_ids[row]]
        self.query_one("#component-version", Input).value = (
            candidate.versions[0] if len(candidate.versions) == 1 else ""
        )
        self.query_one("#component-container", Input).value = (
            candidate.container_uris[0] if len(candidate.container_uris) == 1 else ""
        )

    def _save_component_review(self) -> None:
        table = self.query_one("#component-table", DataTable)
        if self.repository_root is None or table.cursor_row >= len(
            self._component_candidate_ids
        ):
            self.notify("No component is selected.", severity="error")
            return
        try:
            self.service.review_component(
                self.repository_root,
                self._component_candidate_ids[table.cursor_row],
                version=self.query_one("#component-version", Input).value.strip()
                or None,
                container_uri=self.query_one(
                    "#component-container", Input
                ).value.strip()
                or None,
            )
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="error", timeout=5)
            return
        self.snapshot = self.service.inspect(self.repository_root)
        self._refresh_component_candidates()
        self.notify("Canonical component review saved.")

    def _refresh_profile_candidates(self) -> None:
        table = self.query_one("#profile-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Profile", "Executor", "Container", "Config")
        self._profile_candidate_ids = []
        if self.repository_root is None:
            self.query_one("#profile-review-form").display = False
            return
        try:
            document = load_repository_document(self.repository_root)
        except (OSError, AuthoringOperationError):
            self.query_one("#profile-review-form").display = False
            return
        candidates = unresolved_execution_profiles(document)
        for candidate in candidates:
            self._profile_candidate_ids.append(candidate.id)
            table.add_row(
                candidate.name,
                ", ".join(candidate.executors) or "unresolved",
                ", ".join(candidate.container_engines) or "unresolved",
                ", ".join(candidate.config_sources) or "unresolved",
            )
        self.query_one("#profile-review-form").display = bool(candidates)
        if candidates:
            table.cursor_coordinate = Coordinate(0, 0)
            self._show_profile_candidate(0)

    def _show_profile_candidate(self, row: int) -> None:
        if self.repository_root is None or row >= len(self._profile_candidate_ids):
            return
        document = load_repository_document(self.repository_root)
        candidates = {item.id: item for item in unresolved_execution_profiles(document)}
        candidate = candidates[self._profile_candidate_ids[row]]
        self.query_one("#profile-use", Select).clear()
        self.query_one("#profile-description", Input).value = ""
        self.query_one("#profile-executor", Input).value = (
            candidate.executors[0] if len(candidate.executors) == 1 else ""
        )
        self.query_one("#profile-engine", Input).value = (
            candidate.container_engines[0]
            if len(candidate.container_engines) == 1
            else ""
        )
        self.query_one("#profile-config-sources", Input).value = ",".join(
            candidate.config_sources
        )
        self.query_one("#profile-reason", Input).value = ""

    def _save_profile_review(self, *, reject: bool) -> None:
        table = self.query_one("#profile-table", DataTable)
        if self.repository_root is None or table.cursor_row >= len(
            self._profile_candidate_ids
        ):
            self.notify("No execution profile is selected.", severity="error")
            return
        candidate_id = self._profile_candidate_ids[table.cursor_row]
        try:
            if reject:
                self.service.reject_execution_profile(
                    self.repository_root,
                    candidate_id,
                    self.query_one("#profile-reason", Input).value.strip(),
                )
            else:
                selected_use = self.query_one("#profile-use", Select).value
                if selected_use is Select.NULL:
                    raise ValueError("Select a supported profile use.")
                sources = tuple(
                    item.strip()
                    for item in self.query_one(
                        "#profile-config-sources", Input
                    ).value.split(",")
                    if item.strip()
                )
                self.service.review_execution_profile(
                    self.repository_root,
                    candidate_id,
                    use=str(selected_use),
                    description=self.query_one(
                        "#profile-description", Input
                    ).value.strip(),
                    executor=self.query_one("#profile-executor", Input).value.strip()
                    or None,
                    container_engine=self.query_one(
                        "#profile-engine", Input
                    ).value.strip()
                    or None,
                    config_sources=sources,
                )
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="error", timeout=5)
            return
        self.snapshot = self.service.inspect(self.repository_root)
        self._refresh_profile_candidates()
        self.notify("Canonical execution-profile review saved.")

    def _refresh_provenance_candidates(self) -> None:
        table = self.query_one("#provenance-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Strategy", "Source")
        self._provenance_candidate_ids = []
        if self.repository_root is None:
            self.query_one("#provenance-review-form").display = False
            return
        try:
            document = load_repository_document(self.repository_root)
        except (OSError, AuthoringOperationError):
            self.query_one("#provenance-review-form").display = False
            return
        candidates = unresolved_provenance_candidates(document)
        for candidate in candidates:
            self._provenance_candidate_ids.append(candidate.id)
            table.add_row(
                _display_name(candidate.strategy.value),
                candidate.source_path or "built-in renderer",
            )
        self.query_one("#provenance-review-form").display = bool(candidates)
        if candidates:
            table.cursor_coordinate = Coordinate(0, 0)

    def _save_provenance_review(self) -> None:
        table = self.query_one("#provenance-table", DataTable)
        if self.repository_root is None or table.cursor_row >= len(
            self._provenance_candidate_ids
        ):
            self.notify("No provenance strategy is selected.", severity="error")
            return
        authors = tuple(
            ReviewedAuthor(name=item.strip())
            for item in self.query_one("#provenance-authors", Input).value.split(",")
            if item.strip()
        )
        licenses = tuple(
            item.strip()
            for item in self.query_one("#provenance-licenses", Input).value.split(",")
            if item.strip()
        )
        try:
            self.service.review_provenance(
                self.repository_root,
                self._provenance_candidate_ids[table.cursor_row],
                authors=authors,
                licenses=licenses,
                published_at=self.query_one(
                    "#provenance-published", Input
                ).value.strip(),
                source_revision=self.query_one(
                    "#provenance-revision", Input
                ).value.strip()
                or None,
            )
        except (OSError, ValueError) as error:
            self.notify(str(error), severity="error", timeout=5)
            return
        self.snapshot = self.service.inspect(self.repository_root)
        self._refresh_provenance_candidates()
        self.notify("Canonical provenance review saved.")

    def _show_layer(self, index: int) -> None:
        layer = self.snapshot.layers[index]
        self.query_one("#layer-detail", Static).update(self._layer_text(layer))

    def _refresh_candidates(self) -> None:
        table = self.query_one("#candidate-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Key", "Path", "Confidence", "Unresolved")
        self._candidate_ids = []
        if self.repository_root is None:
            self.query_one("#review-form").display = False
            return
        try:
            document = load_repository_document(self.repository_root)
        except (OSError, AuthoringOperationError):
            self.query_one("#review-form").display = False
            return
        candidates = unresolved_output_candidates(document)
        for candidate in candidates:
            self._candidate_ids.append(candidate.id)
            table.add_row(
                candidate.suggested_key,
                candidate.path_pattern or "unresolved",
                f"{candidate.confidence:.2f}",
                ", ".join(candidate.unresolved_fields),
            )
        self.query_one("#review-form").display = bool(candidates)
        self.query_one("#review-summary", Static).update(
            f"{len(candidates)} unresolved output candidate(s)."
        )
        if candidates:
            table.cursor_coordinate = Coordinate(0, 0)
            self._show_candidate(0)

    def _show_candidate(self, row: int) -> None:
        if self.repository_root is None or row >= len(self._candidate_ids):
            return
        document = load_repository_document(self.repository_root)
        candidates = {item.id: item for item in unresolved_output_candidates(document)}
        candidate = candidates[self._candidate_ids[row]]
        evidence = {item.id: item for item in document.evidence}
        decision = next(item for item in document.decisions if item.id == candidate.id)
        details = [
            f"{evidence[item_id].provenance.source}: "
            f"{evidence[item_id].provenance.location}"
            for item_id in decision.evidence_ids
            if item_id in evidence
        ]
        self.query_one("#candidate-evidence", Static).update(
            "\n".join(details) or "No supporting evidence details."
        )
        self.query_one("#output-key", Input).value = candidate.suggested_key
        self.query_one("#output-title", Input).value = candidate.suggested_title or ""
        self.query_one("#output-description", Input).value = (
            candidate.suggested_description or ""
        )
        self.query_one("#output-pattern", Input).value = candidate.path_pattern or ""
        self._set_select(
            "#output-format",
            candidate.suggested_format.value if candidate.suggested_format else None,
        )
        self._set_select(
            "#output-scope",
            candidate.likely_scope.value if candidate.likely_scope else None,
        )
        self._set_select(
            "#output-entity",
            candidate.likely_entity_type.value
            if candidate.likely_entity_type
            else None,
        )
        self._set_select("#output-stage", None)
        self.query_one("#output-labels", Input).value = ""

    def _set_select(self, selector: str, value: str | None) -> None:
        select = self.query_one(selector, Select)
        if value is None:
            select.clear()
        else:
            select.value = value

    def _reviewed_output(self) -> dict[str, Any]:
        def selected(selector: str) -> str:
            value = self.query_one(selector, Select).value
            if value is Select.NULL:
                return ""
            return str(value)

        patterns = [
            item.strip()
            for item in self.query_one("#output-pattern", Input).value.split(",")
            if item.strip()
        ]
        labels = []
        for item in self.query_one("#output-labels", Input).value.split(","):
            name, separator, value = item.partition("=")
            if item.strip() and (
                not separator or not name.strip() or not value.strip()
            ):
                raise OutputReviewError(
                    "labels must use comma-separated name=value pairs"
                )
            if item.strip():
                labels.append({"name": name.strip(), "value": value.strip()})
        output: dict[str, Any] = {
            "key": self.query_one("#output-key", Input).value.strip(),
            "title": self.query_one("#output-title", Input).value.strip(),
            "description": self.query_one("#output-description", Input).value.strip(),
            "category": selected("#output-category"),
            "formats": [selected("#output-format")],
            "scopes": [selected("#output-scope")],
            "entity_types": [selected("#output-entity")],
            "path_patterns": patterns,
            "labels": labels,
        }
        stage = selected("#output-stage")
        if stage:
            output["stage"] = stage
        return output

    def _integration_text(self) -> str:
        unresolved = self.snapshot.authoring.unresolved_decisions
        unresolved_text = "not available" if unresolved is None else str(unresolved)
        return (
            f"Authoring state: {self.snapshot.authoring.state.value}\n"
            f"Unresolved decisions: {unresolved_text}\n"
            f"Build: {self.snapshot.build_status}\n"
            f"Validation: {self.snapshot.validation_status}"
        )

    @staticmethod
    def _layer_text(layer: LayerSummary) -> str:
        unresolved = layer.unresolved_decisions
        unresolved_text = "not available" if unresolved is None else str(unresolved)
        return (
            f"{_display_name(layer.name)}\n"
            f"Status: {layer.status.value}\n"
            f"Decisions: {layer.decision_count}\n"
            f"Unresolved: {unresolved_text}"
        )

    def _warnings_text(self) -> str:
        if not self.snapshot.warnings:
            return "No inspection warnings."
        return "\n".join(f"• {warning}" for warning in self.snapshot.warnings)

    def _evidence_text(self) -> str:
        if not self.snapshot.evidence_counts:
            return "No repository evidence detected."
        return "\n".join(
            f"{_display_name(item.kind.value)}: {item.count}"
            for item in self.snapshot.evidence_counts
        )
