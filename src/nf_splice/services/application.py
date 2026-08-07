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
from nf_splice.services.components import (
    accept_unambiguous_components,
    discover_components,
    review_component,
)
from nf_splice.services.execution import (
    ExecutionBuildResult,
    build_execution_profiles,
    discover_execution_profiles,
    plan_execution_profiles,
    reject_execution_profile,
    review_execution_profile,
)
from nf_splice.services.inputs import discover_inputs, review_input
from nf_splice.services.orchestration import (
    IntegrationBuildResult,
    IntegrationPlan,
    IntegrationValidationReport,
    build_integration,
    plan_integration,
    validate_integration,
)
from nf_splice.services.output_contracts import (
    OutputContractBuildResult,
    build_output_contracts,
    plan_output_contracts,
)
from nf_splice.services.provenance import (
    build_provenance,
    discover_provenance,
    plan_provenance,
    review_provenance,
)
from nf_splice.services.state import (
    StateMigrationResult,
    apply_state_migration,
    plan_state_migration,
)
from nf_splice.services.static_layers import (
    StaticLayerBuildResult,
    build_static_layer,
    plan_static_layer,
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
    """Read-only summary of ``splice/nf-splice.yaml``."""

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
    build_status: str = "reviewed layer and complete integration builds available"
    validation_status: str = "static bundle and runtime output validation available"


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

    def plan_state_migration(
        self, repository_root: str | Path = "."
    ) -> StateMigrationResult:
        """Preview explicit legacy-state reconciliation."""
        return plan_state_migration(repository_root)

    def apply_state_migration(
        self, repository_root: str | Path = "."
    ) -> StateMigrationResult:
        """Apply a previously reviewable, non-destructive state migration."""
        return apply_state_migration(repository_root)

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

    def discover_inputs(self, repository_root: str | Path = ".") -> AuthoringDocument:
        """Discover upstream parameters through the shared authoring core."""
        return discover_inputs(repository_root)

    def review_input(
        self,
        repository_root: str | Path,
        candidate_id: str,
        classification: str,
        *,
        type_override: str | None = None,
        description_override: str | None = None,
    ) -> AuthoringDocument:
        """Classify one pipeline parameter through shared rules."""
        return review_input(
            repository_root,
            candidate_id,
            classification,
            type_override=type_override,
            description_override=description_override,
        )

    def discover_components(
        self, repository_root: str | Path = "."
    ) -> AuthoringDocument:
        """Discover workflow software evidence through the shared core."""
        return discover_components(repository_root)

    def review_component(
        self,
        repository_root: str | Path,
        candidate_id: str,
        *,
        version: str | None = None,
        container_uri: str | None = None,
    ) -> AuthoringDocument:
        """Resolve and accept one component through shared rules."""
        return review_component(
            repository_root,
            candidate_id,
            version=version,
            container_uri=container_uri,
        )

    def accept_unambiguous_components(
        self, repository_root: str | Path
    ) -> AuthoringDocument:
        """Explicitly accept every component without conflicting evidence."""
        return accept_unambiguous_components(repository_root)

    def discover_execution_profiles(
        self, repository_root: str | Path = "."
    ) -> AuthoringDocument:
        """Discover execution environments through the shared authoring core."""
        return discover_execution_profiles(repository_root)

    def review_execution_profile(
        self,
        repository_root: str | Path,
        candidate_id: str,
        *,
        profile_type: str,
        description: str,
        executor: str | None = None,
        container_engine: str | None = None,
        config_source: str | None = None,
    ) -> AuthoringDocument:
        """Select one supported execution environment through shared rules."""
        return review_execution_profile(
            repository_root,
            candidate_id,
            profile_type=profile_type,
            description=description,
            executor=executor,
            container_engine=container_engine,
            config_source=config_source,
        )

    def reject_execution_profile(
        self, repository_root: str | Path, candidate_id: str, reason: str
    ) -> AuthoringDocument:
        """Mark one detected environment unsupported through shared rules."""
        return reject_execution_profile(repository_root, candidate_id, reason)

    def plan_execution_profiles(
        self, repository_root: str | Path
    ) -> ExecutionBuildResult:
        """Preview selected execution profiles and configs."""
        return plan_execution_profiles(repository_root)

    def build_execution_profiles(
        self,
        repository_root: str | Path,
        *,
        replace_existing: bool = False,
    ) -> ExecutionBuildResult:
        """Materialise selected execution profiles and safe configs."""
        return build_execution_profiles(
            repository_root, replace_existing=replace_existing
        )

    def discover_provenance(
        self,
        repository_root: str | Path = ".",
    ) -> AuthoringDocument:
        """Discover the required repository-root RO-Crate."""
        return discover_provenance(repository_root)

    def review_provenance(
        self,
        repository_root: str | Path,
        candidate_id: str,
    ) -> AuthoringDocument:
        """Approve unchanged inclusion of the root RO-Crate."""
        return review_provenance(repository_root, candidate_id)

    def plan_provenance(self, repository_root: str | Path) -> StaticLayerBuildResult:
        """Preview reviewed RO-Crate metadata."""
        return plan_provenance(repository_root)

    def build_provenance(
        self,
        repository_root: str | Path,
        *,
        replace_existing: bool = False,
    ) -> StaticLayerBuildResult:
        """Materialise reviewed RO-Crate metadata."""
        return build_provenance(repository_root, replace_existing=replace_existing)

    def plan_static_layer(
        self, repository_root: str | Path, target: str
    ) -> StaticLayerBuildResult:
        """Preview an input or component artefact."""
        return plan_static_layer(repository_root, target)

    def build_static_layer(
        self,
        repository_root: str | Path,
        target: str,
        *,
        replace_existing: bool = False,
    ) -> StaticLayerBuildResult:
        """Materialise an input or component artefact."""
        return build_static_layer(
            repository_root, target, replace_existing=replace_existing
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

    def plan_integration(
        self, repository_root: str | Path = ".", *, target: str = "all"
    ) -> IntegrationPlan:
        """Preview the complete reviewed integration without writes."""
        return plan_integration(repository_root, target=target)

    def build_integration(
        self,
        repository_root: str | Path = ".",
        *,
        target: str = "all",
        replace_existing: bool = False,
        check: bool = False,
    ) -> IntegrationBuildResult:
        """Materialise a complete reviewed integration after one preflight."""
        return build_integration(
            repository_root,
            target=target,
            replace_existing=replace_existing,
            check=check,
        )

    def validate_integration(
        self, repository_root: str | Path = "."
    ) -> IntegrationValidationReport:
        """Validate the complete static integration and its provenance."""
        return validate_integration(repository_root)

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
        path = root / "splice" / "nf-splice.yaml"
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
            warnings.append(f"splice/nf-splice.yaml is invalid: {authoring.detail}")
        warnings.extend(
            f"Legacy state at {item.path} is {item.classification.value}; "
            f"explicit migration target is {item.destination}"
            + (f": {item.detail}" if item.detail else "")
            for item in inspection.legacy_state
        )
        return tuple(warnings)
