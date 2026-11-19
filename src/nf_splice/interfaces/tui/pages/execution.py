"""Execution: profiles, their native configs and the one default."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Static

from nf_splice.domain.execution import (
    ContainerEngine,
    ExecutionExecutor,
    ExecutionProfileType,
)
from nf_splice.interfaces.tui.model import ProfileRow, WorkspaceModel
from nf_splice.interfaces.tui.navigation import StepState, Target
from nf_splice.interfaces.tui.pages.base import PageView
from nf_splice.interfaces.tui.widgets import Card, IssueList, plain


class ExecutionPage(PageView):
    page_id = "execution"
    form_layer = "execution-profiles"
    help_text = (
        "**Execution profiles** say where SPLICE runs the pipeline. Each names a "
        "native Nextflow config: a private draft in .splice-local/drafts/configs/ "
        "or a repository config adopted unchanged. Exactly one is the default.\n\n"
        "A **starter configuration** was generated from a scaffold, not checked "
        "against a real deployment: review its type and config before relying "
        "on it. Site accounts, queues and paths belong to the deployment and are "
        "never invented.\n\n**Example:** a *Local* development profile with the "
        "local executor and Singularity."
    )

    def __init__(self) -> None:
        super().__init__()
        self.rows: tuple[ProfileRow, ...] = ()

    def body(self) -> ComposeResult:
        with Card(title="Execution profiles"):
            table: DataTable[Any] = DataTable(id="execution-table", cursor_type="row")
            yield table
            yield Static("", id="execution-detail", classes="detail")
            with Horizontal(classes="row"):
                yield Button("Edit profile…", id="execution-edit")
                yield Button("Set as default", id="execution-default")
                yield Button("Open configuration in editor", id="execution-open")
                yield Button("View safe preview", id="execution-preview")
        yield IssueList(id="execution-issues")
        with Card(title="Add a profile"):
            yield Static(
                "Choose Local, Slurm or adopt an existing repository config. A "
                "generated config is a scaffold: nf-SPLICE never claims it is a "
                "validated cluster profile.",
                classes="muted",
            )
            yield Button("+ Add profile…", id="execution-add", variant="primary")

    def on_mount(self) -> None:
        table = self.query_one("#execution-table", DataTable)
        table.add_columns(
            "Default", "Profile", "Type", "Executor", "Containers", "Config", "Status"
        )

    def refresh_page(self, model: WorkspaceModel) -> None:
        self.rows = model.profiles
        self.loaded_sha = model.layer("execution-profiles").sha256
        table = self.query_one("#execution-table", DataTable)
        selected = self.selected()
        table.clear()
        for row in self.rows:
            status = (
                "! Starter configuration · Needs review"
                if row.starter
                else "! " + row.problems[0][:40]
                if row.problems
                else "✓ Ready"
            )
            table.add_row(
                "◉" if row.default else "○",
                f"{row.name} ({row.id})",
                row.type or "not set",
                row.executor,
                row.container_engine,
                Path(row.config).name if row.config else "none",
                status,
                key=row.id,
            )
        if selected and selected in table.rows:
            table.move_cursor(row=table.get_row_index(selected))
        self._detail()
        issues = [
            item
            for item in model.layer("execution-profiles").issues
            if item.code != "identity_not_ready" or not model.layer("bundle").ready
        ]
        self.query_one("#execution-issues", IssueList).show(
            (item.severity, item.message) for item in issues
        )

    def tag_text(self, model: WorkspaceModel, state: StepState) -> str:
        default = next((row.name for row in model.profiles if row.default), "none")
        return f"{len(model.profiles)} PROFILE(S) · DEFAULT: {default}"

    def selected(self) -> str | None:
        table = self.query_one("#execution-table", DataTable)
        if not table.row_count:
            return None
        value = table.coordinate_to_cell_key(table.cursor_coordinate).row_key.value
        return str(value) if value is not None else None

    def _row(self) -> ProfileRow | None:
        key = self.selected()
        return next((row for row in self.rows if row.id == key), None)

    def _detail(self) -> None:
        row = self._row()
        widget = self.query_one("#execution-detail", Static)
        if row is None:
            widget.update("No profile yet: add one below.")
            return
        lines = [
            f"{row.name}: {row.description or 'no description'}",
            f"Executor {row.executor} · containers {row.container_engine} · type "
            f"{row.type or 'not set'}{' · default' if row.default else ''}",
            f"Config: {row.config or 'none'}",
        ]
        if row.starter:
            lines.append(
                "Starter configuration · Needs review: generated from a scaffold, "
                "not a checked deployment. Set its type once you have reviewed it."
            )
        lines.extend(f"! {item}" for item in row.problems[:3])
        widget.update(plain("\n".join(lines)))

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "execution-table":
            self._detail()

    def focus_target(self, target: Target) -> None:
        if target.index is not None and target.index < len(self.rows):
            table = self.query_one("#execution-table", DataTable)
            key = self.rows[target.index].id
            if key in table.rows:
                table.move_cursor(row=table.get_row_index(key))
        self.query_one("#execution-table", DataTable).focus()

    def selection_label(self) -> str:
        row = self._row()
        return row.id if row is not None else ""

    def _config_path(self, row: ProfileRow) -> Path | None:
        from nf_splice.layers.execution import CONFIGS_DIR

        if not row.config:
            return None
        root = self.workspace.repository
        draft = root / CONFIGS_DIR / Path(row.config).name
        if draft.is_file() and row.config.endswith(".draft.config"):
            return draft
        candidate = root / row.config
        return candidate if candidate.is_file() else None

    # ------------------------------------------------------------ actions

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.id or ""
        row = self._row()
        if button == "execution-add":
            event.stop()
            self._add()
            return
        if button not in {
            "execution-edit",
            "execution-default",
            "execution-open",
            "execution-preview",
        }:
            return
        event.stop()
        if row is None:
            self.say("Select a profile first.", "warn")
            return
        if button == "execution-edit":
            self._edit(row)
        elif button == "execution-default":
            from nf_splice.layers.execution import set_default_profile

            self.workspace.write(
                f"Making {row.name} the default profile",
                lambda: set_default_profile(
                    self.workspace.repository, row.id, self.workspace.change_context()
                ),
                then=lambda _r: self.say(
                    f"{row.name} is now the only default profile.", "good"
                ),
                page=self,
                layer="execution-profiles",
            )
        elif button in {"execution-open", "execution-preview"}:
            path = self._config_path(row)
            if path is None:
                self.say("This profile has no readable config yet.", "warn")
                return
            if button == "execution-open":
                self.workspace.edit_file(path)
            else:
                self.workspace.view_file(
                    path.relative_to(self.workspace.repository).as_posix()
                )

    def _edit(self, row: ProfileRow) -> None:
        from nf_splice.interfaces.tui.modals import FormDialog
        from nf_splice.layers.execution import update_profile

        fields = [
            ("name", "Name", row.name),
            ("description", "Description", row.description),
            (
                "type",
                "Type (what this profile is for)",
                (
                    [(item.value, item.value) for item in ExecutionProfileType],
                    row.type or None,
                ),
            ),
            (
                "executor",
                "Executor",
                (
                    [(item.value, item.value) for item in ExecutionExecutor],
                    row.executor or None,
                ),
            ),
            (
                "container_engine",
                "Container engine",
                (
                    [(item.value, item.value) for item in ContainerEngine],
                    row.container_engine or None,
                ),
            ),
        ]

        def done(values: Any) -> None:
            if not values:
                return
            current = {
                "name": row.name,
                "description": row.description,
                "type": row.type or None,
                "executor": row.executor or None,
                "container_engine": row.container_engine or None,
            }
            changes = {
                key: value
                for key, value in values.items()
                if value and value != current.get(key)
            }
            if not changes:
                self.say("No profile changes to save.")
                return
            self.workspace.write(
                f"Saving profile {row.name}",
                lambda: update_profile(
                    self.workspace.repository,
                    row.id,
                    changes,
                    self.workspace.change_context(),
                ),
                then=lambda _r: self.say(f"Saved profile {row.name}.", "good"),
                page=self,
                layer="execution-profiles",
            )

        self.app.push_screen(
            FormDialog(
                f"Edit profile {row.name}",
                "Metadata only: the configuration itself is the native config file "
                "(Open configuration in editor).",
                fields,
            ),
            done,
        )

    def _repository_configs(self) -> list[str]:
        root = self.workspace.repository
        found = []
        for pattern in ("conf/*.config", "*.config", "configs/*.config"):
            for path in sorted(root.glob(pattern)):
                relative = path.relative_to(root).as_posix()
                if path.name not in {"nextflow.config"} and not path.name.startswith(
                    "nf-test"
                ):
                    found.append(relative)
        return found[:200]

    def _add(self) -> None:
        from nf_splice.interfaces.tui.editors import ProfileChooser
        from nf_splice.layers.execution import (
            add_generated_profile,
            profile_id,
            update_profile,
        )

        def done(values: Any) -> None:
            if not values:
                return
            root = self.workspace.repository
            context = self.workspace.change_context()
            kind = values["kind"]

            def write() -> Any:
                result = add_generated_profile(
                    root,
                    context,
                    name=values["name"],
                    description=values["description"],
                    profile_type=values["type"],
                    executor="slurm" if kind == "slurm" else "local",
                    container_engine=values["engine"],
                )
                if kind == "adopt" and values["config"]:
                    result = update_profile(
                        root,
                        profile_id(values["name"]),
                        {"config_adopt": values["config"]},
                        context,
                    )
                return result

            self.workspace.write(
                f"Adding profile {values['name']}",
                write,
                then=lambda _r: self.say(
                    f"Added {values['name']}. Review its config before relying on it.",
                    "good",
                ),
                page=self,
                layer="execution-profiles",
            )

        self.app.push_screen(ProfileChooser(self._repository_configs()), done)
