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
