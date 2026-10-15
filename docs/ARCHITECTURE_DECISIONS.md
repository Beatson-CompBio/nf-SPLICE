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
| ADR-0015 | Separate static integration authoring from per-run analysis output | Superseded | ADR-0028 |
| ADR-0016 | Version authoring, bundle, pipeline, and generator independently | Superseded | ADR-0024 |
| ADR-0017 | Support the nf-core environment without depending on nf-core internals | Current | — |
| ADR-0018 | Support Python 3.10 through 3.14 | Current | — |
| ADR-0019 | Use compatible runtime framework release families | Current | — |
| ADR-0020 | Package with setuptools and a source layout | Current | — |
| ADR-0021 | Keep all static integration-harness state inside `splice/` | Current | — |
| ADR-0022 | Include developer-supplied provenance and execution configs unchanged | Current | — |
| ADR-0023 | Record v0.3.0 decisions incrementally with a traceability ledger | Current | — |
| ADR-0024 | Publish five engine-neutral workflow-bundle contract families with a release registry | Current | — |
| ADR-0025 | Reserve `manifest` and define SPLICE bundle and platform-unit vocabulary | Current | — |
| ADR-0026 | Edit drafts as restricted YAML 1.2 with comment-preserving three-way patches | Current | — |
| ADR-0027 | Classify outputs by SPLICE job, sample and run with free-text scientific labels | Current | — |
| ADR-0028 | Generate one analysis output per job from the embedded output catalogue | Current | — |
| ADR-0029 | Attribute review events publicly by label and keep contact details in a private local audit | Current | — |
| ADR-0030 | Make one YAML draft per layer the authoritative, file-first authoring source | Proposed | — |
| ADR-0031 | Review rich pipeline identity in `bundle.draft.yaml` with evidence kept distinct | Proposed | — |
| ADR-0032 | Own an engine-neutral input contract with one access policy per parameter | Proposed | — |
| ADR-0033 | Separate container sources, runtime variants and verified downloadable distributions | Proposed | — |
| ADR-0034 | Review one default execution profile with adopted or deterministically generated configs | Proposed | — |
| ADR-0035 | Validate, repair or generate the RO-Crate by review while preserving the root source | Proposed | — |

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
| Status | Superseded |
| Date | 2026-08-06 |
| Source | Step 0 architecture baseline |
| Scope | Runtime boundary |
| Supersedes | — |
| Superseded by | ADR-0028 |
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
| Status | Superseded |
| Date | 2026-08-06 |
| Source | Step 0 architecture baseline |
| Scope | Versioning |
| Supersedes | — |
| Superseded by | ADR-0024 |
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

---

## ADR-0022: Include developer-supplied provenance and execution configs unchanged

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-08-07 |
| Source | Milestone D pull-request review correction, 2026-08-07 |
| Scope | RO-Crate and execution-profile source authority |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0002, ADR-0005, ADR-0006, ADR-0012, ADR-0013, ADR-0017, ADR-0021 |

### Decision

Treat workflow provenance and execution configuration as developer-owned source
artefacts. nf-splice may validate, register, and copy these artefacts into the
`splice/` integration harness, but it must not invent their contents.

The only RO-Crate source is the regular file `ro-crate-metadata.json` at the
pipeline repository root. If it is absent, provenance configuration stops and
instructs the developer to generate it with the public nf-core command
`nf-core pipelines rocrate .`, then retry. nf-splice does not provide a minimal
internal generator, accept an arbitrary alternate path, or use a previously
materialised `splice/ro-crate-metadata.json` as source. After explicit review,
the root file is structurally validated and copied byte-for-byte to
`splice/ro-crate-metadata.json`; the root source is never modified.

Each selected execution profile must register exactly one explicitly chosen,
repository-local `.config` source outside `splice/`. Detection may offer
repository evidence, but it does not implicitly select even an unambiguous
source. The selected file is safety-checked and copied byte-for-byte to the
profile's path under `splice/configs/`; nf-splice does not concatenate sources,
add headers, or synthesise config content.

The developer must explicitly confirm `type`, `description`, `executor`,
`container_engine`, and `config_source` for each selected profile. Detected
values are review evidence and may prefill an interactive form, but the shared
core does not silently accept them as registration decisions.

The platform profile record uses the keys `id`, `name`, `description`, `type`,
`engine`, `executor`, `container_engine`, and `config`. The controlled `type`
vocabulary is `test`, `development`, and `production`; `engine` is `nextflow`;
executor values use Nextflow's public executor names; and container-engine
values use one canonical lower-case value per supported runtime. Both authoring
and inspection validate these vocabularies.

nf-splice, not the developer, assigns the profile `id`. It derives a stable,
filesystem-safe ID from the exact detected Nextflow profile name and a
reversible hexadecimal token of that name, so distinct source profile names
cannot collapse to the same platform ID. IDs remain stable when descriptions,
types, executors, or source config contents change.

There is no cardinality constraint by `type` or `executor`: any number of
platform-relevant profiles may be selected, including multiple profiles with
the same type and executor. Their generated IDs remain unique, and the required
description records the developer's distinction between otherwise similar
profiles.

### Consequences

- Missing provenance is a developer-action blocker, not a generation fallback.
- Source files remain reviewable in their native pipeline locations and can be
  regenerated or edited with their owning tools.
- The materialised RO-Crate and config files can be compared byte-for-byte with
  their reviewed sources.
- CLI and TUI review forms collect the platform registration values while
  keeping IDs out of developer input.
- Vocabulary changes require an explicit schema and compatibility review.

---

## ADR-0023: Record v0.3.0 decisions incrementally with a traceability ledger

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, section 0.3 |
| Scope | Architecture governance |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0001 |
| Implementation | `docs/RELEASE_0.3.0.md`, `docs/ARCHITECTURE_DECISIONS.md`, `scripts/check_staged_paths.py` |
| Tests | `tests/test_adr_governance.py`, `tests/test_dev_workspace.py` |

### Context

The 0.3.0 release changes public contracts, authoring authority, runtime
semantics, interfaces and integrations. ADR-0001 requires an append-only
register but does not say when records are written or how a reviewer proves
that each shipped feature has a governing decision and verification evidence.

### Decision

From 0.3.0 onwards every observable behaviour, public nomenclature, schema,
authoring-authority, runtime-semantics, security or integration change is
recorded as a new ADR **in the same commit** as its implementation, tests and
documentation. A record may be committed as Proposed while implementation is
in progress and becomes Current only when the implementation is complete and
tested. Formatting-only refactors do not need records.

Every record from ADR-0023 onwards carries two additional metadata rows,
`Implementation` (source paths) and `Tests` (test files), and the sections
Context, Decision, Alternatives rejected and Consequences. A Security and
privacy section is required whenever the change affects either.

`docs/RELEASE_0.3.0.md` holds the release ledger: one row per feature mapping
feature → ADR(s) → implementation files → tests → status. The automated
governance test validates the register index against each section, the
bidirectional `Supersedes`/`Superseded by` links, the required metadata and
sections of new records, and that every ledger row names existing ADRs,
existing implementation paths and existing test files. A release review fails
when a substantive requirement has no Current ADR and verification evidence.

Development of the release happens only inside the single local clone on a
local WIP branch. Every project-generated temporary file, cache, log, agent
note and local TUI session lives below the anchored, ignored
`/.nf-splice-local/` workspace (`scripts/dev-env.sh` routes tool caches there),
and `scripts/check_staged_paths.py` rejects staged development-only or
secret-bearing paths even when forcibly added. Production behaviour never
depends on that workspace existing.

### Alternatives rejected

- Writing ADRs retrospectively at release time: loses the rationale available
  while implementing and lets undocumented behaviour ship.
- A separate decision file per ADR: the existing single canonical register is
  already the reviewed source of truth (ADR-0001).

### Consequences

- Reviewers can audit each feature commit together with its decision.
- The ledger and register are machine-checked in CI, so missing traceability
  is a test failure rather than a review omission.

---

## ADR-0024: Publish five engine-neutral workflow-bundle contract families with a release registry

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, sections 2 and 0.4 (invariant 8) |
| Scope | Public contract identity and versioning |
| Supersedes | ADR-0016 |
| Superseded by | — |
| Related | ADR-0012, ADR-0015, ADR-0020, ADR-0023 |
| Implementation | `src/nf_splice/contracts/`, `src/nf_splice/cli.py`, `docs/schemas/`, `pyproject.toml` |
| Tests | `tests/test_contracts.py` |

### Context

ADR-0016 kept authoring-state, bundle-contract, pipeline and generator
versions apart, but nf-splice emitted five machine-readable JSON contracts
whose only versioning was an ad hoc `schema_version` in three of them. The
two JSON Schema documents carried no contract identity at all, consumers had
no formal definitions to validate against, and nothing mapped a tool release
to the contract revisions it emits.

### Decision

nf-splice publishes exactly five public **workflow-bundle contract families**,
identified by engine-neutral URIs in an owned namespace:

| Final artefact | Family identifier |
|---|---|
| `bundle.json` | `https://schemas.splice-data.io/workflow-bundle/bundle` |
| `inputs.schema.json` | `https://schemas.splice-data.io/workflow-bundle/inputs` |
| `outputs.schema.json` | `https://schemas.splice-data.io/workflow-bundle/outputs` |
| `components.json` | `https://schemas.splice-data.io/workflow-bundle/components` |
| `execution-profiles.json` | `https://schemas.splice-data.io/workflow-bundle/execution-profiles` |

The URIs are identifiers and planned documentation locations, not deployed
URLs; validation never performs a network request. No family identifier
contains a workflow-engine or tool name, so an independent generator for
another engine can emit the same revision.

Each family has its own revision, starting at `0.3.0`, and a packaged formal
definition (`src/nf_splice/contracts/data/schemas/<family>/<revision>.schema.json`,
mirrored byte-for-byte in `docs/schemas/<family>/v<revision>/schema.json`,
`$id` = `<family>/v<revision>/schema.json`). A family revision changes only
when that family's contract changes, never merely because the tool version
changes.

The two JSON Schema documents keep their standard `$schema` dialect and their
own pipeline-specific `$id` for instance validation; the family URI and
revision are carried separately in the `x-splice-contract` extension
(`id`, `version`, `generated_by`). The three data documents carry
`schema_id`, `schema_version` and `generated_by`.

A wheel-packaged, version-controlled registry
(`src/nf_splice/contracts/data/registry.json`) records every nf-splice release
explicitly: 0.1.0 emitted no family revisions (its legacy formats are listed
as companion formats), 0.3.0 emits revision 0.3.0 of all five. A later
release must add its own row even when no family changed. Other version
concepts stay distinct: pipeline version, the per-pipeline
`analysis_output_schema_version`, the lock format and the generator version
are never substitutes for a family revision.

`nf-splice schema list|show|validate|check` (all with `--json`) exposes the
registry offline. Data documents are validated against their family
definition; JSON Schema documents are first checked as schemas of their
declared dialect and then against the family definition of their SPLICE
extensions. A document without a declared family revision is reported as a
legacy document needing a version-aware migration, and an unknown revision
fails explicitly. `schema check --against OLD --family F` and
`nf_splice.contracts.breaking_changes` report removals, type/enum narrowing,
changed constants, closed objects and new requiredness.

### Alternatives rejected

- Generic identifiers such as `splice.inputs` or tool/engine-specific ones
  such as `nf-splice.inputs`: ambiguous and not engine-neutral.
- Putting the family URI in `$schema` or `$id` of the JSON Schema documents:
  that would corrupt standard JSON Schema dialect and instance identity.
- Tying every family revision to the tool version: forces consumer upgrades
  without a contract change.

### Consequences

- Consumers can validate every published contract offline with packaged or
  documented definitions and examples.
- Old consumers that require bundle `schema_version` `1.0` cannot read 0.3.0
  bundles without an adapter; the migration guide documents a staged rollout.
- Every future release must extend the registry, and contract definition
  changes require an explicit new revision with migration notes.

---

## ADR-0025: Reserve `manifest` and define SPLICE bundle and platform-unit vocabulary

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, section 0.5 and requirements 7-8 |
| Scope | Public nomenclature |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0015, ADR-0024 |
| Implementation | `src/nf_splice/vocabulary.py`, `src/nf_splice/inspectors/identity.py`, `docs/GLOSSARY.md` |
| Tests | `tests/test_vocabulary.py`, `tests/test_output_contracts.py` |

### Context

The SPLICE platform already uses `manifest` for a different concept, and the
platform's units `job`, `sample` and `run` have precise meanings that the
0.1.0 tool used inconsistently (`run` for workflow-wide outputs, run metadata
for job metadata). An audit found one SPLICE-owned use of the reserved word:
the private helper `_MANIFEST_BLOCK` in the Nextflow identity inspector.

### Decision

- SPLICE-owned nomenclature uses **bundle**, **bundle file index**,
  **contract registry**, **workflow job** and **platform run** with the
  meanings in `docs/GLOSSARY.md`; `nf_splice.vocabulary` carries the same
  glossary for code and agent tools.
- `manifest` is never used for the bundle, its index, the contract registry,
  schema identifiers, emitted keys, labels or public API names. The bundle
  family identifier ends in `/bundle` (ADR-0024).
- The literal Nextflow `manifest { ... }` scope and `manifest.<key>`
  assignments remain recognised inside the Nextflow identity parser only, as
  input evidence. Its helpers are renamed `_NEXTFLOW_METADATA_BLOCK` and
  `_NEXTFLOW_METADATA_DOTTED` without changing the regex token.
- An automated audit rejects the reserved word in every Python identifier,
  every string literal outside the Nextflow parser, the packaged contract
  definitions/registry and CLI help, while asserting the upstream syntax is
  still parsed. Later generated-artefact tests extend the audit to bundle
  README, lock, YAML companions and TUI labels.

### Alternatives rejected

- Replacing the token in the parser regex: identity discovery from real
  `nextflow.config` files would silently break.

### Consequences

- New code and documentation must use the glossary words; the audit fails CI
  otherwise.
- `.gitignore` template entries for Python packaging files are third-party
  conventions and are not SPLICE nomenclature.

---

## ADR-0026: Edit drafts as restricted YAML 1.2 with comment-preserving three-way patches

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, sections 10.2.1 and 10.4 |
| Scope | Draft syntax, editing and write safety |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0010, ADR-0012, ADR-0013, ADR-0019 |
| Implementation | `src/nf_splice/drafts/yamlio.py`, `src/nf_splice/drafts/patch.py`, `src/nf_splice/drafts/store.py`, `pyproject.toml` |
| Tests | `tests/test_drafts_infra.py` |

### Context

0.3.0 makes individual YAML drafts the editable authoring truth, shared by
developers' editors, the CLI, the TUI and agents. PyYAML implements YAML 1.1
(`on` becomes `true`, `01` becomes `1`, unquoted dates become timestamps),
loses comments on every rewrite and accepts duplicate keys. Rewriting a whole
draft from a model would discard developer edits and comments.

### Decision

- Drafts are parsed with `ruamel.yaml` (new runtime dependency family
  `ruamel.yaml>=0.18.10,<0.19`) in round-trip mode with YAML 1.2 core-schema
  semantics. A draft must be one JSON-compatible document: aliases, anchors,
  non-core or language tags, duplicate keys, non-string keys, NaN/infinity
  and unquoted timestamps are rejected with a line-addressed
  `DraftSyntaxError`. Unquoted YAML 1.1-ambiguous scalars produce warnings.
- New drafts are written from plain data with conservative quoting so YAML
  1.1 and 1.2 readers agree; repeated serialisation is byte-stable.
- Every mutation is a list of JSON-pointer `PatchOp`s whose `expected` value
  is the value observed when the edit was planned. Applying to the current
  file succeeds only where that base value is still present (or the planned
  value is already there), so non-overlapping concurrent edits are preserved
  and overlaps are reported as conflicts without any write. This is a
  three-way merge whose base travels with the patch; no copy of reviewed
  values is stored elsewhere.
- Patches are applied to the round-trip node tree, so comments and
  formatting of untouched content survive. Replaced values lose only their
  own comments.
- File writes are atomic (temporary file, fsync, `os.replace`), refuse
  symbolic links and paths outside `splice/`, create files only when absent,
  and compare the file's SHA-256 immediately before replacement
  (compare-and-swap); modification times are never trusted.
- Malformed drafts are never regenerated or overwritten; they are reported
  with their parse location until the developer fixes them.

### Alternatives rejected

- PyYAML with a custom resolver: still loses comments and needs a bespoke
  duplicate-key and tag guard.
- Storing a base copy of each draft for merges: a hidden second copy of
  reviewed values competing with the draft.
- Whole-file regeneration with mtime checks: silently discards edits.

### Consequences

- YAML-to-JSON compilation can promise parsed-JSON semantic equality and
  byte-stable repeated output, not byte equality between YAML and JSON.
- A new dependency must remain compatible with Python 3.10-3.14 in CI.

---

## ADR-0027: Classify outputs by SPLICE job, sample and run with free-text scientific labels

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, sections 5.2 and 5.2.1 (requirement 8) |
| Scope | Output contract semantics and nomenclature |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0024, ADR-0025, ADR-0028 |
| Implementation | `src/nf_splice/domain/outputs.py`, `src/nf_splice/inspectors/outputs.py`, `src/nf_splice/renderers/outputs.py`, `src/nf_splice/runtime/analysis_output.py`, `src/nf_splice/cli.py`, `src/nf_splice/interfaces/tui.py` |
| Tests | `tests/test_output_scopes.py`, `tests/test_output_contracts.py`, `tests/test_runtime.py`, `tests/test_authoring.py` |

### Context

0.1.0 used `run` for workflow-wide outputs, `library` for per-library
outputs and `run_metadata` for the whole workflow execution, contradicting the
SPLICE platform where a **run** is a file-level unit belonging to a sample and
the workflow execution is a **job**. Its `OutputCategory` and `OutputStage`
enums also imposed a central scientific vocabulary.

### Decision

- `OutputScope` is exactly `job`, `sample`, `run` (that order). `job` attaches
  to the workflow job; `sample` records carry `sample_id`; `run` records carry
  the platform `run_id` **and** their parent `sample_id`. `library` is never a
  published scope; `library_id` may remain descriptive metadata.
- New path placeholder `{run}` captures `run_id`; `{sample}` captures
  `sample_id`. A reviewed output may list `run` only if a pattern captures
  `{run}`, `sample` only if a pattern captures `{sample}`, and every pattern
  must resolve an owner for at least one listed scope.
- The runtime chooses each record's scope from what its matched pattern
  captures (`run` > `sample` > `job` within the reviewed scopes). A run's
  parent sample comes from the path or from sample metadata with a `run_id`
  column; an unresolved or contradictory parent is a blocking error. The
  generated schema enforces the same rules per record.
- Discovery suggests `job` for single workflow-wide files and `sample` for
  `{sample}` patterns. It never infers `run` from a filename, a library name
  or the engine execution identifier; only an explicit `{run}` binding
  suggests it.
- Legacy scopes are migrated by **source contract version**, never by string
  replacement: a 0.1.0 catalogue's `run` means `job`, `sample` stays
  `sample`, and `library` remains unresolved for explicit review (`run` only
  after a reviewed file-level identifier mapping).
- Category and stage are safe, non-empty free text (no control characters,
  at most 128 characters). Suggested labels are offered by interfaces;
  `job_report` replaces `run_report` as the suggested workflow-wide default.
  Optional per-category titles/descriptions are pipeline metadata, not a
  central mapping.
- Job metadata uses SPLICE names: top-level `job_id_short`/`job_id_long`
  (job identity is now required), `config_profile`, `execution_timestamp`
  and an engine-qualified `job_metadata` object (`engine`,
  `engine_execution_id`, `nextflow.session_id`, `nextflow.run_name`,
  `annotations`). `--job-metadata` replaces `--run-metadata`; the deprecated
  alias converts legacy fields explicitly and rejects `platform_run_id`, which
  cannot be reinterpreted without human clarification.

### Alternatives rejected

- Renaming `run` to `job` by global replacement: silently reinterprets legacy
  per-library data and new platform runs.
- Inferring a platform run from FASTQ mates or library names: not evidence of
  a platform file-level unit.
- Keeping scientific enums with an "other" escape hatch: still a gated
  vocabulary and forces harmonisation.

### Consequences

- 0.3.0 output contracts and runtime documents are not readable by consumers
  that expect the legacy scope meanings; the contract migration guide gives
  before/after payloads and a staged platform rollout.
- Generating `analysis_output.json` requires job identity.

---

## ADR-0028: Generate one analysis output per job from the embedded output catalogue

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, sections 5 and 5.1 (requirement 2) |
| Scope | Runtime boundary and output contract authority |
| Supersedes | ADR-0015 |
| Superseded by | — |
| Related | ADR-0024, ADR-0027 |
| Implementation | `src/nf_splice/renderers/outputs.py`, `src/nf_splice/runtime/analysis_output.py`, `src/nf_splice/contracts/data/schemas/outputs/0.3.0.schema.json` |
| Tests | `tests/test_output_scopes.py`, `tests/test_runtime.py`, `tests/test_output_contracts.py`, `tests/test_legacy_fixtures.py` |

### Context

ADR-0015 separated the per-execution `analysis_output.json` from static
authoring, which remains correct. However 0.1.0 runtime classification read
`outputs.yaml` while validating with `outputs.schema.json`, splitting
authority between two files, and the document was described as per run.

### Decision

- Generating `analysis_output.json` remains a separate operation that never
  mutates static drafts, final files or the lock. It produces **one document
  per completed job**, containing records at job, sample or run granularity.
- The output layer publishes exactly two files from one reviewed model:
  `outputs.yaml` (developer-readable, `catalogue_format_version: 0.3.0`) and
  the **existing** `outputs.schema.json`. No `outputs.json`, no second output
  JSON document and no editable JSON output draft exist.
- `outputs.schema.json` both validates the job document and carries the
  complete `x-output-catalog` (`catalog_version`,
  `analysis_output_schema_version`, pipeline identity, scope descriptions,
  categories and every output type with scope, entity type, format, path
  patterns, stage and labels). The runtime reads its catalogue only from
  there; for a 0.3.0 contract it never reads `outputs.yaml`.
- A contract declaring `x-splice-contract` must pass the outputs family
  validation; a corrupt or incomplete catalogue is an actionable error, never
  replaced by YAML. A contract without the declaration is read only as a
  recognised 0.1.0 contract (bundle schema `1.0` or no bundle): its embedded
  legacy catalogue is used when complete, otherwise the version-gated legacy
  `outputs.yaml` (vocabulary `1.0.0`). Legacy contracts keep their original
  semantics and produce byte-identical legacy documents.

### Alternatives rejected

- An additional `outputs.json` catalogue: a sixth output document that can
  drift from the schema.
- Silent YAML fallback for malformed 0.3.0 schemas: conceals contract
  corruption from ingestion.

### Consequences

- Platform and runtime consumers need only `outputs.schema.json`.
- `outputs.yaml` and the embedded catalogue are tested for semantic equality.

---

## ADR-0029: Attribute review events publicly by label and keep contact details in a private local audit

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, section 8 |
| Scope | Actor identity, accountability and privacy |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0005, ADR-0012, ADR-0023 |
| Implementation | `src/nf_splice/domain/audit.py`, `src/nf_splice/services/audit.py`, `src/nf_splice/cli.py` |
| Tests | `tests/test_audit.py` |

### Context

The platform needs to know who reviewed a bundle change and whether a human
or an agent proposed it, but shared repository files must not leak personal
contact data, and automation must not fail merely because Git identity is
unset.

### Decision

- Every explicit review or change produces a public-safe `ReviewEvent`:
  layer, action, affected JSON pointers, origin (`manual_cli`, `manual_tui`,
  `external_edit`, `agent_suggestion`, `agent_proposed_batch`, `automation`,
  `migration`, `discovery`), approval status, actor and approving actor
  **labels**, tool name/version, before/after content hashes, source
  revision and a UTC RFC 3339 timestamp captured once at the event. Actor
  labels are validated to contain no e-mail address. Rendering never adds
  timestamps, so builds stay deterministic.
- The public actor label comes from `--actor`, `NF_SPLICE_ACTOR`, a CI
  identity (recorded as automation), or `unattributed`. Git `user.name`/
  `user.email` are only an unconfirmed suggestion (`nf-splice audit identity`)
  and are never used implicitly.
- Optional private contact details are appended only to a user-local audit
  store (`NF_SPLICE_AUDIT_DIR`, default `$XDG_STATE_HOME/nf-splice/audit`)
  with owner-only directory/file permissions, keyed by a hash of the
  repository path and never inside the repository (except the ignored
  development workspace). Failure to write it is a warning, never an
  authoring failure. `nf-splice audit show` exports records redacted by
  default (paths, e-mails and secret-like values removed).
- An agent's proposal is distinguishable from human approval through origin,
  approval status and the separate `approved_by` label; unattended policy
  application is recorded as `automation_policy`, not as a human approval.
- Public maintainer contacts are a separate, opt-in bundle field (introduced
  with the identity layer); a local audit actor is never automatically a
  pipeline author or maintainer.

### Alternatives rejected

- Hashing e-mail addresses for publication: e-mail hashes are guessable and
  are not anonymisation.
- Requiring Git identity: breaks CI and first-time users.

### Consequences

- Reviewed changes remain attributable without publishing personal data.

### Security and privacy

- No secrets or e-mail addresses enter public events; redaction is applied
  to exports.

---

## ADR-0030: Make one YAML draft per layer the authoritative, file-first authoring source

| Metadata | Value |
|---|---|
| Status | Proposed |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, section 10 (requirements 3 and 6) |
| Scope | Authoring authority and storage |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0005, ADR-0006, ADR-0008, ADR-0010, ADR-0011, ADR-0013, ADR-0021, ADR-0026, ADR-0029 |
| Implementation | `src/nf_splice/layers/base.py`, `src/nf_splice/layers/bundle.py`, `src/nf_splice/layers/outputs.py`, `src/nf_splice/drafts/store.py` |
| Tests | `tests/test_layer_bundle.py`, `tests/test_layer_outputs.py`, `tests/test_drafts_infra.py` |

### Context

ADR-0021 made `splice/nf-splice.yaml` the single canonical authoring state.
Developers cannot edit the real artefacts directly, every interface must
round-trip through one monolithic object, and externally edited content has
to be "imported". 0.3.0 requires independent, directly editable drafts.

### Decision

- Each layer has exactly one authoritative editable draft below
  `splice/drafts/`: `bundle.draft.yaml`, `inputs.schema.draft.yaml`,
  `outputs.draft.yaml` (the only output draft, compiling to both
  `outputs.yaml` and `outputs.schema.json`), `components.draft.yaml`,
  `execution-profiles.draft.yaml`, `ro-crate-metadata.draft.yaml`, plus native
  `configs/<id>.draft.config`. The lock is generated only. New 0.3.0
  integrations never create `nf-splice.yaml`.
- YAML drafts carry an `x-splice-draft` marker (`layer`, `status: draft`,
  `format`), represent absence explicitly as `null`, and are created only
  when absent: discovery, the CLI, the TUI or an agent never overwrite an
  existing draft.
- A per-layer review sidecar `splice/drafts/.reviews/<layer>.review.json` records
  evidence, the hashes of evidence-seeded values, explicit confirmations,
  discovery candidates, conflicting evidence, review events and promoted file
  hashes. It never stores authoritative values; readiness is computed from
  the current draft bytes on every inspection.
- A seeded value is pending while the draft still holds exactly that value
  and no confirmation matches it. A developer's direct edit changes the value
  and therefore counts as authored; `confirm` records deliberate acceptance
  of an unchanged detected value. Pending values and unresolved conflicting
  evidence block promotion.
- All interface mutations are targeted three-way-merged patches (ADR-0026)
  applied only with explicit approval and recorded as review events
  (ADR-0029); a proposal can be planned and diffed without writing.
- Discovery candidates live in the sidecar under stable IDs with a status
  (`pending`, `accepted`, `rejected`, `merged`, `split`); rediscovery never
  changes a decided candidate, and an unknown candidate ID is an error.
  Reviewed outputs are appended to `outputs.draft.yaml` by stable key; JSON
  previews of the compiled files are derived and never written.

### Alternatives rejected

- Keeping `nf-splice.yaml` as a hidden store behind the drafts: two copies of
  reviewed values that can drift.
- Recording review status inside the drafts: clutters developer-edited files
  and makes direct edits error-prone.

### Consequences

- Status is Proposed until every layer, the promotion lifecycle and the CLI/
  TUI have moved to drafts; it then supersedes ADR-0021's authoring-state
  clause.

---

## ADR-0031: Review rich pipeline identity in `bundle.draft.yaml` with evidence kept distinct

| Metadata | Value |
|---|---|
| Status | Proposed |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, section 3 |
| Scope | Pipeline identity and descriptive metadata |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0005, ADR-0025, ADR-0029, ADR-0030 |
| Implementation | `src/nf_splice/domain/identity.py`, `src/nf_splice/inspectors/identity.py`, `src/nf_splice/layers/bundle.py` |
| Tests | `tests/test_layer_bundle.py`, `tests/test_vocabulary.py` |

### Context

0.1.0 reviewed only name, version, repository URL and release URL, and
derived the bundle id from the name on every render.

### Decision

- `PipelineMetadata` has a documented canonical field order: `id`, `name`,
  `version`, `engine`, `title`, `description`, `long_description`, `readme`,
  `repository_url`, `project_url`, `release_url`, structured `authors`
  (name, person/organisation, affiliation, ORCID, role), `funders` (name,
  award id/title, URL), structured `citation` (DOI, URL, text, CFF path),
  `licence`, `licence_url`, `documentation_url`, `support_url`,
  `engine_version_min`, `engine_versions_tested`, free-text `keywords`,
  `pipeline_type`, `modality` and `released_at`. Required for ingestion:
  `id`, `name`, `version`, `engine`, `repository_url`; a description is
  recommended. No ambiguous `github` alias exists.
- The `id` is derived once from the name when the draft is seeded and is
  stored; later name changes never re-identify the bundle.
- Evidence comes from the Nextflow metadata scope (including
  `nextflowVersion`, `description`, `doi`, `license` and `contributors`),
  Git remote/tags, `CITATION.cff`, the README title and the root RO-Crate.
  Unanimous evidence is seeded but unconfirmed; disagreeing evidence leaves
  the field null with a recorded conflict.
- Validation reports field-addressed issues: missing required fields,
  placeholders, invalid URLs/ORCIDs/DOIs, duplicate authors or funders,
  repository URL differing from the Git remote, a release URL not
  referencing the version, and a minimum Nextflow version contradicting
  `nextflowVersion`.
- Public `maintainers` contacts are opt-in and require
  `maintainers_publication_approved: true` before promotion.

### Alternatives rejected

- Choosing among conflicting evidence by source priority: silently decides
  facts the developer must review.

### Consequences

- Detached contracts receive the identity envelope from this one reviewed
  draft at compilation time.

---

## ADR-0032: Own an engine-neutral input contract with one access policy per parameter

| Metadata | Value |
|---|---|
| Status | Proposed |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, section 4 (requirement 5) |
| Scope | Input contract semantics, permissions and engine bindings |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0024, ADR-0026, ADR-0030 |
| Implementation | `src/nf_splice/layers/inputs.py`, `src/nf_splice/services/input_policy.py`, `src/nf_splice/domain/access.py` |
| Tests | `tests/test_layer_inputs.py` |

### Context

0.1.0 rendered a filtered copy of `nextflow_schema.json` containing only
user-configurable parameters, dropped `hidden`, rebuilt groups without their
`required` lists and assumed a single-string `type`.

### Decision

- `inputs.schema.draft.yaml` / `inputs.schema.json` is a SPLICE-owned JSON
  Schema 2020-12 document of submitted runtime parameter values, keeping
  nf-schema's virtual groups (`$defs.<group>` with group `required`,
  referenced from top-level `allOf`), nested objects, unions, conditional and
  all other standard keywords. Every runnable parameter appears exactly once;
  duplicate definitions across groups are blocking collisions.
- Nextflow `nextflow_schema.json` is imported as evidence by an adapter that
  copies every keyword verbatim (including `help_text`, `fa_icon`, `hidden`,
  `errorMessage`, `exists`, `mimetype`, `schema`, custom formats and unknown
  extensions). Documented mapping decisions: the dialect becomes 2020-12,
  draft-07 `definitions` become `$defs` with `$ref`s rewritten, array-form
  `items` becomes `prefixItems`, and missing `allOf` group references are
  generated. Lossless round-trip is tested on an nf-core-style fixture.
- SPLICE extensions: `x-splice-contract` and `x-splice-pipeline` (identity
  envelope, synchronised explicitly from `bundle.draft.yaml`),
  per-parameter `x-splice-access.editable_by` ⊆ {`user`, `platform`,
  `agent`}, presentation-only `x-splice-ui.visibility`, `x-splice-data.kind`
  for data references and `x-splice-source` engine bindings
  (`params.<name>` for Nextflow). Engine-specific names live only in
  `x-splice-source`.
- A parameter without a reviewed access policy blocks promotion; platform-
  and nobody-editable parameters remain in the contract. Legacy 0.1.0
  classifications migrate conservatively (user → `[user]`, platform and
  execution-environment → `[platform]`, hidden/unsupported → `[]` hidden).
- Enforcement is deterministic and service-side
  (`nf_splice.services.input_policy`): the principal comes from the calling
  platform, visibility never authorises a write, unchanged defaults are not
  changes, submissions are validated against the schema with format
  checking, data references are checked syntactically (allowed schemes, no
  embedded credentials, no filesystem or network probing; `exists`/MIME are
  annotations for the execution environment) and views are filtered per
  principal. Only the Nextflow binding adapter is implemented.
- Agents may propose access policies but cannot write them without a
  separate human approver. Secret-like parameters must not carry defaults.
- Upstream re-import is planned as the difference between the previous and
  current upstream projections and applied as a three-way merge onto the
  draft, so manual edits are never reset; overlaps block the import. The
  previous upstream document is retained in the review sidecar as evidence
  for that comparison.

### Alternatives rejected

- Separate schemas per principal: duplicates parameters and diverges.
- Trusting a role asserted inside the schema or request: privilege
  escalation.

### Consequences

- Platform UIs must filter fields at view time and keep validating advanced
  constructs on the backend.

### Security and privacy

- Permission checks cannot be bypassed by low-level service calls.

---

## ADR-0033: Separate container sources, runtime variants and verified downloadable distributions

| Metadata | Value |
|---|---|
| Status | Proposed |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, section 6 |
| Scope | Component inventory and container provenance |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0005, ADR-0024, ADR-0029, ADR-0030 |
| Implementation | `src/nf_splice/domain/components.py`, `src/nf_splice/inspectors/containers.py`, `src/nf_splice/inspectors/modules.py`, `src/nf_splice/layers/components.py`, `src/nf_splice/services/containers.py` |
| Tests | `tests/test_containers.py`, `tests/test_components.py` |

### Context

0.1.0 stored one `container_uri` per component and inferred its type from
URI prefixes, labelling most unmatched values `docker`. A Quay OCI reference
could therefore be presented as if a static image file could be downloaded.

### Decision

- Discovery records every container reference with its file/line and
  runtime condition. The nf-core ternary on `workflow.containerEngine ==
  'singularity'|'apptainer'` yields distinct Singularity/Apptainer and Docker
  sources; `withName` config overrides are recorded as additional sources;
  any other Groovy expression is kept as an unresolved expression, never
  evaluated. Raw values are preserved verbatim.
- References are classified (OCI registry, `docker://`, `oras://`, HTTPS
  static-image candidate, insecure HTTP, local image, unresolved,
  unsupported). A URL ending in `.img`/`.sif` is only a candidate.
- A reviewed container is one logical image with `source_images` per
  concrete runtime. Same-runtime alternatives, unresolved or unsupported
  references and conflicting versions require explicit resolution; selected
  sources must come from detected evidence. Container IDs keep the 0.1.0
  rule (`container-` + 12 hex of the SHA-256 of the primary, preferably
  Docker, reference) so unchanged legacy IDs stay stable; `legacy_ids`
  records explicit remappings.
- A `distribution` (HTTPS download URI, SHA-256, size, file name, `sif`/`img`
  format, Nextflow cache file name, source runtime) is recorded only by the
  verification operation, which downloads the image and checks HTTP status,
  content type, signature, size quota and checksum. A distribution whose
  checksum does not match a recorded verification is rejected as
  unverified. `require_downloadable_images` must be reviewed; when true a
  container without a verified distribution blocks promotion.
- `components.json` keeps `id`/`type`/`uri`: a verified distribution is
  published as its Singularity/Apptainer runtime with the download URI;
  otherwise the native Docker/OCI reference is published as `docker`. Native
  sources always remain in `source_images`, and `resolution.status` states
  `verified` or `resolved`.
- Network, materialisation and upload are explicit, opt-in operations with
  injectable transports: HTTPS only, no embedded credentials, no private,
  loopback, link-local, multicast or reserved targets (checked at every
  redirect hop), bounded streaming to temporary files and atomic placement.
  Materialisation uses an installed Apptainer/Singularity (never sudo or
  Docker) and leaves no partial file. Uploads go only to an operator-
  configured target (`NF_SPLICE_IMAGE_STORE_URL` with an
  `NF_SPLICE_IMAGE_STORE_ALLOWED_HOSTS` allowlist), reuse an identical object
  by digest and never overwrite an object with a different checksum. No
  organisation URL or credential is built in.
- The Nextflow cache file name follows the published Nextflow
  `SingularityCache.simpleName` rule (scheme stripped, `:`/`/` → `-`,
  `.img`/`.sif`). It is checked against a live Nextflow only by the opt-in
  `nextflow` integration test.

### Alternatives rejected

- Inferring runtime type from URI shape: mislabels OCI references as
  downloadable images.
- Accepting checksums typed into a draft: unverifiable placeholders.

### Consequences

- Ingestion can distinguish registry references from curl-able images.
- The real organisational object store has not been tested; it needs
  credentials and explicit authorisation.

### Security and privacy

- External URLs are untrusted (SSRF, redirect and quota protections); no
  credentials enter the bundle.

---

## ADR-0034: Review one default execution profile with adopted or deterministically generated configs

| Metadata | Value |
|---|---|
| Status | Proposed |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, section 9 |
| Scope | Execution profiles and configuration authoring |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0022, ADR-0030, ADR-0032 |
| Implementation | `src/nf_splice/layers/execution.py`, `src/nf_splice/inspectors/profiles.py` |
| Tests | `tests/test_layer_execution.py`, `tests/test_execution.py` |

### Context

ADR-0022 allowed only byte-identical copies of developer configs and had no
notion of a platform default profile.

### Decision

- `execution-profiles.draft.yaml` lists reviewed profiles (stable IDs as in
  0.1.0) and a separately reviewed `default_profile`; with at least one
  profile, exactly one default must be chosen explicitly and is published as
  `default_profile` plus a per-profile `default` flag. The default is not a
  claim that a cluster is reachable.
- Two explicit config routes per profile: `adopted` (a repository-local
  `.config` outside `splice/`, copied byte-for-byte) or `generated` (an
  editable native `splice/drafts/configs/<id>.draft.config` created once by a
  deterministic builder from reviewed settings and never regenerated over
  edits). Final configs drop the draft marker line.
- Generated configs always contain the two headings
  `// ***** User Pipeline Input Params *****` and
  `// ***** SPLICE Pipeline Input Params *****`, with sorted, escaped
  `params` blocks. User overrides must be user-editable parameters and
  platform overrides platform-only parameters according to the reviewed
  input contract; secret-like parameters are never written.
- A reviewable SPLICE Slurm production candidate is offered with
  operator-managed site parameters (`queue`, `clusterOptions`) emitted only
  as comments: no account, partition, path, credential or database URL is
  hard-coded.
- Safety scanning applies to both routes: embedded secrets, personal paths,
  literal HPC accounts, test/demo settings in production profiles and, for
  adopted configs or text outside the generated sections, overrides of
  user-editable parameters.

### Alternatives rejected

- Treating the first listed profile as default: silent policy choice.
- Generating configs on every build: discards developer edits.

### Consequences

- Site details are an operator concern recorded as `site_parameters`.

---

## ADR-0035: Validate, repair or generate the RO-Crate by review while preserving the root source

| Metadata | Value |
|---|---|
| Status | Proposed |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, sections 7 and 0.3 (ADR-0022 row) |
| Scope | Workflow provenance and integration-review provenance |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0022, ADR-0029, ADR-0030, ADR-0034 |
| Implementation | `src/nf_splice/layers/provenance.py` |
| Tests | `tests/test_layer_provenance.py`, `tests/test_provenance.py` |

### Context

ADR-0022 required the root RO-Crate to be copied byte-for-byte after a few
structural checks, so stale versions or template placeholders were published
unchanged and a pipeline without an RO-Crate could not be integrated.

### Decision

- The root `ro-crate-metadata.json` is analysed for RO-Crate 1.1 structure
  (context, object graph, unique `@id`s, metadata descriptor about `./`,
  `conformsTo`), Workflow RO-Crate conventions (`mainEntity` typed
  `ComputationalWorkflow`), placeholders, malformed ORCIDs and field-level
  differences from the reviewed identity (name, version, description,
  licence, workflow URL and credited authors), each with severity, crate
  value and reviewed value.
- `ro-crate-metadata.draft.yaml` records one reviewed strategy:
  `include` (allowed only without blocking differences; publishes the root
  bytes unchanged), `enriched` (a corrected copy of the root graph stored as
  YAML JSON-LD only if it round-trips losslessly) or `generated` (a minimal
  RO-Crate 1.1 + Workflow RO-Crate graph built from reviewed identity). The
  reviewed root hash is recorded; a later change to the root file makes the
  strategy stale until reviewed again. The root file is never modified;
  `nf-core pipelines rocrate .` may be run only by explicit request and only
  when no root file exists.
- Integration-review provenance is added as namespaced `#nf-splice`
  `SoftwareApplication` and `CreateAction` entities (instrument, result,
  optional source object with its SHA-256, reviewer by public label). The
  action's `endTime` is the approval time stored in the draft, so rebuilding
  produces identical bytes. Pipeline authors and integration reviewers stay
  distinct roles.

### Alternatives rejected

- Editing the developer's root RO-Crate in place.
- Timestamps at render time: non-deterministic builds.

### Consequences

- Together with ADR-0034 this replaces ADR-0022's "copy unchanged only"
  rule; ADR-0022 is superseded when these layers become Current.
