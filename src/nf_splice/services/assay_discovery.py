"""Deterministic scientific discovery of a pipeline's assay capabilities.

nf-splice investigates what a pipeline does, not only what it calls itself:

1. **Evidence.** It reads the tools the pipeline runs (module, process,
   container and conda package names), its parameters and allowed values,
   sample sheet columns, published output paths, and its documentation.
2. **Rules.** Packaged, versioned evidence rules
   (``catalogue/data/assay-evidence-rules.json``) link evidence to a SPLICE
   vocabulary entity at the level the evidence can support: quantification
   tools establish *Short-read RNA-seq*, not *poly(A) RNA-seq*. A rule needs
   several independent terms, and some need a specific tool, so a
   contamination screen (Kraken2) does not make an RNA-seq pipeline a
   metagenomics pipeline.
3. **Vocabulary.** Each established entity is expanded through the
   vocabulary DAG to the assays a pipeline can declare. Each candidate gets a
   status: ``documented`` (the repository names it), ``supported`` (the
   evidence establishes this level and nothing finer is registered),
   ``suggested`` (distinguishing evidence points to it, unconfirmed) or
   ``requires_verification`` (plausible, not distinguishable from its
   alternatives). Explicit mentions of an assay are evidence too.
4. **Questions.** Where the evidence cannot tell alternatives apart, the
   assessment says so and asks the one question that would decide it.

Nothing here declares a capability; people and agents do that through the
identity layer's services, which re-check every choice.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass, field, replace
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any

from nf_splice.catalogue import (
    ASSAY_TYPES,
    Catalogue,
    CatalogueError,
    Entity,
    EntityType,
    default_catalogue,
)

KINDS = ("tool", "parameter", "samplesheet", "output", "text")
_MAX_BYTES = 768_000
_SKIP = {".git", ".splice-local", ".nf-splice-local", "work", "results", ".nextflow"}
_DOC_SUFFIXES = {".md", ".rst", ".txt"}


# ---------------------------------------------------------------- rules


@dataclass(frozen=True, slots=True)
class EvidenceRule:
    id: str
    role: str
    target: int
    basis: str
    signals: dict[str, tuple[str, ...]]
    require_kinds: tuple[str, ...]
    require_terms: tuple[str, ...]
    min_distinct: int


@dataclass(frozen=True, slots=True)
class RuleSet:
    version: str
    rules: tuple[EvidenceRule, ...]


def _load_rules(catalogue: Catalogue) -> RuleSet:
    text = (
        resources.files("nf_splice.catalogue")
        .joinpath("data")
        .joinpath("assay-evidence-rules.json")
        .read_text(encoding="utf-8")
    )
    document = json.loads(text)
    if document.get("format") != "nf-splice-assay-evidence-rules/1":
        raise CatalogueError("invalid_snapshot", "unknown evidence rule format")
    rules = []
    for row in document["rules"]:
        target = catalogue.entity(int(row["target"]))
        if row["role"] not in {"establishes", "suggests"}:
            raise CatalogueError("invalid_snapshot", f"rule {row['id']}: bad role")
        if row["role"] == "suggests" and target.entity_type not in ASSAY_TYPES:
            raise CatalogueError(
                "invalid_snapshot", f"rule {row['id']}: suggests a non-assay entity"
            )
        if target.entity_type in {EntityType.ROOT, EntityType.MODALITY}:
            raise CatalogueError(
                "invalid_snapshot", f"rule {row['id']}: targets {target.label}"
            )
        signals = {
            kind: tuple(str(term).lower() for term in row["signals"].get(kind, ()))
            for kind in KINDS
        }
        unknown = set(row["signals"]) - set(KINDS)
        if unknown:
            raise CatalogueError(
                "invalid_snapshot", f"rule {row['id']}: unknown kinds {unknown}"
            )
        rules.append(
            EvidenceRule(
                id=str(row["id"]),
                role=str(row["role"]),
                target=target.entity_id,
                basis=str(row["basis"]),
                signals=signals,
                require_kinds=tuple(row.get("require_kinds", ())),
                require_terms=tuple(
                    str(t).lower() for t in row.get("require_terms", ())
                ),
                min_distinct=int(row.get("min_distinct", 1)),
            )
        )
    return RuleSet(str(document["version"]), tuple(rules))


@lru_cache(maxsize=1)
def evidence_rules() -> RuleSet:
    return _load_rules(default_catalogue())


# -------------------------------------------------------------- evidence


@dataclass(slots=True)
class Corpus:
    """Everything read from the repository, by evidence kind."""

    names: dict[str, dict[str, set[str]]] = field(
        default_factory=lambda: {kind: defaultdict(set) for kind in KINDS}
    )
    texts: list[tuple[str, str]] = field(default_factory=list)

    def add(self, kind: str, value: str, location: str) -> None:
        value = value.strip().lower()
        if value:
            self.names[kind][value].add(location)


def _files(root: Path, suffixes: set[str]) -> list[Path]:
    found = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).parts
        if any(part in _SKIP for part in relative):
            continue
        if path.suffix.lower() in suffixes and path.is_file() and not path.is_symlink():
            try:
                if path.stat().st_size <= _MAX_BYTES:
                    found.append(path)
            except OSError:
                continue
    return found


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return ""


def _line(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


_PROCESS = re.compile(r"(?m)^\s*process\s+([A-Za-z0-9_]+)\s*\{")
_CONTAINER = re.compile(r"[\"']([a-z0-9.\-]+(?:/[a-z0-9._\-]+)+)(?::[^\"']*)?[\"']")
_PUBLISH = re.compile(r"(?:path\s*:\s*|publishDir\s+)[{\s]*[\"']([^\"'$]*)")
_PARAM = re.compile(r"\bparams\.([A-Za-z0-9_]+)")


def gather(root: Path) -> Corpus:
    """Read the repository's scientific evidence (read-only)."""
    corpus = Corpus()
    modules = root / "modules"
    if modules.is_dir():
        for main in sorted(modules.rglob("main.nf")):
            relative = main.parent.relative_to(root).as_posix()
            corpus.add("tool", main.parent.name, relative)
            for part in main.parent.relative_to(modules).parts:
                corpus.add("tool", part, relative)
    for path in _files(root, {".nf", ".config"}):
        relative = path.relative_to(root).as_posix()
        text = _read(path)
        for match in _PROCESS.finditer(text):
            corpus.add(
                "tool", match.group(1), f"{relative}:{_line(text, match.start())}"
            )
        for match in _CONTAINER.finditer(text):
            image = match.group(1).rsplit("/", 1)[-1]
            corpus.add("tool", image, f"{relative}:{_line(text, match.start())}")
        for match in _PUBLISH.finditer(text):
            corpus.add(
                "output", match.group(1), f"{relative}:{_line(text, match.start())}"
            )
        for match in _PARAM.finditer(text):
            corpus.add(
                "parameter", match.group(1), f"{relative}:{_line(text, match.start())}"
            )
    for path in _files(root, {".yml", ".yaml"}):
        if path.name not in {"environment.yml", "environment.yaml"}:
            continue
        relative = path.relative_to(root).as_posix()
        for line in _read(path).splitlines():
            stripped = line.strip().lstrip("- ")
            if "::" in stripped:
                corpus.add(
                    "tool", re.split(r"[=<>]", stripped.split("::", 1)[1])[0], relative
                )
    schema = root / "nextflow_schema.json"
    if schema.is_file():
        _schema(corpus, schema, "nextflow_schema.json", "parameter")
    for candidate in ("assets/schema_input.json", "assets/schema_samplesheet.json"):
        if (root / candidate).is_file():
            _schema(corpus, root / candidate, candidate, "samplesheet")
    for path in _files(root, {".csv", ".tsv"}):
        relative = path.relative_to(root).as_posix()
        if not any(
            part in {"assets", "tests", "test", "examples"} for part in path.parts
        ):
            continue
        header = _read(path).splitlines()[:1]
        for column in re.split(r"[,\t]", header[0]) if header else ():
            corpus.add("samplesheet", column, f"{relative}:1")
    for path in _files(root, _DOC_SUFFIXES):
        relative = path.relative_to(root).as_posix()
        if path.parent == root or "docs" in path.relative_to(root).parts:
            corpus.texts.append((relative, _read(path)))
    return corpus


def _schema(corpus: Corpus, path: Path, relative: str, kind: str) -> None:
    try:
        document = json.loads(_read(path))
    except json.JSONDecodeError:
        return
    texts: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                for name, definition in properties.items():
                    corpus.add(kind, str(name), relative)
                    if isinstance(definition, dict):
                        for value in definition.get("enum") or ():
                            corpus.add(kind, str(value), relative)
                        for key in ("description", "help_text"):
                            if isinstance(definition.get(key), str):
                                texts.append(definition[key])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(document)
    if texts:
        corpus.texts.append((relative, "\n".join(texts)))


# --------------------------------------------------------------- matching


@dataclass(frozen=True, slots=True)
class Evidence:
    kind: str
    term: str
    locations: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        return {"kind": self.kind, "term": self.term, "locations": list(self.locations)}


def _tokens(name: str) -> set[str]:
    return {part for part in re.split(r"[^a-z0-9]+", name.lower()) if part} | {name}


def _match_names(corpus: Corpus, kind: str, terms: tuple[str, ...]) -> list[Evidence]:
    found = []
    names = corpus.names[kind]
    for term in terms:
        locations: set[str] = set()
        for name, where in names.items():
            if (
                term == name
                or term in _tokens(name)
                or ("_" in term and re.search(rf"(^|_){re.escape(term)}(_|$)", name))
            ):
                locations |= where
        if locations:
            found.append(Evidence(kind, term, tuple(sorted(locations))[:5]))
    return found


def _match_text(corpus: Corpus, terms: tuple[str, ...]) -> list[Evidence]:
    found = []
    for term in terms:
        pattern = re.compile(
            r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", re.IGNORECASE
        )
        locations = []
        for name, text in corpus.texts:
            for match in pattern.finditer(text):
                locations.append(f"{name}:{_line(text, match.start())}")
        if locations:
            found.append(Evidence("text", term, tuple(sorted(set(locations)))[:5]))
    return found


def _rule_evidence(corpus: Corpus, rule: EvidenceRule) -> list[Evidence]:
    found: list[Evidence] = []
    for kind in KINDS:
        terms = rule.signals.get(kind, ())
        if not terms:
            continue
        found.extend(
            _match_text(corpus, terms)
            if kind == "text"
            else _match_names(corpus, kind, terms)
        )
    return found


def _satisfied(rule: EvidenceRule, evidence: list[Evidence]) -> tuple[bool, str]:
    terms = {item.term for item in evidence}
    if len(terms) < rule.min_distinct:
        return False, f"{len(terms)} of the {rule.min_distinct} distinct signals needed"
    kinds = {item.kind for item in evidence}
    missing = [kind for kind in rule.require_kinds if kind not in kinds]
    if missing:
        return False, f"no {', '.join(missing)} evidence"
    if rule.require_terms and not terms & set(rule.require_terms):
        return False, "none of the terms specific to this domain was found"
    return True, ""


# ------------------------------------------------------------- assessment


CONFIDENCE = {
    "documented": "high",
    "supported": "medium",
    "suggested": "medium",
    "requires_verification": "low",
    "rejected": "none",
}


@dataclass(frozen=True, slots=True)
class Candidate:
    """One assay a pipeline may declare, with why and how sure."""

    reference: str
    entity: Entity
    registered_code: str | None
    status: str
    established_by: tuple[str, ...]
    evidence: tuple[Evidence, ...]
    alternatives: tuple[str, ...]
    uncertainty: str
    selectable: bool
    paths: tuple[tuple[Entity, ...], ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "registered_code": self.registered_code,
            "entity": self.entity.reference(with_type=True),
            "classification_level": self.entity.entity_type.value,
            "status": self.status,
            "confidence": CONFIDENCE[self.status],
            "selectable_without_confirmation": self.selectable,
            "established_by": list(self.established_by),
            "evidence": [item.to_json() for item in self.evidence],
            "alternatives": list(self.alternatives),
            "uncertainty": self.uncertainty,
            "paths": [
                [item.reference(with_type=True) for item in path] for path in self.paths
            ],
        }


@dataclass(frozen=True, slots=True)
class Finding:
    """An entity the evidence establishes (a domain-level fact)."""

    rule: EvidenceRule
    entity: Entity
    evidence: tuple[Evidence, ...]
    modalities: tuple[Entity, ...]

    def to_json(self) -> dict[str, Any]:
        return {
            "rule": self.rule.id,
            "basis": self.rule.basis,
            "entity": self.entity.reference(with_type=True),
            "modalities": [item.reference(with_type=True) for item in self.modalities],
            "evidence": [item.to_json() for item in self.evidence],
        }


@dataclass(frozen=True, slots=True)
class AssayAssessment:
    rules_version: str
    vocabulary: dict[str, str]
    findings: tuple[Finding, ...]
    candidates: tuple[Candidate, ...]
    questions: tuple[str, ...]
    discounted: tuple[dict[str, Any], ...]
    declared: tuple[str, ...]

    @property
    def domains(self) -> tuple[Entity, ...]:
        found = {
            path[-1].entity_id: path[-1]
            for item in self.candidates
            if item.status != "rejected"
            for path in item.paths
        }
        return tuple(found[key] for key in sorted(found))

    def summary(self) -> str:
        """A short, deterministic explanation for messages and reports."""
        if not self.candidates:
            return (
                "no scientific domain could be established from the repository; "
                "declare the assays the pipeline processes"
            )
        open_ = [
            f"{item.entity.label} ({item.reference}, {item.status})"
            for item in self.candidates
            if item.status != "rejected"
        ]
        domains = ", ".join(item.label for item in self.domains)
        return f"detected {domains}; candidates: " + "; ".join(open_[:6])

    def to_json(self) -> dict[str, Any]:
        return {
            "rules_version": self.rules_version,
            "vocabulary": self.vocabulary,
            "domains": [item.reference(with_type=True) for item in self.domains],
            "findings": [item.to_json() for item in self.findings],
            "candidates": [item.to_json() for item in self.candidates],
            "questions": list(self.questions),
            "discounted": list(self.discounted),
            "declared": list(self.declared),
            "note": "Candidates are recommendations. Nothing is a capability until "
            "it is declared through nf-splice and validated.",
        }


def _descendant_assays(catalogue: Catalogue, entity: Entity) -> list[Entity]:
    """The most specific assays at or below ``entity`` (missing levels not added)."""
    found: dict[int, Entity] = {}

    def walk(node: Entity) -> None:
        children = [
            item
            for item in catalogue.children(node.entity_id)
            if item.entity_type in ASSAY_TYPES
        ]
        if node.entity_type in ASSAY_TYPES and not children:
            found[node.entity_id] = node
        for child in children:
            walk(child)
        if node.entity_type not in ASSAY_TYPES:
            for child in catalogue.children(node.entity_id):
                if child.entity_type is EntityType.MODALITY_SUBTYPE:
                    walk(child)

    walk(entity)
    return [found[key] for key in sorted(found)]


def _reference(catalogue: Catalogue, entity: Entity) -> tuple[str, str | None]:
    registrations = catalogue.registrations_for(entity.entity_id)
    if len(registrations) == 1:
        return registrations[0].code, registrations[0].code
    return f"entity:{entity.entity_id}", None


def assess_assays(
    repository_root: str | Path,
    *,
    declared: tuple[str, ...] | None = None,
    rejected: tuple[str, ...] | None = None,
    catalogue: Catalogue | None = None,
) -> AssayAssessment:
    """Investigate a repository and recommend assay capabilities (read-only).

    The reviewed decisions recorded for the repository (declared capabilities,
    rejected recommendations) are read unless the caller supplies them.
    """
    from nf_splice.inspectors.assays import detect_assay_candidates
    from nf_splice.layers.bundle import declared_capabilities, rejected_assays

    root = Path(repository_root).resolve()
    if rejected is None:
        rejected = rejected_assays(root)
    if declared is None:
        declared = tuple(
            str(item.get("registered_code") or f"entity:{item.get('entity_id')}")
            for item in declared_capabilities(root)
        )
    catalogue = catalogue or default_catalogue()
    rules = (
        evidence_rules() if catalogue is default_catalogue() else _load_rules(catalogue)
    )
    corpus = gather(root)
    findings: list[Finding] = []
    discounted: list[dict[str, Any]] = []
    suggestions: dict[int, list[tuple[EvidenceRule, list[Evidence]]]] = defaultdict(
        list
    )
    for rule in rules.rules:
        evidence = _rule_evidence(corpus, rule)
        if not evidence:
            continue
        passed, reason = _satisfied(rule, evidence)
        if rule.role == "suggests":
            if passed:
                suggestions[rule.target].append((rule, evidence))
            continue
        entity = catalogue.entity(rule.target)
        if passed:
            findings.append(
                Finding(
                    rule,
                    entity,
                    tuple(evidence),
                    catalogue.modalities_of(entity.entity_id),
                )
            )
        else:
            discounted.append(
                {
                    "rule": rule.id,
                    "entity": entity.reference(with_type=True),
                    "reason": f"not established: {reason}",
                    "evidence": [item.to_json() for item in evidence],
                }
            )
    mentions = {item.key: item for item in detect_assay_candidates(root, catalogue)}

    candidates: dict[str, Candidate] = {}

    def add(candidate: Candidate) -> None:
        if candidate.reference in rejected and candidate.status != "rejected":
            candidate = replace(
                candidate,
                status="rejected",
                uncertainty="rejected during review",
                selectable=False,
            )
        existing = candidates.get(candidate.reference)
        order = [
            "rejected",
            "requires_verification",
            "suggested",
            "supported",
            "documented",
        ]
        if existing is None or order.index(candidate.status) > order.index(
            existing.status
        ):
            candidates[candidate.reference] = candidate

    for finding in findings:
        specific = _descendant_assays(catalogue, finding.entity)
        references = [_reference(catalogue, item)[0] for item in specific]
        for item in specific:
            reference, code = _reference(catalogue, item)
            evidence = list(finding.evidence)
            alternatives = tuple(ref for ref in references if ref != reference)
            if reference in mentions:
                status, uncertainty = "documented", ""
                mention = mentions[reference]
                evidence.append(Evidence("text", mention.term, mention.locations))
            elif item.entity_id in suggestions:
                status = "suggested"
                rule, extra = suggestions[item.entity_id][0]
                evidence.extend(extra)
                uncertainty = (
                    f"{rule.basis} This suggests {item.label} but does not confirm it."
                )
            elif len(specific) == 1 and item.entity_id == finding.entity.entity_id:
                status, uncertainty = "supported", ""
            else:
                status = "requires_verification"
                uncertainty = (
                    f"The evidence establishes {finding.entity.label} "
                    f"[{finding.entity.entity_type.value}] but not which of "
                    + ", ".join(entity.label for entity in specific)
                    + " the pipeline supports."
                )
            add(
                Candidate(
                    reference=reference,
                    entity=item,
                    registered_code=code,
                    status=status,
                    established_by=(finding.rule.id,),
                    evidence=tuple(evidence),
                    alternatives=alternatives if len(specific) > 1 else (),
                    uncertainty=uncertainty,
                    selectable=status in {"documented", "supported"},
                    paths=catalogue.paths(item.entity_id),
                )
            )
        documented = [
            item for item in specific if _reference(catalogue, item)[0] in mentions
        ]
        if (
            finding.entity.entity_type in ASSAY_TYPES
            and len(specific) > 1
            and not documented
        ):
            reference, code = _reference(catalogue, finding.entity)
            add(
                Candidate(
                    reference, finding.entity, code, "supported", (finding.rule.id,),
                    finding.evidence, tuple(references),
                    "A broader classification the evidence supports. More specific "
                    "registered assays exist; prefer them once confirmed.",
                    False, catalogue.paths(finding.entity.entity_id),
                )
            )  # fmt: skip
    # Explicit mentions outside any established domain still count.
    for reference, mention in mentions.items():
        if reference in candidates:
            continue
        resolved = catalogue.resolve_reference(reference)
        add(
            Candidate(
                reference, resolved.assay,
                resolved.registration.code if resolved.registration else None,
                "documented", ("explicit-mention",),
                (Evidence("text", mention.term, mention.locations),), (), "",
                True, resolved.paths,
            )
        )  # fmt: skip

    questions = []
    for finding in findings:
        specific = _descendant_assays(catalogue, finding.entity)
        open_ = [
            item
            for item in specific
            if candidates.get(_reference(catalogue, item)[0]) is not None
            and candidates[_reference(catalogue, item)[0]].status
            in {"requires_verification", "suggested"}
        ]
        decided = [
            item
            for item in specific
            if candidates.get(_reference(catalogue, item)[0]) is not None
            and candidates[_reference(catalogue, item)[0]].status == "documented"
        ]
        if len(open_) > 1 or (open_ and not decided and len(specific) > 1):
            terms = sorted({item.term for item in finding.evidence})[:6]
            questions.append(
                f"The pipeline processes {finding.entity.label} data "
                f"(evidence: {', '.join(terms)}). The repository does not establish "
                "which of "
                + ", ".join(
                    f"{item.label} ({_reference(catalogue, item)[0]})" for item in open_
                )
                + " it supports. Which does it support: one, several or all?"
            )
    ordered = sorted(
        candidates.values(),
        key=lambda item: (
            item.paths[0][-1].label if item.paths else "",
            item.entity.entity_id,
        ),
    )
    return AssayAssessment(
        rules_version=rules.version,
        vocabulary=catalogue.provenance.reference(),
        findings=tuple(findings),
        candidates=tuple(ordered),
        questions=tuple(questions),
        discounted=tuple(discounted),
        declared=declared,
    )
