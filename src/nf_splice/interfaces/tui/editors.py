"""Focused editors: the two-step output form and the profile chooser.

Each editor returns plain values; the page writes them through the shared
layer services, so a form never becomes a second source of truth.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.suggester import SuggestFromList
from textual.widgets import (
    Button,
    ContentSwitcher,
    Input,
    Label,
    RadioButton,
    RadioSet,
    Select,
    Static,
    TextArea,
)

from nf_splice.domain import OutputFormat
from nf_splice.interfaces.tui.modals import Dialog
from nf_splice.interfaces.tui.patterns import (
    KINDS,
    LITERAL,
    Part,
    build_pattern,
    check_pattern,
    key_from_title,
    matches,
    scope_problem,
    split_example,
)
from nf_splice.interfaces.tui.widgets import plain

_KEY_RULE = "lower-case letters, digits and _; starts with a letter"


class OutputEditor(Dialog):
    """Add, edit or duplicate one output in two short steps."""

    def __init__(
        self,
        *,
        initial: Mapping[str, Any] | None = None,
        mode: str = "add",
        existing_keys: Sequence[str] = (),
        categories: Sequence[str] = (),
        example: str = "",
    ) -> None:
        super().__init__()
        self._initial = dict(initial or {})
        self._mode = mode
        self._original_key = str(self._initial.get("key") or "")
        self._existing = {item for item in existing_keys if item != self._original_key}
        self._categories = sorted({item for item in categories if item})
        self._example = example
        self._key_edited = mode == "edit"
        self._parts: list[Part] = []
        self._advanced = False

    # ------------------------------------------------------------ layout

    def compose(self) -> ComposeResult:
        data = self._initial
        title = {
            "add": "Add output",
            "edit": "Edit output",
            "duplicate": "Duplicate output",
        }[self._mode]
        with Vertical(classes="dialog dialog-wide", id="output-editor"):
            yield Static(title, classes="dialog-title")
            yield Static(
                "STEP 1 OF 2 · WHAT IS PRODUCED?", id="editor-step", classes="muted"
            )
            with ContentSwitcher(initial="editor-what", id="editor-steps"):
                with VerticalScroll(id="editor-what"):
                    yield Label("Title *", classes="field-label")
                    yield Input(
                        str(data.get("title") or ""),
                        placeholder="e.g. Gene counts",
                        id="output-title",
                    )
                    yield Label(
                        "Stable key *  (generated from the title; editable)",
                        classes="field-label",
                    )
                    yield Input(
                        "" if self._mode == "duplicate" else str(data.get("key") or ""),
                        placeholder="gene_counts",
                        id="output-key",
                    )
                    yield Static("", id="error-key", classes="field-error")
                    yield Label(
                        "Description *  (what it contains scientifically)",
                        classes="field-label",
                    )
                    yield TextArea(
                        str(data.get("description") or ""), id="output-description"
                    )
                    yield Label(
                        "Category *  (your own label; reuse an existing one)",
                        classes="field-label",
                    )
                    yield Input(
                        str(data.get("category") or ""),
                        placeholder="quantification",
                        id="output-category",
                        suggester=SuggestFromList(self._categories)
                        if self._categories
                        else None,
                    )
                    yield Label(
                        "Format(s) *  (comma-separated, e.g. tsv or bam, bai)",
                        classes="field-label",
                    )
                    yield Input(
                        ", ".join(str(item) for item in data.get("formats") or []),
                        placeholder="tsv",
                        id="output-formats",
                        suggester=SuggestFromList(
                            [item.value for item in OutputFormat]
                        ),
                    )
                    yield Label("Applies to *", classes="field-label")
                    scope = (list(data.get("scopes") or []) or ["job"])[0]
                    with RadioSet(id="output-scope"):
                        yield RadioButton(
                            "Whole job (one per run of the pipeline)",
                            value=scope == "job",
                            id="scope-job",
                        )
                        yield RadioButton(
                            "One sample", value=scope == "sample", id="scope-sample"
                        )
                        yield RadioButton(
                            "One run (a platform file-level unit)",
                            value=scope == "run",
                            id="scope-run",
                        )
                    yield Label("Represents *", classes="field-label")
                    entity = (list(data.get("entity_types") or []) or ["file"])[0]
                    with RadioSet(id="output-entity"):
                        yield RadioButton(
                            "A file", value=entity == "file", id="entity-file"
                        )
                        yield RadioButton(
                            "A directory",
                            value=entity == "directory",
                            id="entity-directory",
                        )
                    yield Static("", id="error-what", classes="field-error")
                with VerticalScroll(id="editor-where"):
                    yield Label(
                        "Example relative path (as published in the output directory)",
                        classes="field-label",
                    )
                    with Horizontal(classes="row"):
                        yield Input(
                            self._example,
                            placeholder="quantification/SAMPLE1/counts.tsv",
                            id="output-example",
                        )
                        yield Button(
                            "Use this example", id="editor-split", classes="compact"
                        )
                    yield Static(
                        "Say where the path varies; every part is fixed text "
                        "until you change it.",
                        classes="muted",
                    )
                    yield Vertical(id="editor-parts")
                    yield Label("Path pattern *", classes="field-label")
                    with Horizontal(classes="row"):
                        yield Input(
                            "\n".join(data.get("path_patterns") or [])[:0]
                            or (str((data.get("path_patterns") or [""])[0])),
                            id="output-pattern",
                        )
                        yield Button(
                            "Advanced", id="editor-advanced", classes="compact"
                        )
                    yield Label(
                        "More patterns (advanced, one per line)",
                        classes="field-label",
                        id="label-extra",
                    )
                    yield TextArea(
                        "\n".join(
                            str(item) for item in (data.get("path_patterns") or [])[1:]
                        ),
                        id="output-extra-patterns",
                    )
                    yield Static("", id="editor-match")
                    yield Static("", id="editor-summary", classes="muted")
                    yield Static("", id="error-where", classes="field-error")
            with Horizontal(classes="dialog-actions"):
                yield Button("Cancel", id="editor-cancel")
                yield Button("← Back", id="editor-back")
                yield Button("Next: location →", id="editor-next", variant="primary")
                yield Button("Save output", id="editor-save", variant="primary")

    def on_mount(self) -> None:
        self._show_step(1)
        extra = self.query_one("#output-extra-patterns", TextArea)
        has_extra = bool(extra.text.strip())
        extra.display = has_extra
        self.query_one("#label-extra").display = has_extra
        pattern = self.query_one("#output-pattern", Input)
        pattern.disabled = not bool(pattern.value)
        self._advanced = bool(pattern.value)
        if self._example:
            self._split()
        self.query_one("#output-title", Input).focus()

    def _show_step(self, step: int) -> None:
        self.query_one("#editor-steps", ContentSwitcher).current = (
            "editor-what" if step == 1 else "editor-where"
        )
        self.query_one("#editor-step", Static).update(
            "STEP 1 OF 2 · WHAT IS PRODUCED?"
            if step == 1
            else "STEP 2 OF 2 · WHERE DOES IT APPEAR?"
        )
        self.query_one("#editor-back").display = step == 2
        self.query_one("#editor-next").display = step == 1
        self.query_one("#editor-save").display = step == 2
        if step == 2:
            self._refresh_where()

    # ------------------------------------------------------------ step 1

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "output-title" and not self._key_edited:
            self.query_one("#output-key", Input).value = key_from_title(event.value)
        elif event.input.id == "output-key" and event.input.has_focus:
            self._key_edited = True
        elif event.input.id == "output-pattern":
            self._refresh_where()

    def _radio(self, selector: str, prefix: str) -> str:
        pressed = self.query_one(selector, RadioSet).pressed_button
        return (pressed.id or "").removeprefix(prefix) if pressed else ""

    def what(self) -> dict[str, Any]:
        return {
            "key": self.query_one("#output-key", Input).value.strip(),
            "title": self.query_one("#output-title", Input).value.strip(),
            "description": self.query_one("#output-description", TextArea).text.strip(),
            "category": self.query_one("#output-category", Input).value.strip(),
            "formats": [
                item.strip().lower()
                for item in self.query_one("#output-formats", Input).value.split(",")
                if item.strip()
            ],
            "scopes": [self._radio("#output-scope", "scope-") or "job"],
            "entity_types": [self._radio("#output-entity", "entity-") or "file"],
        }

    def _check_what(self) -> bool:
        values = self.what()
        missing = [
            label
            for name, label in (
                ("title", "title"),
                ("key", "stable key"),
                ("description", "description"),
                ("category", "category"),
                ("formats", "format"),
            )
            if not values[name]
        ]
        key_error = ""
        import re

        if values["key"] and not re.fullmatch(r"[a-z][a-z0-9_]*", values["key"]):
            key_error = f"The key must use {_KEY_RULE}."
        elif values["key"] in self._existing:
            key_error = f"Another output already uses the key {values['key']!r}."
        bad_formats = [
            item
            for item in values["formats"]
            if not re.fullmatch(r"[a-z0-9][a-z0-9._+-]*", item)
        ]
        self.query_one("#error-key", Static).update(plain(key_error))
        problems = []
        if missing:
            problems.append("Complete: " + ", ".join(missing) + ".")
        if bad_formats:
            problems.append(
                "Formats are lower-case names such as tsv or ome-tiff: "
                + ", ".join(bad_formats)
            )
        self.query_one("#error-what", Static).update(plain(" ".join(problems)))
        if key_error:
            self.query_one("#output-key", Input).focus()
        elif missing:
            first = {
                "title": "#output-title",
                "stable key": "#output-key",
                "description": "#output-description",
                "category": "#output-category",
                "format": "#output-formats",
            }[missing[0]]
            self.query_one(first).focus()
        return not (missing or key_error or bad_formats)

    # ------------------------------------------------------------ step 2

    def _split(self) -> None:
        example = self.query_one("#output-example", Input).value
        self._parts = [Part(text) for text in split_example(example)]
        holder = self.query_one("#editor-parts", Vertical)
        holder.remove_children()
        for index, part in enumerate(self._parts):
            row = Horizontal(classes="part-row")
            holder.mount(row)
            row.mount(Static(plain(part.text), classes="part-text"))
            row.mount(
                Select(
                    [(label, kind) for kind, label in KINDS],
                    value=LITERAL,
                    allow_blank=False,
                    name=f"part-{index}",
                    classes="part-kind",
                )
            )
        self._advanced = False
        self.query_one("#output-pattern", Input).disabled = True
        self._rebuild()

    def on_select_changed(self, event: Select.Changed) -> None:
        identifier = event.select.name or ""
        if identifier.startswith("part-") and self._parts:
            index = int(identifier.removeprefix("part-"))
            if index < len(self._parts):
                self._parts[index] = Part(self._parts[index].text, str(event.value))
                self._rebuild()

    def _rebuild(self) -> None:
        if self._advanced or not self._parts:
            self._refresh_where()
            return
        try:
            pattern = build_pattern(self._parts)
        except ValueError as error:
            self.query_one("#error-where", Static).update(plain(str(error)))
            return
        self.query_one("#output-pattern", Input).value = pattern
        self._refresh_where()

    def patterns(self) -> list[str]:
        first = self.query_one("#output-pattern", Input).value.strip()
        extra = [
            line.strip()
            for line in self.query_one(
                "#output-extra-patterns", TextArea
            ).text.splitlines()
            if line.strip()
        ]
        return [item for item in [first, *extra] if item]

    def _refresh_where(self) -> None:
        patterns = self.patterns()
        example = self.query_one("#output-example", Input).value.strip().strip("/")
        lines = []
        for pattern in patterns:
            problem = check_pattern(pattern)
            if problem:
                lines.append(f"✕ {pattern}: {problem}")
            elif example:
                hit = matches(pattern, [example])
                lines.append(
                    f"✓ matches {example}" if hit else f"✕ does not match {example}"
                )
        self.query_one("#editor-match", Static).update(plain("\n".join(lines)))
        values = self.what()
        self.query_one("#editor-summary", Static).update(
            plain(
                f"Summary: {values['title'] or '(untitled)'} · "
                f"{', '.join(values['formats']) or '?'} · {values['scopes'][0]} · "
                f"{values['entity_types'][0]}"
            )
        )

    def _check_where(self) -> bool:
        patterns = self.patterns()
        problem = None
        if not patterns:
            problem = "Give the path where it is published (an example, or a pattern)."
        for pattern in patterns:
            problem = problem or check_pattern(pattern)
        values = self.what()
        problem = problem or scope_problem(values["scopes"][0], patterns)
        self.query_one("#error-where", Static).update(plain(problem or ""))
        if problem:
            self.query_one("#output-example", Input).focus()
        return problem is None

    # ------------------------------------------------------------ actions

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        button = event.button.id
        if button == "editor-cancel":
            self.dismiss(None)
        elif button == "editor-next":
            if self._check_what():
                self._show_step(2)
                self.query_one("#output-example", Input).focus()
        elif button == "editor-back":
            self._show_step(1)
        elif button == "editor-split":
            self._split()
        elif button == "editor-advanced":
            self._advanced = True
            pattern = self.query_one("#output-pattern", Input)
            pattern.disabled = False
            pattern.focus()
            extra = self.query_one("#output-extra-patterns", TextArea)
            extra.display = True
            self.query_one("#label-extra").display = True
        elif button == "editor-save":
            if not self._check_what():
                self._show_step(1)
                return
            if not self._check_where():
                return
            output = self.what() | {"path_patterns": self.patterns()}
            for name in ("stage", "labels"):
                if self._initial.get(name) and self._mode != "add":
                    output[name] = self._initial[name]
            self.dismiss(output)


class ProfileChooser(Dialog):
    """Add a profile: what each choice writes, before anything is written."""

    def __init__(self, repository_configs: Sequence[str]) -> None:
        super().__init__()
        self._configs = list(repository_configs)

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static("Add an execution profile", classes="dialog-title")
            yield Static(
                "Local and Slurm create a private native Nextflow config under "
                ".splice-local/drafts/configs/ from a scaffold: review it before "
                "relying on it; nf-SPLICE never invents accounts, queues or paths "
                "from this computer. Adopt references a config already in the "
                "repository, unchanged. Nothing in the pipeline is modified.",
                classes="dialog-text",
            )
            yield Label("Name *", classes="field-label")
            yield Input(placeholder="e.g. Local workstation", id="profile-name")
            yield Label("Description *", classes="field-label")
            yield Input(
                placeholder="Where and how this profile runs", id="profile-description"
            )
            yield Label("Kind", classes="field-label")
            with RadioSet(id="profile-kind"):
                yield RadioButton(
                    "Local: run on one machine", value=True, id="kind-local"
                )
                yield RadioButton("Slurm: submit to a Slurm cluster", id="kind-slurm")
                yield RadioButton(
                    "Adopt an existing repository config",
                    id="kind-adopt",
                    disabled=not self._configs,
                )
            yield Label("Repository config to adopt", classes="field-label")
            yield Select(
                [(item, item) for item in self._configs],
                prompt="(none found)" if not self._configs else "choose a config",
                id="profile-config",
                disabled=not self._configs,
            )
            yield Label("What is it for? *", classes="field-label")
            yield Select(
                [
                    ("Development: trying the pipeline", "development"),
                    ("Production: real analyses", "production"),
                    ("Test: automated checks", "test"),
                ],
                id="profile-type",
            )
            yield Label("Container engine", classes="field-label")
            yield Select(
                [
                    ("Singularity", "singularity"),
                    ("Apptainer", "apptainer"),
                    ("Docker", "docker"),
                    ("Conda", "conda"),
                ],
                value="singularity",
                allow_blank=False,
                id="profile-engine",
            )
            yield Static("", id="profile-error", classes="field-error")
            with Horizontal(classes="dialog-actions"):
                yield Button("Cancel", id="profile-cancel")
                yield Button("Create profile", id="profile-create", variant="primary")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        event.stop()
        if event.button.id != "profile-create":
            self.dismiss(None)
            return
        name = self.query_one("#profile-name", Input).value.strip()
        description = self.query_one("#profile-description", Input).value.strip()
        pressed = self.query_one("#profile-kind", RadioSet).pressed_button
        kind = (
            (pressed.id or "kind-local").removeprefix("kind-") if pressed else "local"
        )
        config = self.query_one("#profile-config", Select).value
        purpose = self.query_one("#profile-type", Select).value
        error = ""
        if not name or not description:
            error = "Give the profile a name and a description."
        elif purpose is Select.NULL:
            error = "Say what the profile is for."
        elif kind == "adopt" and config is Select.NULL:
            error = "Choose the repository config to adopt."
        if error:
            self.query_one("#profile-error", Static).update(plain(error))
            return
        self.dismiss(
            {
                "name": name,
                "description": description,
                "kind": kind,
                "config": None if config is Select.NULL else str(config),
                "type": str(purpose),
                "engine": str(self.query_one("#profile-engine", Select).value),
            }
        )
