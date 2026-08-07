"""Shared application services consumed by every nf-splice interface."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from nf_splice.domain import (
    AuthoringDocument,
    AuthoringDocumentError,
    EvidenceKind,
    LayerStatus,
    PathClassification,
    RepositoryInspection,
    TreeState,
    load_authoring_document,
)
from nf_splice.inspectors import inspect_repository
from nf_splice.services.authoring import (
    DiscoveryResult,
    accept_output,
    discover_outputs,
    initialise_authoring_document,
    reject_output,
)
from nf_splice.services.output_contracts import (
    OutputContractBuildResult,
    build_output_contracts,
    plan_output_contracts,
)

_INTEGRATION_LAYERS = (
    "identity",
    "inputs",
    "outputs",
    "components",
    "execution_profiles",
    "provenance",
    "bundle",
)


class AuthoringState(str, Enum):
    """Read-only availability of canonical authoring state."""

    ABSENT = "not initialized"
    VALID = "available"
    INVALID = "invalid"


class Operation(str, Enum):
    """Planned mutating or generation operations exposed by interface shells."""

    CONFIGURE = "configure"
    PLAN = "plan"
    BUILD = "build"
    VALIDATE = "validate"


@dataclass(frozen=True, slots=True)
class EvidenceCount:
    """Count of detected evidence for one machine-readable kind."""

    kind: EvidenceKind
    count: int


@dataclass(frozen=True, slots=True)
class AuthoringSummary:
    """Read-only summary of ``nf-splice.yaml``."""

    state: AuthoringState
    unresolved_decisions: int | None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class LayerSummary:
    """Interface-neutral readiness summary for one integration layer."""

    name: str
    status: LayerStatus
    decision_count: int
    unresolved_decisions: int | None


@dataclass(frozen=True, slots=True)
class WorkspaceSnapshot:
    """Immutable result shared by CLI and TUI presentation code."""

    inspection: RepositoryInspection
    evidence_counts: tuple[EvidenceCount, ...]
    authoring: AuthoringSummary
    layers: tuple[LayerSummary, ...]
    warnings: tuple[str, ...]
    build_status: str = "output contracts available"
    validation_status: str = "runtime outputs available; bundle not available"


@dataclass(frozen=True, slots=True)
class UnavailableOperation:
    """Truthful result returned for a planned operation with no semantics yet."""

    operation: Operation
    message: str


class ApplicationService:
    """Coordinate read-only application state without interface-specific rules."""

    def inspect(self, repository_root: str | Path = ".") -> WorkspaceSnapshot:
        """Inspect a repository and return one shared interface snapshot."""
        inspection = inspect_repository(repository_root)
        root = Path(inspection.root)
        authoring, document = self._authoring_summary(root)
        evidence_counts = tuple(
            EvidenceCount(kind=kind, count=count)
            for kind, count in sorted(
                Counter(item.kind for item in inspection.evidence).items(),
                key=lambda item: item[0].value,
            )
        )
        return WorkspaceSnapshot(
            inspection=inspection,
            evidence_counts=evidence_counts,
            authoring=authoring,
            layers=self._layer_summaries(document),
            warnings=self._warnings(inspection, authoring),
        )

    def initialise(
        self,
        repository_root: str | Path = ".",
        *,
        name: str | None = None,
        version: str | None = None,
        repository_url: str | None = None,
        release_url: str | None = None,
        accept_detected: bool = False,
    ) -> AuthoringDocument:
        """Initialise reviewed identity through the shared authoring core."""
        return initialise_authoring_document(
            repository_root,
            name=name,
            version=version,
            repository_url=repository_url,
            release_url=release_url,
            accept_detected=accept_detected,
        )

    def discover_outputs(
        self,
        repository_root: str | Path = ".",
        *,
        example_output_tree: str | Path | None = None,
        publish_directory: str | Path | None = None,
        contract_version: str | None = None,
    ) -> DiscoveryResult:
        """Discover and persist output candidates through the shared core."""
        return discover_outputs(
            repository_root,
            example_output_tree=example_output_tree,
            publish_directory=publish_directory,
            contract_version=contract_version,
        )

    def accept_output(
        self,
        repository_root: str | Path,
        candidate_id: str,
        output: Mapping[str, Any],
    ) -> AuthoringDocument:
        """Accept one complete output review through shared validation."""
        return accept_output(repository_root, candidate_id, output)

    def reject_output(
        self, repository_root: str | Path, candidate_id: str, reason: str
    ) -> AuthoringDocument:
        """Reject one output candidate through shared validation."""
        return reject_output(repository_root, candidate_id, reason)

    def plan_output_contracts(
        self, repository_root: str | Path = "."
    ) -> OutputContractBuildResult:
        """Preview reviewed output-contract artefacts without writing them."""
        return plan_output_contracts(repository_root)

    def build_output_contracts(
        self,
        repository_root: str | Path = ".",
        *,
        replace_existing: bool = False,
    ) -> OutputContractBuildResult:
        """Materialise the reviewed output-contract layer."""
        return build_output_contracts(
            repository_root, replace_existing=replace_existing
        )

    @staticmethod
    def unavailable(operation: Operation) -> UnavailableOperation:
        """Describe a visible command whose application behaviour is not built yet."""
        descriptions = {
            Operation.CONFIGURE: (
                "Integration-layer configuration is not available yet."
            ),
            Operation.PLAN: "Change planning is not available yet.",
            Operation.BUILD: "Integration building is not available yet.",
            Operation.VALIDATE: "Integration validation is not available yet.",
        }
        return UnavailableOperation(
            operation=operation, message=descriptions[operation]
        )

    @staticmethod
    def _authoring_summary(
        root: Path,
    ) -> tuple[AuthoringSummary, AuthoringDocument | None]:
        path = root / "nf-splice.yaml"
        if not path.exists():
            return (
                AuthoringSummary(
                    state=AuthoringState.ABSENT,
                    unresolved_decisions=None,
                ),
                None,
            )
        try:
            document = load_authoring_document(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, AuthoringDocumentError) as error:
            return (
                AuthoringSummary(
                    state=AuthoringState.INVALID,
                    unresolved_decisions=None,
                    detail=str(error),
                ),
                None,
            )
        unresolved = {
            item.decision_id for layer in document.layers for item in layer.unresolved
        }
        return (
            AuthoringSummary(
                state=AuthoringState.VALID,
                unresolved_decisions=len(unresolved),
            ),
            document,
        )

    @staticmethod
    def _layer_summaries(
        document: AuthoringDocument | None,
    ) -> tuple[LayerSummary, ...]:
        if document is None:
            return tuple(
                LayerSummary(
                    name=name,
                    status=LayerStatus.NOT_CONFIGURED,
                    decision_count=0,
                    unresolved_decisions=None,
                )
                for name in _INTEGRATION_LAYERS
            )

        by_name = {layer.name: layer for layer in document.layers}
        names = (
            *_INTEGRATION_LAYERS,
            *(sorted(set(by_name) - set(_INTEGRATION_LAYERS))),
        )
        summaries: list[LayerSummary] = []
        for name in names:
            layer = by_name.get(name)
            summaries.append(
                LayerSummary(
                    name=name,
                    status=(
                        layer.status
                        if layer is not None
                        else LayerStatus.NOT_CONFIGURED
                    ),
                    decision_count=len(layer.decision_ids) if layer is not None else 0,
                    unresolved_decisions=len(layer.unresolved)
                    if layer is not None
                    else 0,
                )
            )
        return tuple(summaries)

    @staticmethod
    def _warnings(
        inspection: RepositoryInspection,
        authoring: AuthoringSummary,
    ) -> tuple[str, ...]:
        warnings: list[str] = []
        tree = inspection.splice_tree
        if tree.state is TreeState.ABSENT:
            warnings.append("No repository-root splice/ integration exists.")
        elif tree.state is TreeState.EMPTY:
            warnings.append("The repository-root splice/ directory is empty.")

        unknown_count = sum(
            item.classification is PathClassification.UNKNOWN for item in tree.paths
        )
        if unknown_count:
            warnings.append(
                f"{unknown_count} unknown splice/ path(s) will be preserved."
            )
        warnings.extend(
            f"Unsafe collision at {item.path}: {item.reason}"
            for item in tree.collisions
        )
        if authoring.state is AuthoringState.INVALID:
            warnings.append(f"nf-splice.yaml is invalid: {authoring.detail}")
        return tuple(warnings)
