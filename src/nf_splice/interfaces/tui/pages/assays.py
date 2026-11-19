"""Supported assays: tick the assays the pipeline can process.

The tree is the packaged SPLICE vocabulary (modality → subtype → assay type
→ method). Only assays are selectable; organisational parents are not. An
assay that sits under several modalities appears in each branch with one
selection state. Nothing is preselected except what the draft already
declares: nf-SPLICE infers no assay (ADR-0069).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding, BindingType
from textual.containers import Horizontal
from textual.widgets import Button, Input, Static, Tree
from textual.widgets.tree import TreeNode

from nf_splice.catalogue import CatalogueError, ResolvedCapability, default_catalogue
from nf_splice.interfaces.tui.model import WorkspaceModel
from nf_splice.interfaces.tui.navigation import StepState, Target
from nf_splice.interfaces.tui.pages.base import PageView
from nf_splice.interfaces.tui.widgets import Card, IssueList, plain


@dataclass(frozen=True, slots=True)
class NodeData:
    entity_id: str
    label: str
    key: str | None


@lru_cache(maxsize=1)
def vocabulary() -> tuple[ResolvedCapability, ...]:
    """Every assay in the packaged vocabulary (loaded once, in memory)."""
    return tuple(default_catalogue().assays(registered_only=False))


def assay_index() -> dict[str, ResolvedCapability]:
    return {item.key: item for item in vocabulary()}


def declared_keys(entries: Iterable[Any]) -> set[str]:
    catalogue = default_catalogue()
    found = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        try:
            found.add(catalogue.resolve_reference(entry).key)
        except CatalogueError:
            continue
    return found


def _selectable_by_entity() -> dict[str, str]:
    """Assay entity IDs that are themselves selectable, mapped to their key."""
    return {str(item.assay.entity_id): item.key for item in vocabulary()}


class AssaysPage(PageView):
    page_id = "assays"
    form_layer = "bundle"
    help_text = (
        "**Supported assays** are what this pipeline can process across all of "
        "its routes: the pipeline's capability, not one sample's assay.\n\n"
        "**What you decide:** tick every assay it supports, then Save "
        "selections. A tick records your assertion; no essay is needed.\n\n"
        "**Example:** a bulk RNA-seq pipeline might support *poly(A) RNA-seq* "
        "and *Total RNA-seq*. Accepting FASTQ does not by itself establish a "
        "library preparation. Can't find yours? Use Suggest an addition."
    )
    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("space", "toggle_assay", "Tick/untick", show=False)
    ]

    def __init__(self) -> None:
        super().__init__()
        self.saved: set[str] = set()
        self.staged: set[str] = set()
        self.only_selected = False
        self._query = ""
        self._ready = False

    def body(self) -> ComposeResult:
        with Card(title="Find an assay"):
            with Horizontal(classes="row"):
                yield Input(
                    placeholder="Search by label, registered code or entity ID…",
                    id="assay-search",
                )
                yield Button(
                    "Selected (0)", id="assay-only-selected", classes="compact"
                )
            tree: Tree[NodeData] = Tree("SPLICE assay vocabulary", id="assay-tree")
            tree.show_root = False
            yield tree
            yield Static("", id="assay-detail", classes="detail")
        yield Static("", id="assay-summary", classes="notice")
        yield IssueList(id="assay-issues")
        with Horizontal(classes="page-actions"):
            yield Static("Couldn't find your assay?", classes="muted")
            yield Button("Suggest an addition ↗", id="assay-suggest")
            yield Button("Clear all ticks", id="assay-clear")
            yield Button("Save selections", id="assay-save", variant="primary")

    # ------------------------------------------------------------ tree

    def _build_tree(self) -> None:
        tree = self.query_one("#assay-tree", Tree)
        expanded = {
            str(node.data.entity_id)
            + "/"
            + str(
                node.parent.data.entity_id if node.parent and node.parent.data else ""
            )
            for node in self._tree_nodes(tree.root)
            if node.data is not None and node.is_expanded
        }
        tree.clear()
        selectable = _selectable_by_entity()
        query = self._query.lower().strip()
        children: dict[int, dict[str, TreeNode[NodeData]]] = {}
        for item in sorted(vocabulary(), key=lambda entry: entry.assay.label):
            haystack = " ".join(
                [item.assay.label, item.key, str(item.assay.entity_id)]
                + ([item.registration.code] if item.registration else [])
            ).lower()
            if query and query not in haystack:
                continue
            if self.only_selected and item.key not in self.staged:
                continue
            for path in item.paths:
                parent = tree.root
                for entity in reversed(path):
                    group = children.setdefault(id(parent), {})
                    node = group.get(str(entity.entity_id))
                    if node is None:
                        key = selectable.get(str(entity.entity_id))
                        data = NodeData(str(entity.entity_id), entity.label, key)
                        node = parent.add(self._label(data), data=data)
                        node.allow_expand = True
                        group[str(entity.entity_id)] = node
                    parent = node
        for node in self._tree_nodes(tree.root):
            if node.data is None:
                continue
            marker = (
                str(node.data.entity_id)
                + "/"
                + str(
                    node.parent.data.entity_id
                    if node.parent and node.parent.data
                    else ""
                )
            )
            if query or self.only_selected or marker in expanded or not self._ready:
                node.expand()
            if not node.children:
                node.allow_expand = False
        self._ready = True

    def _tree_nodes(self, root: TreeNode[NodeData]) -> Iterable[TreeNode[NodeData]]:
        stack = list(root.children)
        while stack:
            node = stack.pop()
            yield node
            stack.extend(node.children)

    def _label(self, data: NodeData) -> Text:
        if data.key is None:
            return Text(data.label, style="bold")
        tick = "[x]" if data.key in self.staged else "[ ]"
        return Text(f"{tick} {data.label}")

    def _relabel(self) -> None:
        tree = self.query_one("#assay-tree", Tree)
        for node in self._tree_nodes(tree.root):
            if node.data is not None and node.data.key is not None:
                node.set_label(self._label(node.data))
        self._summary()

    def _summary(self) -> None:
        index = assay_index()
        count = len(self.staged)
        self.query_one(
            "#assay-only-selected", Button
        ).label = f"{'All assays' if self.only_selected else f'Selected ({count})'}"
        if count:
            names = ", ".join(
                index[key].assay.label for key in sorted(self.staged) if key in index
            )
            text = f"✓ {count} assay(s) ticked: {names}."
        else:
            text = "No assay is ticked yet. SPLICE ingestion needs at least one."
        if self.staged != self.saved:
            text += "  Unsaved: press Save selections to write them."
        self.query_one("#assay-summary", Static).update(plain(text))

    def _detail(self, data: NodeData | None) -> None:
        widget = self.query_one("#assay-detail", Static)
        if data is None:
            widget.update("")
            return
        if data.key is None:
            widget.update(
                plain(
                    f"{data.label}: a grouping in the vocabulary; tick an assay "
                    "below it."
                )
            )
            return
        item = assay_index().get(data.key)
        if item is None:
            widget.update(plain(data.label))
            return
        paths = [
            " > ".join(entity.label for entity in reversed(path)) for path in item.paths
        ]
        registration = (
            f"registered as {item.registration.code}"
            if item.registration
            else "not registered with the platform yet (declared by entity ID)"
        )
        state = "ticked" if data.key in self.staged else "not ticked"
        widget.update(
            plain(
                f"{item.assay.label} ({registration}; entity {item.assay.entity_id}; "
                f"{state})\n" + "\n".join(f"  in {path}" for path in paths)
            )
        )

    def on_tree_node_highlighted(self, event: Tree.NodeHighlighted[NodeData]) -> None:
        self._detail(event.node.data)

    def on_tree_node_selected(self, event: Tree.NodeSelected[NodeData]) -> None:
        data = event.node.data
        if data is not None and data.key is not None:
            self._toggle(data.key)

    def action_toggle_assay(self) -> None:
        tree = self.query_one("#assay-tree", Tree)
        node = tree.cursor_node
        if node is not None and node.data is not None and node.data.key is not None:
            self._toggle(node.data.key)

    def _toggle(self, key: str) -> None:
        if key in self.staged:
            self.staged.discard(key)
        else:
            self.staged.add(key)
        self._relabel()
        tree = self.query_one("#assay-tree", Tree)
        if tree.cursor_node is not None:
            self._detail(tree.cursor_node.data)

    # ------------------------------------------------------------ model

    def refresh_page(self, model: WorkspaceModel) -> None:
        declared = declared_keys(model.pipeline().get("assay_capabilities") or [])
        if not self._ready or self.staged == self.saved:
            self.staged = set(declared)
        self.saved = declared
        self.loaded_sha = model.layer("bundle").sha256
        if not self._ready:
            self._build_tree()
        self._relabel()
        self.query_one("#assay-issues", IssueList).show(
            (item.severity, item.message) for item in model.assay_issues()
        )

    def tag_text(self, model: WorkspaceModel, state: StepState) -> str:
        return f"{len(self.saved)} SELECTED"

    def has_unsaved(self) -> bool:
        return self.staged != self.saved

    def focus_target(self, target: Target) -> None:
        self.query_one("#assay-tree", Tree).focus()

    def selection_label(self) -> str:
        node = self.query_one("#assay-tree", Tree).cursor_node
        return node.data.label if node is not None and node.data is not None else ""

    # ------------------------------------------------------------ actions

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "assay-search":
            self._query = event.value
            self._build_tree()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.id
        if button == "assay-only-selected":
            event.stop()
            self.only_selected = not self.only_selected
            self._build_tree()
            self._summary()
        elif button == "assay-clear":
            event.stop()
            self.staged.clear()
            self._relabel()
        elif button == "assay-save":
            event.stop()
            self.save()
        elif button == "assay-suggest":
            event.stop()
            self.workspace.suggest_assay()

    def save(self) -> None:
        add = sorted(self.staged - self.saved)
        remove = sorted(self.saved - self.staged)
        if not add and not remove:
            self.say("No assay changes to save.")
            return
        from nf_splice.layers.bundle import (
            add_assay_capability,
            remove_assay_capability,
        )

        root = self.workspace.repository
        context = self.workspace.change_context()

        def write() -> None:
            for key in remove:
                remove_assay_capability(root, key, context)
            for key in add:
                add_assay_capability(root, key, context, evidence="asserted")

        def saved(_result: Any) -> None:
            self.saved = set(self.staged)
            self.say(
                f"Saved assays: {len(add)} added, {len(remove)} removed "
                "(.splice-local/drafts/bundle.draft.yaml)",
                "good",
            )

        self.workspace.write(
            "Saving assays", write, then=saved, page=self, layer="bundle"
        )
