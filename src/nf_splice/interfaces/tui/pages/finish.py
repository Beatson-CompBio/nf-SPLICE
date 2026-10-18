"""Review and Publish.

Review groups what blocks publication by page, with one Fix per group that
opens the exact field, and lists separately what SPLICE ingestion still
needs. Publish shows the validated plan's exact files and writes them only
when the person presses Publish; afterwards it states the four lifecycle
facts apart (ADR-0062): published, structurally valid, classified, ready.
"""

from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from nf_splice.interfaces.tui.model import (
    DEPENDENCIES,
    BlockerGroup,
    BlockerReport,
    Issue,
    PlanView,
    ReadinessView,
    WorkspaceModel,
    blocker_report,
    bounded,
)
from nf_splice.interfaces.tui.navigation import PAGES, StepState, target_for
from nf_splice.interfaces.tui.navigation import page as page_spec
from nf_splice.interfaces.tui.pages.base import PageView
from nf_splice.interfaces.tui.widgets import Card, plain


def _labels(items: tuple[Issue, ...]) -> str:
    seen: list[str] = []
    for item in items:
        label = f"{item.entity} {item.label}".strip() if item.entity else item.label
        if label not in seen:
            seen.append(label)
    text = ", ".join(seen[:3]) + (f" and {len(seen) - 3} more" if len(seen) > 3 else "")
    return text


def group_text(group: BlockerGroup) -> str:
    """What a section needs, root causes first, consequences last."""
    parts = []
    if group.incomplete:
        parts.append(
            f"{len(group.incomplete)} to complete: {_labels(group.incomplete)}"
        )
    if group.errors:
        parts.append(f"{len(group.errors)} to correct: {_labels(group.errors)}")
    if group.cascaded:
        roots = sorted(
            {
                page_spec(target_for(DEPENDENCIES[item.code], "").page).title
                for item in group.cascaded
            }
        )
        parts.append(
            f"{len(group.cascaded)} waiting on {' and '.join(roots)} (resolves with it)"
        )
    if group.warnings and not group.blocking:
        parts.append(f"{len(group.warnings)} warning(s): {_labels(group.warnings)}")
    return "; ".join(parts)


class ReviewPage(PageView):
    page_id = "review"
    help_text = (
        "**Review** lists what still blocks publication, grouped by section: "
        "values still *to complete*, values *to correct*, and errors that only "
        "wait on another section (they resolve with it and are not counted). "
        "Each Fix opens the exact field. Warnings and **ingestion readiness** "
        "never block publication; a bundle is ready for SPLICE ingestion only "
        "when every readiness dimension is.\n\n"
        "Readiness is derived only from the current drafts, never from which "
        "screens you visited."
    )

    def __init__(self) -> None:
        super().__init__()
        self.readiness: ReadinessView | None = None
        self.report: BlockerReport | None = None
        self.groups: dict[str, BlockerGroup] = {}

    def body(self) -> ComposeResult:
        yield Static("", id="review-summary", classes="lead")
        with Card(title="Required before publication", id="review-required"):
            yield Vertical(id="review-groups")
        with Card(title="Warnings · do not block publication", id="review-warnings"):
            yield Static("", id="review-warning-list", classes="muted")
        with Card(
            title="Ingestion readiness · not publication blockers",
            id="review-further",
        ):
            yield Vertical(id="review-readiness")
            yield Button(
                "View readiness details ↗",
                id="review-readiness-details",
                classes="compact",
            )
        with Horizontal(classes="page-actions"):
            yield Button("View full technical report ↗", id="review-report")
            yield Button("Revalidate", id="review-revalidate")
            yield Button("Review publication →", id="review-publish", variant="primary")

    def refresh_page(self, model: WorkspaceModel) -> None:
        report = blocker_report(model)
        self.report = report
        self.groups = {group.page: group for group in report.groups}
        self.query_one("#review-summary", Static).update(
            plain(
                "All drafts validate: review the publication plan next."
                if not report.count
                else report.summary()
            )
        )
        holder = self.query_one("#review-groups", Vertical)
        holder.remove_children()
        if not report.count:
            holder.mount(Static("✓ Nothing blocks publication.", classes="good-text"))
        for group in report.groups:
            if not group.blocking and not group.cascaded:
                continue
            title = page_spec(group.page).title
            glyph = "!" if group.blocking else "…"
            row = Horizontal(classes="review-row")
            actions = Horizontal(classes="review-actions")
            holder.mount(row, actions)
            row.mount(Static(plain(f"{glyph} {title}"), classes="review-group"))
            row.mount(
                Static(plain(bounded(group_text(group), 200)), classes="review-detail")
            )
            if group.blocking:
                actions.mount(
                    Button(
                        f"Fix {title.lower()} →",
                        name=f"review-fix-{group.page}",
                        classes="compact",
                    ),
                    Button(
                        "✧ Propose a fix",
                        name=f"review-ai-{group.page}",
                        classes="compact ai-context",
                    ),
                )
        warnings = [group for group in report.groups if group.warnings]
        self.query_one("#review-warnings").display = bool(warnings)
        self.query_one("#review-warning-list", Static).update(
            plain(
                "\n".join(
                    f"{page_spec(group.page).title}: {_labels(group.warnings)}"
                    for group in warnings
                )
            )
        )
        self.query_one("#review-publish", Button).disabled = not model.drafts_valid
        self._further()
        self.workspace.request_readiness()

    def show_readiness(self, readiness: ReadinessView) -> None:
        self.readiness = readiness
        self._further()

    def _further(self) -> None:
        model = self.model
        if model is None:
            return
        holder = self.query_one("#review-readiness", Vertical)
        holder.remove_children()
        rows: list[tuple[str, str, str]] = []
        readiness = (
            self.readiness
            if self.readiness and self.readiness.key == model.key
            else None
        )
        if readiness is None:
            rows.append(("…", "Output coverage and ingestion readiness", "assessing…"))
        else:
            coverage = readiness.coverage
            status = str(coverage.get("status"))
            rows.append(
                (
                    "✓" if status == "complete" else "ⓘ",
                    "Output coverage",
                    bounded(str(coverage.get("summary")), 100),
                )
            )
        if model.submission_blockers:
            rows.append(
                (
                    "ⓘ",
                    "Job submission",
                    f"{len(model.submission_blockers)} required parameter(s) nobody "
                    "may supply: "
                    + ", ".join(item.name for item in model.submission_blockers[:4]),
                )
            )
        components = model.layer("components").data
        unverified = [
            item
            for item in model.containers
            if not (item.get("distribution") or {}).get("sha256")
        ]
        if components.get("require_downloadable_images") and unverified:
            rows.append(
                (
                    "ⓘ",
                    "Image distribution",
                    f"{len(unverified)} container(s) have no verified "
                    "downloadable image",
                )
            )
        if readiness is not None:
            rows.append(
                (
                    "✓" if readiness.ingestion_ready else "ⓘ",
                    "SPLICE ingestion readiness",
                    bounded(readiness.headline, 100),
                )
            )
        for glyph, label, text in rows:
            row = Horizontal(classes="review-row")
            holder.mount(row)
            row.mount(Static(plain(f"{glyph} {label}"), classes="review-group"))
            row.mount(Static(plain(text), classes="review-detail"))

    def tag_text(self, model: WorkspaceModel, state: StepState) -> str:
        return "✓ READY TO PUBLISH" if model.drafts_valid else "○ NOT READY TO PUBLISH"

    def selection_label(self) -> str:
        focused = self.app.focused
        identifier = getattr(focused, "name", "") or getattr(focused, "id", "") or ""
        for prefix in ("review-fix-", "review-ai-"):
            if identifier.startswith(prefix):
                return page_spec(identifier.removeprefix(prefix)).title
        return ""

    def report_text(self) -> str:
        model = self.model
        if model is None:
            return ""
        lines = []
        for layer in model.layers.values():
            lines.append(f"## {layer.name} ({layer.path})")
            if layer.malformed:
                lines.append(f"  malformed: {layer.malformed}")
            if not layer.issues:
                lines.append("  no issues")
            for item in layer.issues:
                lines.append(
                    f"  {item.severity.upper()} {item.pointer or '/'} "
                    f"[{item.code}] {item.message}"
                )
            lines.append("")
        return "\n".join(lines)

    def readiness_text(self) -> str:
        readiness = self.readiness
        if readiness is None:
            return "Readiness is still being assessed."
        lines = [readiness.headline, ""]
        lines.extend(f"- {item}" for item in readiness.reasons)
        lines.append("")
        lines.append("Output coverage: " + str(readiness.coverage.get("summary")))
        for item in readiness.coverage.get("uncovered") or []:
            lines.append(
                f"  {item['kind']}: {item['instance']} → {', '.join(item['globs'])}"
            )
        lines.append("")
        for name, dimension in readiness.dimensions.items():
            lines.append(f"{name.replace('_', ' ')}: {dimension['status']}")
            lines.extend(f"  blocker: {text}" for text in dimension["blockers"])
            lines.extend(f"  note: {text}" for text in dimension["notes"])
        return "\n".join(lines)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.name or event.button.id or ""
        workspace = self.workspace
        if button.startswith("review-fix-"):
            event.stop()
            group = self.groups.get(button.removeprefix("review-fix-"))
            if group is not None:
                workspace.jump(group.target)
        elif button.startswith("review-ai-"):
            event.stop()
            name = button.removeprefix("review-ai-")
            group = self.groups.get(name)
            items = group.blocking if group is not None else ()
            stage = page_spec(name).stage
            guidance = "Fix these validation issues: " + "; ".join(
                f"{item.pointer or '/'} {item.message}" for item in items[:8]
            )
            if stage:
                workspace.start_assist(stage, guidance)
        elif button == "review-report":
            event.stop()
            workspace.view_text("Full technical report", self.report_text())
        elif button == "review-readiness-details":
            event.stop()
            workspace.view_text("Readiness details", self.readiness_text())
        elif button == "review-revalidate":
            event.stop()
            workspace.action_reload()
        elif button == "review-publish":
            event.stop()
            workspace.show_page("publish")


class PublishPage(PageView):
    page_id = "publish"
    help_text = (
        "**Publish** writes the validated drafts into `splice/` in one atomic "
        "transaction: if anything fails, the previous files are restored. The "
        "list below is the actual plan, recomputed from your drafts.\n\n"
        "Afterwards nf-SPLICE reports four separate facts: published, "
        "structurally valid, scientifically classified and ready for SPLICE "
        "ingestion. Nothing is committed or pushed unless you choose it."
    )

    def __init__(self) -> None:
        super().__init__()
        self.plan: PlanView | None = None
        self.result: list[str] = []

    def body(self) -> ComposeResult:
        yield Static("", id="publish-summary", classes="lead")
        with Card(title="Will write into ./splice/", id="publish-plan"):
            yield Static("", id="publish-files")
            yield Static(
                "Safety: the original pipeline is unchanged · this works on your "
                "local copy · nothing is pushed.",
                classes="muted",
            )
        with Horizontal(classes="page-actions"):
            yield Button("Inspect full diff ↗", id="publish-diff")
            yield Button("← Review outstanding issues", id="publish-back")
            yield Button("Publish bundle", id="publish-go", variant="primary")
        with Card(title="Result", id="publish-result"):
            yield Static("", id="publish-result-text")
            with Horizontal(classes="row"):
                yield Button("View published files ↗", id="publish-files-view")
                yield Button("Export ZIP…", id="publish-export")
                yield Button("Commit locally…", id="publish-commit")
                yield Button("Finish", id="publish-finish")

    def on_mount(self) -> None:
        self.query_one("#publish-result").display = False

    def refresh_page(self, model: WorkspaceModel) -> None:
        if self.plan is None or self.plan.key != model.key:
            self.query_one("#publish-summary", Static).update(
                "Computing the publication plan…"
            )
            self.query_one("#publish-go", Button).disabled = True
            from nf_splice.interfaces.tui.model import build_plan

            self.workspace.run_view(
                "plan", lambda: build_plan(model.repository, model.key), self.show_plan
            )
        else:
            self.show_plan(self.plan)

    def show_plan(self, plan: PlanView) -> None:
        self.plan = plan
        report = blocker_report(self.model) if self.model is not None else None
        if plan.ready:
            summary = (
                "✓ All required contract checks passed. Review the files, then publish."
            )
        elif report is not None and report.count:
            # The same account as Review, so the counts always agree.
            summary = f"{report.summary()} Fix them in Review first."
        else:
            summary = (
                f"Publishing is blocked by {len(plan.blockers)} cross-layer "
                "check(s) the drafts pass individually."
            )
        self.query_one("#publish-summary", Static).update(plain(summary))
        if plan.ready:
            files = "\n".join(
                f"{kind:<10} splice/{path}" for kind, path in plan.changes
            ) or ("No file changes: the published bundle already matches the drafts.")
        elif report is not None and report.count:
            files = "\n".join(
                f"✕ {page_spec(group.page).title}: {group_text(group)}"
                for group in report.blocking_groups
            )
        else:
            files = "\n".join(f"✕ {item}" for item in plan.blockers[:10])
        self.query_one("#publish-files", Static).update(plain(files))
        read_only = (
            bool(self.model and self.model.read_only) or self.workspace.inspect_only
        )
        self.query_one("#publish-go", Button).disabled = not plan.ready or read_only
        self.set_tag(
            "✓ READY TO PUBLISH" if plan.ready else "○ PUBLISH BLOCKED",
            "good" if plan.ready else "warn",
        )

    def tag_text(self, model: WorkspaceModel, state: StepState) -> str:
        return "● PUBLISHED" if state is StepState.PUBLISHED else "○ NOT PUBLISHED"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button = event.button.id or ""
        workspace = self.workspace
        if button == "publish-diff":
            event.stop()
            plan = self.plan
            if plan is None:
                return
            text = "\n\n".join(
                f"### {kind} splice/{path}\n"
                + (plan.diffs.get(path) or "(no textual diff)")
                for kind, path in plan.changes
            )
            workspace.view_text(
                "Publication diff", text or "No changes.", language=None
            )
        elif button == "publish-back":
            event.stop()
            workspace.show_page("review")
        elif button == "publish-go":
            event.stop()
            self.publish()
        elif button == "publish-files-view":
            event.stop()
            files = sorted(
                path.relative_to(workspace.repository).as_posix()
                for path in (workspace.repository / "splice").rglob("*")
                if path.is_file()
            )
            workspace.view_text("Published files", "\n".join(files[:2000]))
        elif button == "publish-export":
            event.stop()
            workspace.export_bundle()
        elif button == "publish-commit":
            event.stop()
            workspace.commit_bundle()
        elif button == "publish-finish":
            event.stop()
            workspace.show_page("review")

    def publish(self) -> None:
        plan = self.plan
        if plan is None or not plan.ready:
            self.say("The plan is not ready to publish.", "warn")
            return
        from nf_splice.interfaces.tui.modals import ConfirmDialog
        from nf_splice.services.lifecycle import promote

        root = self.workspace.repository

        def run(replace: bool) -> None:
            def published(result: Any) -> None:
                wrote = list(getattr(result, "wrote", ()) or ())
                self.result = wrote
                self.query_one("#publish-result").display = True
                self.query_one("#publish-result-text", Static).update(
                    plain(
                        (
                            f"Published ✓ {len(wrote)} file(s) written:\n"
                            if wrote
                            else "Published ✓ no file changed.\n"
                        )
                        + "\n".join(f"  splice/{item}" for item in wrote[:20])
                        + "\nChecking the published bundle…"
                    )
                )
                self.workspace.request_readiness(force=True)
                self.say("Published the bundle into splice/.", "good")

            self.workspace.write(
                "Publishing the bundle",
                lambda: promote(
                    root,
                    None,
                    self.workspace.change_context(),
                    replace_existing=replace,
                ),
                then=published,
                page=self,
                layer=None,
            )

        if plan.replaces_existing:
            changed = [
                path
                for kind, path in plan.changes
                if kind not in {"create", "unchanged"}
            ]

            def confirmed(result: Any) -> None:
                if result:
                    run(True)

            self.app.push_screen(
                ConfirmDialog(
                    "Replace published files?",
                    f"{len(changed)} file(s) already in splice/ will be replaced: "
                    + ", ".join(changed[:6])
                    + (" …" if len(changed) > 6 else "")
                    + ". Inspect the full diff first if you have not. The previous "
                    "files are restored if publishing fails.",
                    confirm="Replace and publish",
                    danger=True,
                ),
                confirmed,
            )
        else:
            run(False)

    def show_readiness(self, readiness: ReadinessView) -> None:
        if not self.query_one("#publish-result").display:
            return
        wrote = self.result
        lines = [
            (
                f"Published ✓ {len(wrote)} file(s) written"
                if wrote
                else "Published ✓ (no file changed)"
            ),
            f"Structural validation {'✓' if readiness.structurally_valid else '✕'}",
            "Scientific classification "
            + ("✓ assessed" if readiness.classified else "✕ not established"),
            "SPLICE ingestion readiness "
            + ("✓ ready" if readiness.ingestion_ready else "○ not ready"),
            "",
            readiness.headline,
            *(f"  - {item}" for item in readiness.reasons[:12]),
        ]
        self.query_one("#publish-result-text", Static).update(plain("\n".join(lines)))


PAGE_ORDER = tuple(item.id for item in PAGES)
