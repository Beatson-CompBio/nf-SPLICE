# nf-splice architecture decision register

This file is the canonical register of architecture decisions for `nf-splice`.
Each numbered section is one independently reviewable decision.

This register is the source of truth for architecture. Implementation plans,
status notes, issue discussions, and implementation details must conform to the
Current decisions recorded here. They cannot override this register.

## ADR lifecycle

| Status | Meaning |
|---|---|
| Proposed | Draft decision awaiting approval. It may be edited freely. |
| Current | Approved decision governing the implementation. |
| Superseded | Historical decision replaced by the ADR named in `Superseded by`. |
| Rejected | Considered choice that was explicitly not adopted. |

After an ADR becomes Current, its decision text is historical. A changed choice
is recorded in a new ADR whose `Supersedes` field names the old ADR. The old
ADR's status and `Superseded by` field are then updated, but its original
decision is retained. Corrections that do not change the decision may be made
with an explanatory note.

`Source` identifies the project event or current artefact that caused the
decision to be recorded. The initial records use `Step 0 architecture baseline`.
Future records must identify the concrete implementation finding, review,
platform-contract change, or Current ADR that triggered the new decision.

## Decision index

| ID | Decision | Status | Superseded by |
|---|---|---|---|
| ADR-0001 | Maintain an append-only decision history | Current | — |
| ADR-0002 | Build an assisted authoring and maintenance tool | Current | — |
| ADR-0003 | Materialise the platform integration at repository-root `splice/` | Superseded | ADR-0021 |
| ADR-0004 | Use `nf-splice.yaml` as canonical authoring state | Superseded | ADR-0021 |
| ADR-0005 | Keep evidence, candidates, and decisions distinct | Current | — |
| ADR-0006 | Render only reviewed state and block affected unresolved layers | Current | — |
| ADR-0007 | Record generation provenance in `nf-splice.lock.json` | Superseded | ADR-0021 |
| ADR-0008 | Treat a recognised existing `splice/` tree as a returning workflow | Current | — |
| ADR-0009 | Inspect the complete tree and establish ownership per path | Current | — |
| ADR-0010 | Treat direct generated-file edits as drift requiring reconciliation | Current | — |
| ADR-0011 | Preserve reviewed decisions during rediscovery | Current | — |
| ADR-0012 | Make rendering deterministic and idempotent | Current | — |
| ADR-0013 | Require explicit, previewed, atomic, collision-safe writes | Current | — |
| ADR-0014 | Put CLI and TUI over one application core | Current | — |
| ADR-0015 | Separate static integration authoring from per-run analysis output | Current | — |
| ADR-0016 | Version authoring, bundle, pipeline, and generator independently | Current | — |
| ADR-0017 | Support the nf-core environment without depending on nf-core internals | Current | — |
| ADR-0018 | Support Python 3.10 through 3.14 | Current | — |
| ADR-0019 | Use compatible runtime framework release families | Current | — |
| ADR-0020 | Package with setuptools and a source layout | Current | — |
| ADR-0021 | Keep all static integration-harness state inside `splice/` | Current | — |

---

## ADR-0001: Maintain an append-only decision history

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-08-06 |
| Source | Step 0 architecture baseline |
| Scope | Architecture governance |
| Supersedes | — |
| Superseded by | — |
| Related | All ADRs |

### Decision

Record each canonical architectural choice as a separately numbered ADR in
this register. Once Current, a changed choice is expressed by a new ADR that
supersedes it; the earlier decision remains visible as history.

### Consequences

- Implementation can identify the exact active choice governing it.
- Incorrect assumptions can be replaced without rewriting project history.
- The index and bidirectional supersession metadata must be maintained.

---

## ADR-0002: Build an assisted authoring and maintenance tool

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-08-06 |
| Source | Step 0 architecture baseline |
| Scope | Product purpose |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0005, ADR-0006, ADR-0008, ADR-0011 |

### Decision

`nf-splice` will guide a developer through creating and later maintaining a
SPLICE platform integration. It will not claim to convert a pipeline safely in
one automatic operation.

### Consequences

- First-time creation and later review/update are equally supported workflows.
- Decisions that inspection cannot make safely require developer review.

---

## ADR-0003: Materialise the platform integration at repository-root `splice/`

| Metadata | Value |
|---|---|
| Status | Superseded |
| Date | 2026-08-06 |
| Source | Step 0 architecture baseline |
| Scope | Integration location and ownership |
| Supersedes | — |
| Superseded by | ADR-0021 |
| Related | ADR-0004, ADR-0007, ADR-0008, ADR-0009 |

### Decision

The tool will create and maintain the complete platform integration layer in a
`splice/` directory at the pipeline repository root. The directory is created
only by an explicit build after the required choices have been reviewed.

### Consequences

- Renderers and validators share one defined integration root.
- Root control files used to author and verify the integration remain distinct
  from the materialised platform layer.

---

## ADR-0004: Use `nf-splice.yaml` as canonical authoring state

| Metadata | Value |
|---|---|
| Status | Superseded |
| Date | 2026-08-06 |
| Source | Step 0 architecture baseline |
| Scope | State authority |
| Supersedes | — |
| Superseded by | ADR-0021 |
| Related | ADR-0005, ADR-0006, ADR-0007, ADR-0010, ADR-0011 |

### Decision

`nf-splice.yaml` will be the version-controlled canonical record of reviewed
authoring choices, rejected candidates, and unresolved decisions. Files under
`splice/` are materialisations and are not a competing source of truth.

### Consequences

- The developer's intent survives regeneration.
- Generated artefacts cannot silently redefine reviewed state.

---

## ADR-0005: Keep evidence, candidates, and decisions distinct

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-08-06 |
| Source | Step 0 architecture baseline |
| Scope | Domain model |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0002, ADR-0004, ADR-0006, ADR-0011 |

### Decision

Represent detected evidence, proposed candidates, and developer decisions as
different domain concepts. Evidence records its source, location, observed
value, confidence, and applicable repository revision.

### Consequences

- Detection never implies acceptance.
- Every inferred proposal remains explainable and reviewable.

---

## ADR-0006: Render only reviewed state and block affected unresolved layers

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-08-06 |
| Source | Step 0 architecture baseline |
| Scope | Generation eligibility |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0004, ADR-0005, ADR-0012, ADR-0013 |

### Decision

Renderers will consume reviewed canonical state, never raw inspection results.
A required unresolved or conflicting choice blocks generation of its affected
layer, without unnecessarily blocking unrelated reviewed layers.

### Consequences

- Scientific and platform-policy guesses cannot leak into generated files.
- Layer dependency and blocker models are required.

---

## ADR-0007: Record generation provenance in `nf-splice.lock.json`

| Metadata | Value |
|---|---|
| Status | Superseded |
| Date | 2026-08-06 |
| Source | Step 0 architecture baseline |
| Scope | Provenance and reproducibility |
| Supersedes | — |
| Superseded by | ADR-0021 |
| Related | ADR-0003, ADR-0004, ADR-0008, ADR-0010, ADR-0012, ADR-0016 |

### Decision

`nf-splice.lock.json` will record generator provenance, applicable repository
revision, selected evidence, managed artefact inventory, and content hashes.
It supports verification and reproduction; it is not canonical developer
intent.

### Consequences

- Later runs can identify previous output and detect drift.
- Lock format compatibility must be versioned and validated.

---

## ADR-0008: Treat a recognised existing `splice/` tree as a returning workflow

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-08-06 |
| Source | Step 0 architecture baseline |
| Scope | Integration maintenance lifecycle |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0002, ADR-0003, ADR-0007, ADR-0009, ADR-0010, ADR-0011 |

### Decision

When compatible authoring state, provenance, and structure establish that the
existing root `splice/` is managed by `nf-splice`, the tool will reopen it as a
continuation of the earlier authoring session. It will compare previous output,
current evidence, and reviewed state before proposing updates.

### Consequences

- Maintenance does not restart the integration from scratch.
- Compatibility and recognition rules must be explicit.

---

## ADR-0009: Inspect the complete tree and establish ownership per path

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-08-06 |
| Source | Step 0 architecture baseline |
| Scope | Inspection and ownership |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0003, ADR-0007, ADR-0008, ADR-0010, ADR-0013 |

### Decision

Before planning or building, inventory every path below an existing `splice/`.
Classify paths as expected unchanged, missing, drifted, malformed/incompatible,
unknown, or colliding. Establish tool ownership per path from compatible state,
provenance, and structure rather than from the directory name alone.

### Consequences

- Unknown content is reported and preserved.
- A problem blocks only writes for which a safe ownership boundary cannot be
  established.

---

## ADR-0010: Treat direct generated-file edits as drift requiring reconciliation

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-08-06 |
| Source | Step 0 architecture baseline |
| Scope | Drift management |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0004, ADR-0007, ADR-0008, ADR-0009, ADR-0013 |

### Decision

A managed artefact whose content differs from its recorded generated hash is
drifted. Preserve it until the developer explicitly adopts the meaningful
change into canonical state, where supported, or approves its replacement from
canonical state.

### Consequences

- Direct edits cannot disappear or silently become authoring decisions.
- Reconciliation must occur at the domain level, not inside a renderer.

---

## ADR-0011: Preserve reviewed decisions during rediscovery

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-08-06 |
| Source | Step 0 architecture baseline |
| Scope | State evolution |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0004, ADR-0005, ADR-0008 |

### Decision

Rediscovery may add or refresh evidence and candidates but will not overwrite
reviewed or rejected decisions. When changed evidence invalidates or conflicts
with a decision, mark it for renewed review and retain the reason.

### Consequences

- Routine maintenance preserves developer intent.
- Domain models must track evidence freshness and decision validity separately.

---

## ADR-0012: Make rendering deterministic and idempotent

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-08-06 |
| Source | Step 0 architecture baseline |
| Scope | Rendering |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0006, ADR-0007, ADR-0013, ADR-0016 |

### Decision

Identical reviewed state, applicable inputs, contract version, and generator
version will produce byte-equivalent integration artefacts. A second build with
no relevant changes produces no file changes.

### Consequences

- Serialisation, ordering, formatting, and templates form part of the tested
  renderer contract.
- Golden-file and second-build tests are required.

---

## ADR-0013: Require explicit, previewed, atomic, collision-safe writes

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-08-06 |
| Source | Step 0 architecture baseline |
| Scope | File mutation safety |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0006, ADR-0009, ADR-0010, ADR-0012 |

### Decision

Inspection and planning are read-only. A build is explicit, presents its
proposed file-level changes, writes atomically, and never silently replaces or
deletes conflicting or unknown content. No broad force option bypasses
ownership, drift, or collision checks.

### Consequences

- Partial or destructive bundle updates are prevented.
- Build services require path-level blockers and a transaction strategy.

---

## ADR-0014: Put CLI and TUI over one application core

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-08-06 |
| Source | Step 0 architecture baseline |
| Scope | Interface architecture |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0004, ADR-0005, ADR-0006, ADR-0012 |

### Decision

Typer and Textual will be thin clients of the same domain models and
application services. They will not implement separate inspection, review,
reconciliation, rendering, or validation rules.

### Consequences

- Equivalent CLI and TUI operations must produce identical canonical state and
  byte-equivalent artefacts.
- Interface tests can assert behaviour against shared service results.

---

## ADR-0015: Separate static integration authoring from per-run analysis output

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-08-06 |
| Source | Step 0 architecture baseline |
| Scope | Runtime boundary |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0003, ADR-0004, ADR-0006 |

### Decision

Generating runtime `analysis_output.json` is a separate operation that consumes
completed-run evidence and the static output contract. It does not mutate
static authoring state or rebuild the integration layer.

Terminology corrected on 2026-08-07 to reserve SPLICE platform vocabulary;
the operation boundary itself is unchanged.

### Consequences

- Static repository integration and per-run data have separate services and
  validation lifecycles.

---

## ADR-0016: Version authoring, bundle, pipeline, and generator independently

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-08-06 |
| Source | Step 0 architecture baseline |
| Scope | Versioning |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0004, ADR-0007, ADR-0008, ADR-0012 |

### Decision

Treat the `nf-splice.yaml` schema version, SPLICE bundle contract version,
pipeline version, and generator version as separate values with separate
compatibility rules. Unknown or incompatible versions fail explicitly.

### Consequences

- No version value may be reused as an implicit substitute for another.
- Migration boundaries must be designed per versioned contract.

---

## ADR-0017: Support the nf-core environment without depending on nf-core internals

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-08-06 |
| Source | Step 0 architecture baseline |
| Scope | Dependency boundary |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0002 |

### Decision

Support the Python environment used by the agreed nf-core tooling version, but
do not make nf-core implementation internals part of the `nf-splice`
architecture.

### Consequences

- Step 1 must verify installation coexistence in a clean environment.
- Integration with nf-core must use stable public boundaries or isolated
  adapters.

---

## ADR-0018: Support Python 3.10 through 3.14

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-08-07 |
| Source | Step 1 user requirement and package metadata review, 2026-08-07 |
| Scope | Python compatibility |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0017, ADR-0019, ADR-0020 |

### Decision

Support nf-splice on Python 3.10 through 3.14. Test coexistence with nf-core
4.0.2 on Python 3.10, the minimum version supported by both packages. Keep
nf-core tooling outside the nf-splice runtime dependency graph.

### Consequences

- Package metadata and CI define and enforce the supported Python range.
- Python 3.9 is not supported.
- nf-core coexistence is verified without coupling to nf-core internals.

---

## ADR-0019: Use compatible runtime framework release families

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-08-07 |
| Source | Step 1 dependency metadata review, 2026-08-07 |
| Scope | Runtime dependencies |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0014, ADR-0018 |

### Decision

Use Typer 0.27.x, Textual 8.x, Pydantic 2.x, and PyYAML 6.x as the initial
runtime framework families. These provide the CLI, TUI, model, and YAML
foundations within the supported Python range.

### Consequences

- Upper bounds prevent accidental major-version contract changes.
- Upgrading beyond these families requires compatibility evidence and a new or
  superseding ADR when the supported range or architecture changes.

---

## ADR-0020: Package with setuptools and a source layout

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-08-07 |
| Source | Step 1 packaging compatibility review, 2026-08-07 |
| Scope | Packaging |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0016, ADR-0018 |

### Decision

Use the PEP 517 setuptools build backend, declarative project metadata in
pyproject.toml, and a src/nf_splice package layout. Keep one package version
constant and expose it through both installed metadata and the CLI.

### Consequences

- Tests exercise the installed package instead of importing accidentally from
  the repository root.
- Build-backend compatibility is part of the Python support contract.
- Changing the backend or source layout is an architectural change.

---

## ADR-0021: Keep all static integration-harness state inside `splice/`

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-08-07 |
| Source | Post-Milestone B user architecture correction, 2026-08-07 |
| Scope | Integration location, authoring state, and generation provenance |
| Supersedes | ADR-0003, ADR-0004, ADR-0007 |
| Superseded by | — |
| Related | ADR-0008, ADR-0009, ADR-0010, ADR-0013, ADR-0015 |

### Decision

Keep every static file that nf-SPLICE adds to a pipeline repository as part of
its integration harness inside the repository-root `splice/` directory.

The canonical reviewed authoring state is `splice/nf-splice.yaml`. Generator
provenance and managed-file hashes will be recorded in
`splice/nf-splice.lock.json`; the lock remains JSON, not YAML. Generated
platform contracts and supporting integration files remain below the same
`splice/` root.

`nf-splice init` may therefore create `splice/` before generated bundle layers
exist. Canonical state remains distinct from generated materialisations by its
model and ownership rules, not by being stored outside the harness directory.

Existing repository-root `nf-splice.yaml` or `nf-splice.lock.json` files are
legacy state from the superseded layout. A later command may migrate recognised
compatible legacy state only through an explicit, previewed, collision-safe,
atomic operation. It must not silently move, replace, or delete either source
or destination content.

The separate per-run `analysis_output.json` remains outside the static pipeline
integration harness. It belongs to a completed run and continues to follow the
runtime boundary in ADR-0015.

### Consequences

- Repository inspection and returning-workflow recognition must classify
  `splice/nf-splice.yaml` and `splice/nf-splice.lock.json` as owned control
  files with their own validation rules.
- All authoring document reads and writes, CLI/TUI initialisation, status,
  configuration, rendering, and tests must use `splice/nf-splice.yaml`.
- Bundle provenance must use `splice/nf-splice.lock.json` without creating a
  self-referential content hash.
- The next delivery milestone must implement and test the location change and
  safe legacy reconciliation before adding further authoring layers.
- Public documentation and examples must show only the Current paths after the
  migration behaviour is available.
