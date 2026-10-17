"""Shared per-file draft lifecycle: layer registry, issues and review sidecars.

Each layer has exactly one authoritative editable draft below
``.splice-local/drafts/``. A layer's review sidecar
(``.splice-local/reviews/<layer>.review.json``)
records evidence-derived *seeded* values, optional confirmations, advisory
discovery candidates, review events and the hashes of promoted final files.
It is provenance, never authority: it holds no field values, and a
candidate's review status never blocks validation. Readiness is always
derived from the current draft bytes (ADR-0057).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from nf_splice.domain.audit import Actor, ApprovalStatus, ChangeOrigin, ReviewEvent
from nf_splice.drafts import (
    ABSENT,
    DRAFT_MARKER,
    DRAFTS_DIR,
    DraftConflictError,
    DraftSyntaxError,
    PatchOp,
    YamlFileState,
    create_file,
    dump_yaml_data,
    load_yaml_draft,
    patch_yaml,
    read_sidecar,
    read_yaml,
    replace_file,
    resolve,
    sha256,
    text_diff,
    write_sidecar,
)
from nf_splice.layout import legacy_paths
from nf_splice.services.audit import make_event, record_private

SIDECAR_FORMAT = "0.3.0"
DRAFT_FORMAT = "0.3.0"


class Severity(str, Enum):
    """Whether an issue blocks promotion."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class DraftIssue:
    """One actionable, path-addressed draft validation finding."""

    layer: str
    path: str
    pointer: str
    severity: Severity
    code: str
    message: str

    def to_json(self) -> dict[str, str]:
        return {
            "layer": self.layer,
            "path": self.path,
            "pointer": self.pointer,
            "severity": self.severity.value,
            "code": self.code,
            "message": self.message,
        }


class LayerError(ValueError):
    """Raised when a requested layer operation is unsafe or invalid."""


@dataclass(frozen=True, slots=True)
class LayerSpec:
    """Static description of one authoring layer."""

    name: str
    draft: str
    finals: tuple[str, ...]
    title: str


LAYERS: tuple[LayerSpec, ...] = (
    LayerSpec(
        "bundle", f"{DRAFTS_DIR}/bundle.draft.yaml", ("bundle.json",), "Identity"
    ),
    LayerSpec(
        "inputs",
        f"{DRAFTS_DIR}/inputs.draft.yaml",
        ("inputs.schema.json",),
        "Inputs",
    ),
    LayerSpec(
        "outputs",
        f"{DRAFTS_DIR}/outputs.draft.yaml",
        ("outputs.yaml", "outputs.schema.json"),
        "Outputs",
    ),
    LayerSpec(
        "components",
        f"{DRAFTS_DIR}/components.draft.yaml",
        ("components.json",),
        "Components",
    ),
    LayerSpec(
        "execution-profiles",
        f"{DRAFTS_DIR}/execution-profiles.draft.yaml",
        ("execution-profiles.json",),
        "Execution profiles",
    ),
    LayerSpec(
        "provenance",
        f"{DRAFTS_DIR}/provenance.draft.yaml",
        ("ro-crate-metadata.json",),
        "Provenance",
    ),
)


def layer_spec(name: str) -> LayerSpec:
    """Return the layer by name or draft path."""
    for item in LAYERS:
        if name in {item.name, item.draft, item.draft.removeprefix(f"{DRAFTS_DIR}/")}:
            return item
    raise LayerError(f"unknown authoring layer {name!r}")


def draft_marker(layer: str) -> dict[str, str]:
    """Return the machine-readable marker carried by every YAML draft."""
    return {
        "layer": layer,
        "status": "draft",
        "format": DRAFT_FORMAT,
        "note": "Editable nf-SPLICE draft; not for ingestion. Validate and "
        "promote with nf-splice draft validate/promote.",
    }


def value_sha256(value: Any) -> str:
    """Hash a JSON value canonically (key order independent)."""
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()


def strip_marker(data: Mapping[str, Any]) -> dict[str, Any]:
    """Return draft data without draft-only metadata."""
    return {key: value for key, value in data.items() if key != DRAFT_MARKER}


@dataclass(slots=True)
class ReviewState:
    """Mutable working copy of a layer's review sidecar."""

    layer: str
    document: dict[str, Any] = field(default_factory=dict)
    sha256: str | None = None

    def section(self, name: str) -> dict[str, Any]:
        value = self.document.setdefault(name, {})
        if not isinstance(value, dict):
            raise LayerError(f"review sidecar section {name!r} is malformed")
        return value

    @property
    def seeded(self) -> dict[str, Any]:
        return self.section("seeded")

    @property
    def confirmed(self) -> dict[str, Any]:
        return self.section("confirmed")

    @property
    def candidates(self) -> dict[str, Any]:
        return self.section("candidates")

    @property
    def conflicts(self) -> dict[str, Any]:
        return self.section("conflicts")

    @property
    def promoted(self) -> dict[str, Any]:
        return self.section("promoted")

    @property
    def events(self) -> list[Any]:
        value = self.document.setdefault("events", [])
        if not isinstance(value, list):
            raise LayerError("review sidecar events are malformed")
        return value

    def pending(self, data: Any) -> list[str]:
        """Pointers still holding an unconfirmed evidence-derived value."""
        found = []
        for pointer, digest in sorted(self.seeded.items()):
            current = resolve(data, pointer)
            if current is ABSENT or current is None or current in ([], {}):
                continue
            current_digest = value_sha256(current)
            if current_digest != digest:
                continue
            confirmation = self.confirmed.get(pointer)
            if (
                isinstance(confirmation, dict)
                and confirmation.get("sha256") == current_digest
            ):
                continue
            found.append(pointer)
        return found


def load_review_state(root: Path, layer: str) -> ReviewState:
    """Read a layer's sidecar (empty when absent)."""
    document, digest = read_sidecar(root, layer)
    return ReviewState(layer=layer, document=document, sha256=digest)


def save_review_state(root: Path, state: ReviewState) -> None:
    """Persist the sidecar with compare-and-swap protection."""
    state.document["format"] = SIDECAR_FORMAT
    state.document["layer"] = state.layer
    ordered = {key: state.document[key] for key in sorted(state.document)}
    state.sha256 = write_sidecar(
        root, state.layer, ordered, expected_sha256=state.sha256
    )


def update_review_state(
    root: Path, layer: str, mutate: Callable[[ReviewState], None]
) -> ReviewState:
    """Apply a mutation to the current sidecar and save it atomically."""
    state = load_review_state(root, layer)
    mutate(state)
    save_review_state(root, state)
    return state


@dataclass(frozen=True, slots=True)
class ChangeContext:
    """Who requested a draft change, from where, and whether it is approved."""

    actor: Actor
    origin: ChangeOrigin = ChangeOrigin.MANUAL_CLI
    approved: bool = True
    approved_by: Actor | None = None

    @property
    def approval(self) -> ApprovalStatus:
        if not self.approved:
            return ApprovalStatus.PROPOSED
        if self.origin is ChangeOrigin.AUTOMATION:
            return ApprovalStatus.AUTOMATION_POLICY
        if self.origin is ChangeOrigin.AGENT_AUTONOMOUS:
            # An unattended agent decision under a user-granted policy is never
            # recorded as human review.
            return ApprovalStatus.AGENT_POLICY
        return ApprovalStatus.APPROVED


@dataclass(frozen=True, slots=True)
class EditResult:
    """Outcome of a planned or applied draft edit."""

    layer: str
    path: str
    diff: str
    wrote: bool
    event: ReviewEvent | None
    data: Any
    warnings: tuple[str, ...] = ()


def refuse_legacy_layout(root: Path) -> None:
    """Stop before working over drafts of an earlier layout (migrate first)."""
    legacy = legacy_paths(root)
    if legacy and not (root / DRAFTS_DIR).is_dir():
        raise LayerError(
            f"{', '.join(legacy)} holds drafts or sessions from an earlier nf-splice "
            "layout; run `nf-splice migrate --check`, then "
            "`nf-splice migrate --apply` to move them to .splice-local/"
        )


def read_layer(root: Path, layer: str) -> YamlFileState:
    """Read the current bytes and parse result of a layer's draft."""
    refuse_legacy_layout(root)
    return read_yaml(root, layer_spec(layer).draft)


def seed_draft(
    root: Path,
    layer: str,
    data: Mapping[str, Any],
    *,
    seeded_pointers: Iterable[str] = (),
    header: Sequence[str] = (),
    review: Callable[[ReviewState], None] | None = None,
) -> bool:
    """Create a layer draft only if absent; never overwrite an existing draft."""
    refuse_legacy_layout(root)
    spec = layer_spec(layer)
    document = {DRAFT_MARKER: draft_marker(layer), **data}
    created = create_file(
        root,
        spec.draft,
        dump_yaml_data(
            document,
            header=header
            or (
                f"nf-SPLICE {spec.title.lower()} draft (authoritative, editable).",
                "Seeded from repository evidence: edit anything, in any editor.",
                "Null fields are unresolved. nf-splice never overwrites this file.",
            ),
        ).encode("utf-8"),
    )
    if not created:
        return False

    def mutate(state: ReviewState) -> None:
        for pointer in seeded_pointers:
            value = resolve(document, pointer)
            if value is not ABSENT and value is not None:
                state.seeded[pointer] = value_sha256(value)
        if review is not None:
            review(state)

    update_review_state(root, layer, mutate)
    return True


def _record(
    root: Path,
    layer: str,
    action: str,
    context: ChangeContext,
    pointers: tuple[str, ...],
    before: str | None,
    after: str | None,
) -> ReviewEvent:
    event = make_event(
        layer=layer,
        action=action,
        origin=context.origin,
        approval=context.approval,
        actor=context.actor,
        approved_by=context.approved_by,
        pointers=pointers,
        before_sha256=before,
        after_sha256=after,
    )
    record_private(root, event)
    return event


def edit_draft(
    root: Path,
    layer: str,
    operations: Sequence[PatchOp],
    context: ChangeContext,
    *,
    action: str = "edit",
    write: bool = True,
    confirm: bool = True,
    review: Callable[[ReviewState], None] | None = None,
) -> EditResult:
    """Plan or apply a targeted, three-way-merged edit to a layer draft.

    Only an approved change is written. Applied pointers are recorded as
    confirmed (deliberate review) and a review event is appended.
    """
    spec = layer_spec(layer)
    if write and not context.approved:
        raise LayerError(
            f"{spec.draft}: change is only a proposal; explicit approval is required"
        )
    for operation in operations:
        if operation.path == f"/{DRAFT_MARKER}" or operation.path.startswith(
            f"/{DRAFT_MARKER}/"
        ):
            raise LayerError("the draft marker is managed by nf-splice")
    outcome = patch_yaml(root, spec.draft, operations, write=write)
    if not write or not operations:
        return EditResult(layer, spec.draft, outcome.diff, False, None, outcome.data)
    pointers = tuple(sorted({item.path for item in operations}))
    event = _record(
        root,
        layer,
        action,
        context,
        pointers,
        outcome.before_sha256,
        outcome.after_sha256,
    )

    def mutate(state: ReviewState) -> None:
        if confirm:
            for pointer in pointers:
                value = resolve(outcome.data, pointer)
                if value is ABSENT:
                    state.confirmed.pop(pointer, None)
                    continue
                state.confirmed[pointer] = {
                    "sha256": value_sha256(value),
                    "event": event.id,
                }
        state.events.append(event.model_dump(mode="json"))
        if review is not None:
            review(state)

    update_review_state(root, layer, mutate)
    return EditResult(
        layer, spec.draft, outcome.diff, outcome.wrote, event, outcome.data
    )


def replace_draft(
    root: Path,
    layer: str,
    context: ChangeContext,
    *,
    expected_sha256: str | None,
    content: str | None = None,
    data: Any = ABSENT,
    section: str | None = None,
    write: bool = True,
) -> EditResult:
    """Deliberately replace a whole draft, or one section of it.

    This is authoring, not regeneration: the caller states the file hash it
    read (``expected_sha256``), so an edit made on disk since then is never
    overwritten. The new content only has to be *safe* (restricted YAML that
    parses, the draft marker unchanged, an allowed path); it does not have to
    pass the layer's semantic validation, so a person or an agent can save a
    useful intermediate draft and repair it in later revisions.

    - ``content``: complete YAML text of the draft (comments are kept as
      written).
    - ``data``: a JSON value; with ``section`` it replaces that JSON pointer
      (comments outside the section survive), without it the whole document.
    """
    spec = layer_spec(layer)
    if write and not context.approved:
        raise LayerError(
            f"{spec.draft}: change is only a proposal; explicit approval is required"
        )
    if (content is None) == (data is ABSENT):
        raise LayerError("supply either the YAML content or the data, not both")
    if content is not None and section is not None:
        raise LayerError("a section is replaced with data, not YAML text")
    if section is not None and (
        not section.startswith("/")
        or section == f"/{DRAFT_MARKER}"
        or section.startswith(f"/{DRAFT_MARKER}/")
    ):
        raise LayerError(
            "section must be a JSON pointer such as /outputs, and the draft "
            "marker is managed by nf-splice"
        )
    state = read_layer(root, spec.name)
    if state.file.sha256 != expected_sha256:
        raise DraftConflictError(
            spec.draft,
            "the draft changed on disk since it was read (for example in an "
            "editor); read it again and base the replacement on the current file",
        )
    marker = draft_marker(spec.name)
    if section is not None:
        if state.draft is None:
            raise LayerError(
                f"{spec.draft} cannot be edited by section until its syntax is "
                f"fixed: {state.error}"
            )
        current = resolve(state.draft.data, section)
        operation = (
            PatchOp("add", section, data)
            if current is ABSENT
            else PatchOp("replace", section, data, expected=current)
        )
        outcome = patch_yaml(root, spec.draft, [operation], write=write)
        before_sha, after_sha, rendered, written = (
            outcome.before_sha256,
            outcome.after_sha256,
            outcome.diff,
            outcome.wrote,
        )
        new_data = outcome.data
        pointers: tuple[str, ...] = (section,)
    else:
        if content is None:
            if not isinstance(data, Mapping):
                raise LayerError("a draft is a mapping of top-level fields")
            document = {DRAFT_MARKER: marker} | {
                key: value for key, value in data.items() if key != DRAFT_MARKER
            }
            text = dump_yaml_data(
                document,
                header=(
                    f"nf-SPLICE {spec.title.lower()} draft (authoritative, editable).",
                ),
            )
        else:
            text = content if content.endswith("\n") else content + "\n"
        try:
            parsed = load_yaml_draft(text)
        except DraftSyntaxError as error:
            raise LayerError(
                f"{spec.draft}: unsafe or invalid YAML: {error}"
            ) from error
        if not isinstance(parsed.data, dict):
            raise LayerError(f"{spec.draft}: a draft must be a mapping")
        if parsed.data.get(DRAFT_MARKER) != marker:
            raise LayerError(
                f"{spec.draft}: keep the {DRAFT_MARKER} block exactly as nf-splice "
                "wrote it"
            )
        before_text = state.file.text or ""
        rendered = text_diff(spec.draft, before_text, text)
        before_sha = state.file.sha256
        after_sha = sha256(text.encode("utf-8"))
        written = False
        if write and text != before_text:
            replace_file(
                root, spec.draft, text.encode("utf-8"), expected_sha256=expected_sha256
            )
            written = True
        new_data = parsed.data
        pointers = ("",)
    if not write:
        return EditResult(spec.name, spec.draft, rendered, False, None, new_data)
    event = _record(
        root,
        spec.name,
        "replace_section" if section is not None else "replace_draft",
        context,
        pointers,
        before_sha,
        after_sha,
    )

    def mutate(review: ReviewState) -> None:
        review.events.append(event.model_dump(mode="json"))

    update_review_state(root, spec.name, mutate)
    return EditResult(spec.name, spec.draft, rendered, written, event, new_data)


def confirm_values(
    root: Path, layer: str, pointers: Sequence[str], context: ChangeContext
) -> ReviewEvent:
    """Record deliberate confirmation of current (e.g. detected) draft values."""
    if not context.approved:
        raise LayerError("confirmation requires explicit approval")
    state = read_layer(root, layer)
    if state.draft is None:
        raise LayerError(f"{layer_spec(layer).draft} is missing or malformed")
    data = state.draft.data
    missing = [item for item in pointers if resolve(data, item) in (ABSENT, None)]
    if missing:
        raise LayerError(f"cannot confirm absent values: {', '.join(missing)}")
    event = _record(
        root,
        layer,
        "confirm",
        context,
        tuple(sorted(pointers)),
        state.file.sha256,
        state.file.sha256,
    )

    def mutate(review: ReviewState) -> None:
        for pointer in pointers:
            review.confirmed[pointer] = {
                "sha256": value_sha256(resolve(data, pointer)),
                "event": event.id,
            }
        review.events.append(event.model_dump(mode="json"))

    update_review_state(root, layer, mutate)
    return event


@dataclass(frozen=True, slots=True)
class LayerValidation:
    """Readiness of one layer derived from current draft bytes.

    ``files`` holds the compiled final payloads (relative to ``splice/``)
    only when the layer has no blocking issue.
    """

    layer: str
    issues: tuple[DraftIssue, ...]
    files: Mapping[str, bytes] = field(default_factory=dict)

    @property
    def errors(self) -> tuple[DraftIssue, ...]:
        return tuple(item for item in self.issues if item.severity is Severity.ERROR)

    @property
    def ready(self) -> bool:
        return not self.errors and bool(self.files)


def issue(
    layer: str,
    pointer: str,
    code: str,
    message: str,
    severity: Severity = Severity.ERROR,
    *,
    path: str | None = None,
) -> DraftIssue:
    """Build an issue addressed to a layer draft (or another path)."""
    return DraftIssue(
        layer, path or layer_spec(layer).draft, pointer, severity, code, message
    )


def record_decision(
    root: Path,
    layer: str,
    action: str,
    context: ChangeContext,
    pointers: tuple[str, ...],
    mutate: Callable[[ReviewState], None],
) -> ReviewEvent:
    """Record a review decision that changes only the sidecar (e.g. reject)."""
    if not context.approved:
        raise LayerError(f"{action} requires explicit approval")
    current = read_layer(root, layer).file.sha256
    event = _record(root, layer, action, context, pointers, current, current)

    def apply(state: ReviewState) -> None:
        mutate(state)
        state.events.append(event.model_dump(mode="json"))

    update_review_state(root, layer, apply)
    return event


def ops_for(data: Any, changes: Mapping[str, Any]) -> list[PatchOp]:
    """Build expected-value operations that set pointers to new values."""
    operations = []
    for pointer, value in changes.items():
        current = resolve(data, pointer)
        if current is ABSENT:
            operations.append(PatchOp("add", pointer, value))
        elif value is ABSENT:
            operations.append(PatchOp("remove", pointer, expected=current))
        else:
            operations.append(PatchOp("replace", pointer, value, expected=current))
    return operations


__all__ = [
    "LAYERS",
    "ChangeContext",
    "DraftConflictError",
    "DraftIssue",
    "EditResult",
    "LayerError",
    "LayerSpec",
    "LayerValidation",
    "ReviewState",
    "Severity",
    "confirm_values",
    "draft_marker",
    "edit_draft",
    "issue",
    "layer_spec",
    "load_review_state",
    "ops_for",
    "read_layer",
    "record_decision",
    "replace_draft",
    "save_review_state",
    "seed_draft",
    "strip_marker",
    "update_review_state",
    "value_sha256",
]
