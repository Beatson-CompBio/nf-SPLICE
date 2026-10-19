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
| ADR-0006 | Render only reviewed state and block affected unresolved layers | Superseded | ADR-0061 |
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
| ADR-0021 | Keep all static integration-harness state inside `splice/` | Superseded | ADR-0030 |
| ADR-0022 | Include developer-supplied provenance and execution configs unchanged | Superseded | ADR-0034, ADR-0035 |
| ADR-0023 | Record v0.3.0 decisions incrementally with a traceability ledger | Current | — |
| ADR-0024 | Publish five engine-neutral workflow-bundle contract families with a release registry | Current | — |
| ADR-0025 | Reserve `manifest` and define SPLICE bundle and platform-unit vocabulary | Current | — |
| ADR-0026 | Edit drafts as restricted YAML 1.2 with comment-preserving three-way patches | Current | — |
| ADR-0027 | Classify outputs by SPLICE job, sample and run with free-text scientific labels | Current | — |
| ADR-0028 | Generate one analysis output per job from the embedded output catalogue | Current | — |
| ADR-0029 | Attribute review events publicly by label and keep contact details in a private local audit | Current | — |
| ADR-0030 | Make one YAML draft per layer the authoritative, file-first authoring source | Superseded | ADR-0061 |
| ADR-0031 | Review rich pipeline identity in `bundle.draft.yaml` with evidence kept distinct | Current | — |
| ADR-0032 | Own an engine-neutral input contract with one access policy per parameter | Superseded | ADR-0061 |
| ADR-0033 | Separate container sources, runtime variants and verified downloadable distributions | Superseded | ADR-0061 |
| ADR-0034 | Review one default execution profile with adopted or deterministically generated configs | Superseded | ADR-0059 |
| ADR-0035 | Validate, repair or generate the RO-Crate by review while preserving the root source | Superseded | ADR-0060 |
| ADR-0036 | Promote layers independently and publish the bundle through a recoverable transaction | Current | — |
| ADR-0037 | Migrate 0.1.0 authoring state into drafts explicitly and non-destructively | Superseded | ADR-0041 |
| ADR-0038 | Replace the dashboard with a guided, session-resumable Textual wizard over shared services | Superseded | ADR-0057 |
| ADR-0039 | Offer optional, provider-neutral agents that can only propose through deterministic tools | Superseded | ADR-0044 |
| ADR-0040 | Gate releases on a Python 3.10-3.14 matrix, packaging and repository hygiene | Current | — |
| ADR-0041 | Support only 0.3.0 contracts and remove pre-release 0.1.0 compatibility | Current | — |
| ADR-0042 | Trace output publication routes and assess contract validity, observed outputs and coverage separately | Current | — |
| ADR-0043 | Run optional external checkers only when installed, applicable and explicitly permitted | Current | — |
| ADR-0044 | Offer manual, AI-assisted and autonomous work as three policies over one deterministic session engine | Superseded | ADR-0058 |
| ADR-0045 | Govern agents with operation-level permissions, bound approvals and truthful attribution | Current | — |
| ADR-0046 | Keep provider-neutral skills canonical in the repository, packaged and loaded by the runtime | Current | — |
| ADR-0047 | Keep private authoring state in an ignored `.splice-local/` and publish only `splice/` | Current | — |
| ADR-0048 | Integrate in an isolated working copy and commit only the validated bundle locally | Current | — |
| ADR-0049 | Export deterministic, independently verified ZIP archives of the bundle or pipeline | Superseded | ADR-0060 |
| ADR-0050 | Select providers explicitly, classify their failures and keep credentials outside every project | Current | — |
| ADR-0051 | Use OpenAI through Sign in with ChatGPT for open-source apps and the Responses API | Current | — |
| ADR-0052 | Run Codex only through a locked-down app-server whose restrictions are tested | Current | — |
| ADR-0053 | Run OpenCode as a loopback server with deny-all permissions and a token-protected tool bridge | Current | — |
| ADR-0054 | Publish a consumer kit of agent and skill files for developers who build on bundles | Current | — |
| ADR-0055 | Declare typed assay capabilities from a pinned SPLICE modality vocabulary | Current | — |
| ADR-0056 | Discover assay capabilities from scientific evidence and require classification for ingestion readiness | Superseded | ADR-0069 |
| ADR-0057 | Make the six YAML drafts and native configs the authors' source of truth, seeded once and never gated on candidates | Current | — |
| ADR-0058 | Review every layer with deep, high-effort AI investigation, independently of its validation gate | Superseded | ADR-0063 |
| ADR-0059 | Keep profile metadata in YAML and configuration in native files; deliver images only on explicit approval | Current | — |
| ADR-0060 | Author one RO-Crate graph, enrich it with the bundle, and make the pipeline archive a Workflow RO-Crate | Current | — |
| ADR-0061 | State the authoring, access and image-provenance rules once for the file-first model | Current | — |
| ADR-0062 | State one lifecycle: drafts valid, published, classified and ingestion ready are separate facts | Current | — |
| ADR-0063 | Complete a layer review only with stage-specific evidence, an assessment of the draft and cited support | Current | — |
| ADR-0064 | Keep outputs and components pipeline-defined and classify uncovered routes by evidence | Superseded | ADR-0068 |
| ADR-0065 | Let agents assess, regenerate and check the RO-Crate through permission-controlled operations | Current | — |
| ADR-0066 | Settle the maintainer's four corrective decisions: route errors, private state, process components and image reuse | Superseded | ADR-0068 |
| ADR-0067 | Work in one persistent workspace with an AI dock, safe pauses, takeover and same-session resume | Current | — |
| ADR-0068 | Author the output catalogue; make route coverage an ingestion-readiness dimension and version analysis output independently | Current | — |
| ADR-0069 | Infer no science deterministically: import identity from exact keys and let people declare assays | Current | — |
| ADR-0070 | The container engine is optional profile metadata; authoring a bundle never needs a runtime | Current | — |
| ADR-0071 | One first-run journey: task-oriented help, a safe working copy, a capability-aware Welcome | Current | — |

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

> **Note (2026-10-17).** Candidates are advisory evidence; the authored draft is the decision, and no pending-candidate queue gates validation (ADR-0057).

## ADR-0006: Render only reviewed state and block affected unresolved layers

| Metadata | Value |
|---|---|
| Status | Superseded |
| Date | 2026-08-06 |
| Source | Step 0 architecture baseline |
| Scope | Generation eligibility |
| Supersedes | — |
| Superseded by | ADR-0061 |
| Related | ADR-0004, ADR-0005, ADR-0012, ADR-0013 |

### Decision

Renderers will consume reviewed canonical state, never raw inspection results.
A required unresolved or conflicting choice blocks generation of its affected
layer, without unnecessarily blocking unrelated reviewed layers.

### Consequences

- Scientific and platform-policy guesses cannot leak into generated files.
- Layer dependency and blocker models are required.

---

> **Note (2026-10-17).** An externally edited, valid draft is authored, reviewed content; a candidate's pending status alone never blocks (ADR-0057).

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

> **Note (2026-10-17).** Rediscovery now never changes an existing draft or native config at all, in every layer (ADR-0057).

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
| Status | Superseded |
| Date | 2026-08-07 |
| Source | Post-Milestone B user architecture correction, 2026-08-07 |
| Scope | Integration location, authoring state, and generation provenance |
| Supersedes | ADR-0003, ADR-0004, ADR-0007 |
| Superseded by | ADR-0030 |
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
| Status | Superseded |
| Date | 2026-08-07 |
| Source | Milestone D pull-request review correction, 2026-08-07 |
| Scope | RO-Crate and execution-profile source authority |
| Supersedes | — |
| Superseded by | ADR-0034, ADR-0035 |
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

> **Note (2026-10-17).** Deliberate whole-draft or section replacement with an expected sha256 (`replace_draft`) is authoring, not regeneration; the restricted-YAML and conflict rules apply to it (ADR-0057).

> **Note (2026-10-17).** Drafts and their atomic writes are confined to `.splice-local/drafts/` (ADR-0047), not `splice/`; ADR-0061 states the current authoring rules.

## ADR-0027: Classify outputs by SPLICE job, sample and run with free-text scientific labels

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, sections 5.2 and 5.2.1 (requirement 8) |
| Scope | Output contract semantics and nomenclature |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0024, ADR-0025, ADR-0028, ADR-0041 |
| Implementation | `src/nf_splice/domain/outputs.py`, `src/nf_splice/inspectors/outputs.py`, `src/nf_splice/renderers/outputs.py`, `src/nf_splice/runtime/analysis_output.py`, `src/nf_splice/cli.py`, `src/nf_splice/interfaces/tui/` |
| Tests | `tests/test_output_scopes.py`, `tests/test_output_contracts.py`, `tests/test_runtime.py` |

Correction 2026-10-15: the Implementation row now names the `interfaces/tui/`
wizard package that replaced `interfaces/tui.py` (ADR-0038), and the Tests row
names `tests/test_output_discovery.py`, which replaced the removed
monolithic-state `tests/test_authoring.py`; the decision is unchanged.
Correction 2026-10-18: output-candidate discovery was removed (ADR-0068), so
the Tests row no longer names `tests/test_output_discovery.py`; the decision
is unchanged.


Amended by ADR-0041 (2026-10-15): the version-gated reading of 0.1.0 scopes and the deprecated `--run-metadata` alias described below were removed; only 0.3.0 catalogues and `--job-metadata` are supported.

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
| Related | ADR-0024, ADR-0027, ADR-0041 |
| Implementation | `src/nf_splice/renderers/outputs.py`, `src/nf_splice/runtime/analysis_output.py`, `src/nf_splice/contracts/data/schemas/outputs/0.3.0.schema.json` |
| Tests | `tests/test_output_scopes.py`, `tests/test_runtime.py`, `tests/test_output_contracts.py` |


Amended by ADR-0041 (2026-10-15): the version-gated legacy runtime path described below was removed; an `outputs.schema.json` without `x-splice-contract` is rejected.

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

Amended by ADR-0045 (2026-10-15): agent origins are `agent_assisted` and `agent_autonomous`; autonomous decisions carry approval `agent_policy`.

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

> **Note (2026-10-18).** ADR-0067 renames the option and variable to `--user` and `NF_SPLICE_USER`; `--actor` and `NF_SPLICE_ACTOR` are removed. The label rules are unchanged.

---

## ADR-0030: Make one YAML draft per layer the authoritative, file-first authoring source

| Metadata | Value |
|---|---|
| Status | Superseded |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, section 10 (requirements 3 and 6) |
| Scope | Authoring authority and storage |
| Supersedes | ADR-0021 |
| Superseded by | ADR-0061 |
| Related | ADR-0005, ADR-0006, ADR-0008, ADR-0010, ADR-0011, ADR-0013, ADR-0021, ADR-0026, ADR-0029 |
| Implementation | `src/nf_splice/layers/base.py`, `src/nf_splice/layers/bundle.py`, `src/nf_splice/layers/outputs.py`, `src/nf_splice/drafts/store.py` |
| Tests | `tests/test_layer_bundle.py`, `tests/test_layer_outputs.py`, `tests/test_drafts_infra.py` |

Amended by ADR-0047 (2026-10-15): drafts live in `.splice-local/drafts/` (as `<layer>.draft.yaml`, with `inputs.draft.yaml` and `provenance.draft.yaml`) and review sidecars in `.splice-local/reviews/`; `splice/` holds published files only.

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

- Supersedes ADR-0021: every static harness file still lives below
  repository-root `splice/` and the lock remains `splice/nf-splice.lock.json`,
  but `splice/nf-splice.yaml` is no longer canonical state; it is read-only
  migration input (ADR-0037).

---

> **Note (2026-10-17).** The sidecars hold no authority: seeded drafts are populated and candidate status never gates them (ADR-0057).

## ADR-0031: Review rich pipeline identity in `bundle.draft.yaml` with evidence kept distinct

| Metadata | Value |
|---|---|
| Status | Current |
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
  `pipeline_type`, `modality` and `released_at` (amended by ADR-0055:
  `modality` is replaced by typed `assay_capabilities`). Required for ingestion:
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
| Status | Superseded |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, section 4 (requirement 5) |
| Scope | Input contract semantics, permissions and engine bindings |
| Supersedes | — |
| Superseded by | ADR-0061 |
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

> **Note (2026-10-17).** Imported parameters start with `editable_by: []` and hidden presentation, a valid reviewed policy rather than a missing one; readiness checks that indispensable inputs can be supplied (ADR-0057).

## ADR-0033: Separate container sources, runtime variants and verified downloadable distributions

| Metadata | Value |
|---|---|
| Status | Superseded |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, section 6 |
| Scope | Component inventory and container provenance |
| Supersedes | — |
| Superseded by | ADR-0061 |
| Related | ADR-0005, ADR-0024, ADR-0029, ADR-0030, ADR-0041 |
| Implementation | `src/nf_splice/domain/components.py`, `src/nf_splice/inspectors/containers.py`, `src/nf_splice/inspectors/modules.py`, `src/nf_splice/layers/components.py`, `src/nf_splice/services/containers.py` |
| Tests | `tests/test_containers.py` |


Amended by ADR-0041 (2026-10-15): the `legacy_ids` field was removed from `components.json` before revision 0.3.0 was published.

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
| Status | Superseded |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, section 9 |
| Scope | Execution profiles and configuration authoring |
| Supersedes | ADR-0022 |
| Superseded by | ADR-0059 |
| Related | ADR-0022, ADR-0030, ADR-0032 |
| Implementation | `src/nf_splice/layers/execution.py`, `src/nf_splice/inspectors/profiles.py` |
| Tests | `tests/test_layer_execution.py` |

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
| Status | Superseded |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, sections 7 and 0.3 (ADR-0022 row) |
| Scope | Workflow provenance and integration-review provenance |
| Supersedes | ADR-0022 |
| Superseded by | ADR-0060 |
| Related | ADR-0022, ADR-0029, ADR-0030, ADR-0034 |
| Implementation | `src/nf_splice/layers/provenance.py` |
| Tests | `tests/test_layer_provenance.py` |

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

- Together with ADR-0034 this supersedes ADR-0022's "copy unchanged only"
  rule while keeping its source-ownership and profile-ID rules.

---

## ADR-0036: Promote layers independently and publish the bundle through a recoverable transaction

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, sections 10.6, 3.2 and 0.4 (invariant 6) |
| Scope | Promotion, publication, lock and whole-bundle validation |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0009, ADR-0010, ADR-0012, ADR-0013, ADR-0024, ADR-0030 |
| Implementation | `src/nf_splice/services/lifecycle.py`, `src/nf_splice/renderers/bundle_index.py`, `src/nf_splice/inspectors/splice_tree.py` |
| Tests | `tests/test_lifecycle.py` |

### Context

0.1.0 replaced each file with an individual `os.replace`, so an interrupted
build could leave a mixed bundle that looked complete.

### Decision

- Layer readiness is computed from current draft bytes. A ready layer may be
  promoted to its final names while other layers remain drafts. The whole
  bundle (`bundle.json`, `README.md`, `nf-splice.lock.json`) is published
  only when every layer is ready.
- Writes are staged under `splice/.nf-splice-staging/`, verified, the
  existing files are backed up under `splice/.nf-splice-backup/`, a journal
  `splice/.nf-splice-publish.json` is written, and files are replaced with the
  lock and `bundle.json` last. Any failure restores the previous files and
  removes created ones; a leftover journal blocks further publication until
  `recover` restores the previous coherent release.
- Promotion never overwrites unknown or non-regular paths. A published file
  whose bytes differ from the hash recorded when it was promoted (review
  sidecar, or the lock for older bundles) is drifted: it is preserved and
  blocks promotion unless the reviewer names it explicitly for overwriting
  after reconciling. Updating an unchanged recognised file still requires
  `--replace-existing` after reviewing the diff.
- `bundle.json` 0.3.0 carries `schema_id`/`schema_version`/`generated_by`,
  the ordered reviewed identity, opt-in maintainers, the five-family
  `schemas` map, the unchanged six-entry `files` index (no `outputs.json`)
  and `default_execution_profile`. The lock (format 2.0) records generator,
  repository URL and informational revision, contract revisions, source
  hashes (input-schema evidence, RO-Crate source, adopted configs),
  RO-Crate strategy/transformation hashes and managed-file hashes; it never
  hashes itself or drafts. A lock differing only in the informational
  revision is not rewritten, so committing the bundle does not cause churn.
- Whole-bundle validation checks every family document against its
  contract, the `schemas` map, cross-file identity envelopes, the YAML/JSON
  output projection, forbidden artefacts, draft markers, lock hashes and
  source freshness, and warns about unpromoted draft changes. Bundle schema
  1.0 is reported as legacy needing migration.

### Alternatives rejected

- Per-file replacement without journal: partial bundles.

### Consequences

- Repeated publication with unchanged reviewed state writes nothing.

---

## ADR-0037: Migrate 0.1.0 authoring state into drafts explicitly and non-destructively

| Metadata | Value |
|---|---|
| Status | Superseded |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, section 14 |
| Scope | Legacy compatibility and migration |
| Supersedes | — |
| Superseded by | ADR-0041 |
| Related | ADR-0021, ADR-0027, ADR-0030, ADR-0032, ADR-0033 |
| Implementation | `src/nf_splice/services/migration.py`, `src/nf_splice/services/lifecycle.py` |
| Tests | `tests/test_migration.py`, `tests/test_legacy_fixtures.py` |

### Context

Existing integrations store reviewed decisions in `splice/nf-splice.yaml`
(authoring schema 1.0) with 0.1.0 output-scope and classification meanings.

### Decision

- `splice/nf-splice.yaml` is read-only migration input. A read-only preview
  lists the drafts that would be created and every transformed, defaulted,
  unmapped, permission-changing or blocking value. Applying requires
  approval, creates only absent drafts and sidecars (recording the source
  hash in `migrated_from`) and verifies the legacy file and published files
  are unchanged. The legacy file is never edited, moved or treated as
  current authority; `migrate-state` still relocates repository-root state.
- Identity values become developer-authored draft values with the 0.1.0
  name-derived `id`; new fields are seeded from evidence for review.
- Input classifications map conservatively (ADR-0032) onto a fresh import
  of `nextflow_schema.json`; reviewed type/description overrides are kept;
  parameters without a legacy decision are blockers.
- Output scopes migrate by source version: `run` → `job`, `sample` →
  `sample`; `library` → `run` only with an explicit reviewed mapping
  (`--map-library-to-run`, rewriting `{library}` to `{run}`), otherwise a
  blocker. `run_report` becomes the suggested `job_report`; other categories
  and stages migrate literally. Rejected candidates stay rejected.
- Components keep their 0.1.0 container IDs; the heuristic type of each old
  `container_uri` is reported for review and no distribution is assumed
  verified. Profiles keep IDs and adopted sources; a default must be chosen.
  Approved unchanged RO-Crate inclusion becomes strategy `include` and is
  re-analysed against the reviewed identity.
- Recognised 0.1.0 published files without recorded hashes are treated as
  tool-owned and may be replaced by a reviewed publication; the previous
  release stays usable until a new coherent release is published.

### Alternatives rejected

- Automatic in-place upgrade on first run: unreviewed reinterpretation.

### Consequences

- A migrated bundle needs the reported blockers resolved before publishing.

---

## ADR-0038: Replace the dashboard with a guided, session-resumable Textual wizard over shared services

| Metadata | Value |
|---|---|
| Status | Superseded |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, section 11 |
| Scope | Terminal user interface |
| Supersedes | — |
| Superseded by | ADR-0057 |
| Related | ADR-0014, ADR-0029, ADR-0030, ADR-0036, ADR-0041, ADR-0044 |
| Implementation | `src/nf_splice/interfaces/tui/`, `src/nf_splice/cli.py` |
| Tests | `tests/test_tui.py`, `tests/tui_helpers.py` |


Amended by ADR-0041 (2026-10-15): the Migration step was removed from the wizard.

Amended by ADR-0044 (2026-10-15): the welcome step offers manual, AI-assisted and autonomous work; Ctrl+A opens read-only Ask AI; sessions have their own views.

Amended by ADR-0047 (2026-10-15): wizard progress is kept in `.splice-local/sessions/wizard/` unless `NF_SPLICE_SESSION_DIR` is set.

### Context

The 0.1.0 dashboard showed every layer at once, wrote the monolithic
`nf-splice.yaml` and indexed candidates by cursor position.

### Decision

- `nf-splice tui` launches a guided wizard (package
  `nf_splice.interfaces.tui`): welcome (create / resume / inspect only),
  repository, migration, identity, inputs, outputs, components, execution
  profiles, provenance, drafts, readiness, build and done. A declarative
  step graph (`steps.py`) defines prerequisites and derives completion from
  a service-computed snapshot; visiting a step unlocks its dependants so a
  step may be deferred, while build stays locked until every layer is ready.
- Every view calls the shared file-first services with origin
  `manual_tui`; confirmed choices are targeted draft patches, never
  `nf-splice.yaml`. Service calls run in Textual thread workers; results
  are re-derived from disk after each action. Errors persist in the status
  line until a later success.
- Candidate tables use stable candidate IDs as row keys; inputs use
  keyboard toggles (u/p/g, v) staged until Save; outputs support
  accept/reject/mark+merge/split keys with an inline regex preview and free
  text categories with suggestions; components separate registry sources
  from verified downloads and require explicit network approval; profiles
  show generated config previews and a single default; provenance shows the
  field-level RO-Crate report; drafts list external edits and can open
  `$EDITOR`; readiness links to the step that fixes each blocker; build
  shows the plan diff and publishes explicitly; done shows validation and
  the equivalent CLI checks.
- Sessions (`WizardSession`) store only navigation, visited/deferred steps,
  unsaved form text and draft hashes, under `NF_SPLICE_SESSION_DIR` or the
  user cache, never inside `splice/`. `--no-session` disables them. Deleting
  a session loses no reviewed state; changed draft hashes are reported on
  resume. Inspect-only mode and read-only repositories never write.
- The CLI/TUI equivalence gate authors the same repository through both
  interfaces and requires identical parsed drafts and byte-identical
  published files. Reviewed text snapshots of every step (including empty
  and error states) are committed under `tests/snapshots/tui/`.

### Alternatives rejected

- Per-screen hard-coded routing: diverges from service readiness.

### Consequences

- Replaces the dashboard and its `nf-splice.yaml` equivalence test.

---

## ADR-0039: Offer optional, provider-neutral agents that can only propose through deterministic tools

| Metadata | Value |
|---|---|
| Status | Superseded |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, section 12 |
| Scope | AI integration, permissions and privacy |
| Supersedes | — |
| Superseded by | ADR-0044 |
| Related | ADR-0002, ADR-0005, ADR-0014, ADR-0029, ADR-0032, ADR-0038 |
| Implementation | `src/nf_splice/agents/`, `src/nf_splice/cli.py`, `src/nf_splice/interfaces/tui/screens/agent.py`, `docs/AGENTS.md`, `pyproject.toml` |
| Tests | `tests/test_agents.py` |

### Context

Developers want AI help with discovery and review, but generated content
must never become reviewed fact implicitly, and the tool must remain fully
usable without AI, credentials or network.

### Decision

- `nf_splice.agents` defines a small provider protocol (capabilities,
  cancellable streaming sessions, tool mediation) with no SDK import. Modes
  are `off` (default), `ask`, `suggest`, `draft` and `apply`.
- Agents see only the `AgentToolbox`: typed, schema-described read-only
  tools and `propose_*` tools over the same services as the CLI/TUI.
  Proposals are validated (three-way patch planning, reviewed-output
  validation, candidate existence) and stored as pending proposals; they
  never write files. A separate human approval (`agent approve`, wizard
  panel) applies a proposal with origin `agent_suggestion`, the agent as
  actor and the human as `approved_by`. Agents cannot approve their own
  proposals; `apply_approved_proposal` exists only for human-approved ones.
- Policy fails closed: tools outside the mode, unknown tools, paths outside
  the repository and unapproved applications are denied and audited
  privately. Network, image and publication operations are not exposed.
- The Claude Agent SDK provider (optional extra `nf-splice[claude]`) is the
  only remote provider in 0.3.0. It empties and denies the built-in tool set,
  loads no user/project settings, configures only the in-process nf-splice
  MCP server, and denies everything else through `can_use_tool` and a
  `PreToolUse` hook, with turn and budget limits. Remote disclosure needs
  explicit consent; no provider is selected silently.
- Offline CI uses a deterministic scripted provider and a fake SDK; a live
  test is opt-in (`live_agent`). Proposals persist outside the repository.

### Alternatives rejected

- Letting the model edit draft files directly: bypasses validation,
  attribution and approval.
- Relying on `allowed_tools` alone: it pre-approves tools but does not remove
  others.

### Consequences

- Manual and AI-assisted work are interchangeable at every step and produce
  identical drafts after approval.
- Live Claude behaviour depends on organisational account setup, documented
  in `docs/AGENTS.md`.

### Security and privacy

- No shell, file, network or upload capability is reachable by the model;
  tool results are redacted and bounded; consent precedes remote disclosure.

---

## ADR-0040: Gate releases on a Python 3.10-3.14 matrix, packaging and repository hygiene

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-15 |
| Source | nf-SPLICE 0.3.0 implementation specification, sections 1.2, 15.4 and 13 (CI row) |
| Scope | Continuous integration and packaging |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0017, ADR-0018, ADR-0019, ADR-0020, ADR-0023, ADR-0026, ADR-0039 |
| Implementation | `.github/workflows/ci.yml`, `pyproject.toml`, `.gitattributes`, `scripts/check_staged_paths.py` |
| Tests | `tests/test_packaging.py`, `tests/test_dev_workspace.py`, `tests/test_docs.py` |

### Context

0.1.0 CI tested only Python 3.10. 0.3.0 adds packaged contract data, a
stylesheet, a new runtime dependency (`ruamel.yaml`, ADR-0026), an optional
AI extra and committed byte-exact fixtures.

### Decision

- CI runs on every push to `main` (including direct merges), on pushes to
  `wip/**` review branches, on pull requests and on demand.
- CI runs the offline test suite, ruff, ruff format, mypy, the generated
  contract-reference check and the installed CLI on Python 3.10, 3.11, 3.12,
  3.13 and 3.14. Live Nextflow and live AI tests are markers that CI excludes.
- nf-core 4.0.2 coexistence stays tested on Python 3.10 (ADR-0018).
- A packaging job builds sdist and wheel, installs the wheel without the
  optional extra (checking that no AI SDK is imported) and separately with
  `[claude]`. `tests/test_packaging.py` checks the wheel and sdist contain
  the registry, the five definitions and the wizard stylesheet, and runs the
  CLI from the unpacked wheel.
- A hygiene job rejects tracked development-only or secret-bearing paths and
  verifies `/.nf-splice-local/` is ignored. `.gitattributes` keeps fixture
  bytes exact (no line-ending normalisation).
- The dev extra adds `pytest-asyncio` (Textual Pilot tests) and `setuptools`
  (offline `--no-isolation` builds). Runtime dependency families are
  unchanged apart from `ruamel.yaml`; the optional extra pins
  `claude-agent-sdk>=0.2.167,<0.3`.

### Alternatives rejected

- Testing only the minimum Python: misses newer-runtime regressions.

### Consequences

- CI cost grows with the matrix; failures are reported per interpreter.

---

## ADR-0041: Support only 0.3.0 contracts and remove pre-release 0.1.0 compatibility

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-15 |
| Source | Maintainer decision during review of the 0.3.0 branch |
| Scope | Supported versions, migration and legacy code |
| Supersedes | ADR-0037 |
| Superseded by | — |
| Related | ADR-0023, ADR-0027, ADR-0028, ADR-0033, ADR-0038 |
| Implementation | `src/nf_splice/cli.py`, `src/nf_splice/runtime/analysis_output.py`, `src/nf_splice/inspectors/splice_tree.py`, `src/nf_splice/services/lifecycle.py`, `src/nf_splice/contracts/data/registry.json` |
| Tests | `tests/test_state.py`, `tests/test_output_scopes.py`, `tests/test_contracts.py`, `tests/test_cli.py` |

### Context

nf-splice 0.1.0 was a pre-release test version. Its bundles were never used
in production, so the compatibility code built for them (the `migrate`
commands, repository-root state relocation, the version-gated legacy runtime,
legacy scope interpretation, the `--run-metadata` alias, the wizard's
Migration step, the single-file authoring model and the frozen 0.1.0
fixtures) protected no real users while adding code, tests and documentation
that new users and integrators had to read past.

### Decision

- nf-splice supports only the 0.3.0 contract revisions and lock format 2.0.
  Compatibility guarantees start at 0.3.0.
- All 0.1.0 compatibility is removed: `nf-splice migrate drafts`,
  `nf-splice migrate-state`, `--run-metadata`, the legacy catalogue and
  runtime paths, legacy scope interpretation, 0.1.0 input classifications,
  the wizard's Migration step, the 0.1.0 authoring-document model and its
  serialisation, recognition of 1.0 bundles and locks, and the 0.1.0 entry
  of the contract registry.
- `legacy_ids` is removed from the components 0.3.0 definition before that
  revision is first published.
- A document that does not declare a 0.3.0 contract is rejected with a
  message to rebuild it with nf-splice.

### Alternatives rejected

- Keeping migration code for test bundles: maintenance and documentation
  cost with no production users.
- Keeping only the runtime legacy path: the same cost for the same reason.

### Consequences

- Leftover test bundles must be rebuilt from their pipeline repositories
  with `nf-splice init` and a normal review.
- Specification scenarios S05 (legacy bundle migration) and S14 (scope
  migration) no longer apply; mixed job/sample/run granularity from S14
  stays covered by `tests/test_output_scopes.py`.
- ADR-0027, ADR-0028, ADR-0033 and ADR-0038 carry amendment notes.

---

## ADR-0042: Trace output publication routes and assess contract validity, observed outputs and coverage separately

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-15 |
| Source | Maintainer's three-mode agentic implementation instructions for 0.3.0, section 6 |
| Scope | Output discovery, examples and assessment |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0027, ADR-0028, ADR-0044 |
| Implementation | `src/nf_splice/inspectors/routes.py`, `src/nf_splice/inspectors/outputs.py`, `src/nf_splice/services/coverage.py`, `src/nf_splice/runtime/analysis_output.py`, `src/nf_splice/cli.py`, `tests/fixtures/multi-route-0.3.0/` |
| Tests | `tests/test_routes.py`, `tests/test_coverage.py`, `tests/test_layer_outputs.py` |

### Context

nf-splice does not run pipelines. A pipeline has alternative routes
(aligners, optional steps, conditional QC) and one completed run exercises
only some of them. A process `output:` declaration does not prove that a file
is published. The output catalogue must describe what the pipeline may
publish, while each job's `analysis_output.json` lists only what it did
publish.

### Decision

- A static route analyser separates declared from published outputs. It
  follows `publishDir` in processes, configuration `withName` selectors
  (regular expressions, aliases, qualified names) and the configuration's
  default rule, including nf-core's process-name idiom; applies `pattern`
  filters, `enabled` flags and `saveAs`; and records the `if`/`else`
  conditions on every invocation path from the entry workflow. Each
  published route has a status: `confirmed_from_code`, `inferred_unverified`,
  `unresolved` or `not_reachable`; declared-only outputs are
  `not_published`. Comments and strings never create routes.
- Output candidates come only from published routes, with the publication
  rule as evidence, per-sample captures for `meta` outputs and
  process-qualified keys where emit names collide.
- An example output (directory, saved listing or output index) is enumerated
  without following symbolic links or leaving its root, and each entry is
  classified, unclassified or ambiguous against the catalogue. Catalogue
  types an example lacks are `not_observed` and never a failure. Empty files,
  partial files and skipped links are reported as limitations.
- `nf-splice assess` reports three independent results: contract validity
  (the bundle validators), observed-output compatibility (per example,
  including a real `analysis_output.json` generated from observed paths and
  validated, with a nil-UUID placeholder job identity) and a coverage
  assessment (routes covered by the catalogue, excluded by review, not
  covered or unresolved). Coverage is never claimed complete; the statement
  names what static analysis cannot see.
- The catalogue's `optional` field keeps its reserved meaning; presence in a
  run is not required by the catalogue.

### Alternatives rejected

- Treating one example run as the catalogue: drops supported routes.
- Requiring every catalogue type in every run: invalidates normal runs.
- Running Nextflow to observe outputs: outside nf-splice's scope and
  permissions.

### Consequences

- Intermediates such as unpublished sort steps are no longer offered as
  output candidates; module metadata enriches descriptions instead.
- A multi-route fixture (STAR or HISAT2, optional Salmon, conditional QC,
  MultiQC, an unpublished samtools step) and a STAR-only example back the
  tests.

> **Note (2026-10-17, superseding the earlier note).** Outputs validation classifies uncovered routes: established ones are errors (`route_not_covered`), conditional and unresolved ones warnings (ADR-0064).

---

## ADR-0043: Run optional external checkers only when installed, applicable and explicitly permitted

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-15 |
| Source | Maintainer's three-mode agentic implementation instructions for 0.3.0, section 5 |
| Scope | Optional nf-core and Nextflow checks |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0017, ADR-0045, ADR-0042 |
| Implementation | `src/nf_splice/services/checks.py`, `src/nf_splice/services/coverage.py` |
| Tests | `tests/test_coverage.py`, `tests/test_agents.py` |

### Context

nf-core is not a runtime dependency (ADR-0017); CI only checks that nf-core
4.0.2 can be installed alongside. nf-core lint runs `nextflow config` and can
contact the network, so it is not a read-only check.

### Decision

- A checker registry detects nf-core and Nextflow by `PATH` lookup only.
  nf-core lint runs only for nf-core pipelines (`.nf-core.yml` or an
  `nf-core/` pipeline name), with nf-core 3.x or 4.x, Nextflow on `PATH`, and
  the `external_tools`, `run_nextflow` and `network` permissions granted.
- Results are `passed`, `passed_with_warnings`, `failed`, `error`,
  `not_applicable` or `not_run`, with the tool version, the command and the
  reason. A check that did not run is never reported as passed. nf-core's
  own version check is disabled.

### Alternatives rejected

- Bundling nf-core: a large dependency most users do not need.
- Running nf-core lint whenever it is installed: hides its side effects.

### Consequences

- Against nf-core 4.0.2 without Nextflow the check reports `not_run` with the
  reason; with Nextflow and the permissions it runs and its counts are
  recorded.

---

## ADR-0044: Offer manual, AI-assisted and autonomous work as three policies over one deterministic session engine

| Metadata | Value |
|---|---|
| Status | Superseded |
| Date | 2026-10-15 |
| Source | Maintainer's three-mode agentic implementation instructions for 0.3.0 |
| Scope | AI integration, sessions, CLI and wizard |
| Supersedes | ADR-0039 |
| Superseded by | ADR-0058 |
| Related | ADR-0014, ADR-0030, ADR-0036, ADR-0038, ADR-0045, ADR-0042, ADR-0046 |
| Implementation | `src/nf_splice/agents/engine.py`, `src/nf_splice/agents/stages.py`, `src/nf_splice/agents/state.py`, `src/nf_splice/agents/operations.py`, `src/nf_splice/agents/toolbox.py`, `src/nf_splice/agents/sandbox.py`, `src/nf_splice/agents/help.py`, `src/nf_splice/agents/protocol.py`, `src/nf_splice/agents/providers/`, `src/nf_splice/cli.py`, `src/nf_splice/interfaces/tui/screens/session.py`, `src/nf_splice/interfaces/tui/screens/ask.py` |
| Tests | `tests/test_agents.py`, `tests/test_agent_interfaces.py`, `tests/test_scenarios.py` |

Amended by ADR-0047 (2026-10-15): sessions live in `.splice-local/sessions/<id>/` with `session.json`, `events.jsonl` and `checkpoints/`; previews are staged in `.splice-local/staging/`.

### Context

Integrating a pipeline with SPLICE is mostly careful, repetitive review work:
reading Nextflow code, tracing outputs, confirming identity, choosing access
policies and profiles. An agent can do much of it, but people need different
amounts of control: some want to drive and ask questions, some want an agent
to propose each step and wait, and some want the work done unattended within
limits they set. All three must produce the same files and the same
validation as manual work.

### Decision

- nf-splice offers three interaction modes over one engine and one set of
  deterministic services:
  - **Manual**: the CLI and the wizard. *Ask AI* (`nf-splice ask`, Ctrl+A)
    answers one question with read-only tools; it never edits, stages or
    builds and starts no session.
  - **AI-assisted**: a persistent session. For each stage the agent stages
    exact operations, which run through the real services on a private copy
    of the repository so the person sees the diff and the validation outcome.
    Only the person's approval applies them; an objection starts an
    investigation and possibly a revised proposal; a question or silence is
    never approval.
  - **Autonomous**: after a person approves the scope, permissions and
    budgets, the agent applies routine decisions directly, stage by stage,
    without prompts. A stage that cannot be completed with evidence becomes a
    recorded blocker; independent stages continue; the final report is
    truthful about partial completion.
- The engine is a typed state machine over the stages discover, identity,
  inputs, outputs, components, execution profiles, provenance, cross-layer
  validation, build, verify and report. Each stage runs a bounded loop:
  observe, plan, propose or execute, validate, reflect. A stage is complete
  only when its deterministic gate passes (layer validation, the cross-layer
  publication plan, bundle validation); a model's statement never completes
  a stage. Retries need progress: an attempt that leaves the draft content
  and the issues unchanged ends the retries.
- Discovery and the build are proposed or executed deterministically, without
  a model. Approved operations run under a checkpoint of `splice/`; a failed
  operation restores it. A transaction marker makes an interrupted action
  roll back on the next load.
- Sessions persist atomically in a versioned format inside the repository's
  ignored `.nf-splice-local/agent/` workspace (with its own `.gitignore`), or
  under `NF_SPLICE_AGENT_DIR`. They record mode, stage records, proposals,
  approvals, objections, conversation, evidence, blockers, checkpoints, usage
  and the provider's conversation reference. Draft and source fingerprints
  detect external edits: affected stages reopen and stale proposals are
  withdrawn. A file lock stops two sessions changing the same drafts.
- Modes can be switched in any direction (`nf-splice session resume --mode`);
  the draft files, evidence and history carry over. Switching is refused
  while an action is being applied. Manual mode pauses the session.
- The provider protocol is turn-based and SDK-free: capabilities (remote,
  tool calling, streaming, cancellation, budgets, continuation), a session
  that runs turns with a tool invoker, and cancellation. Providers without
  structured tool calling are refused. Remote providers need explicit
  consent. The Claude Agent SDK adapter and an offline scripted provider are
  implemented; Codex and OpenCode adapters fit the same protocol and are not
  implemented.
- CLI: `nf-splice ask`, `nf-splice session start|status|list|approve|object|reply|ask|continue|pause|cancel|resume|report|rollback|tools`
  and `nf-splice skills list|show|export`. The wizard's welcome step offers
  the three ways of working; session views share state with the CLI.

### Alternatives rejected

- Renaming the previous ask/suggest/draft modes: they produced proposals
  only, so neither a conversation that executes approved work nor unattended
  integration was possible.
- A graph-orchestration framework: a typed stage machine covers branching,
  rollback, resumption and human checkpoints without tying the core to one
  provider.
- Letting a provider SDK edit files directly: bypasses validation,
  attribution and permissions.

### Consequences

- The previous propose-only agent commands are replaced by `ask` and
  `session`.
- Autonomous runs make policy-scoped, local, reversible draft edits without
  per-stage approval; ADR-0045 bounds and attributes them.
- Live provider behaviour depends on the provider account; offline tests use
  the scripted provider with the real engine and services.

---

## ADR-0045: Govern agents with operation-level permissions, bound approvals and truthful attribution

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-15 |
| Source | Maintainer's three-mode agentic implementation instructions for 0.3.0 |
| Scope | AI permissions, approvals, audit and privacy |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0029, ADR-0032, ADR-0044 |
| Implementation | `src/nf_splice/agents/permissions.py`, `src/nf_splice/agents/operations.py`, `src/nf_splice/agents/toolbox.py`, `src/nf_splice/domain/audit.py`, `src/nf_splice/layers/base.py`, `src/nf_splice/layers/inputs.py`, `src/nf_splice/services/audit.py` |
| Tests | `tests/test_agents.py`, `tests/test_audit.py`, `tests/test_layer_inputs.py` |

### Context

An agent that can apply changes needs limits that are finer than read versus
write, approvals that cannot be reused for something else, and records that
never present an agent's decision as a person's review.

### Decision

- Every operation declares one permission: `read`, `draft_edit`, `build`,
  `overwrite`, `external_tools`, `run_nextflow` or `network`. Sessions grant
  `read`, `draft_edit` and `build` by default; others are added explicitly
  (`--allow`). `install`, `publish_external`, `credentials` and
  `human_consent` can never be granted, and no operation needs them.
  Publishing maintainers' contact details is a `human_consent` decision.
- Each turn offers only the operations of its stage plus read operations;
  arguments are validated against JSON schemas; layer-scoped operations are
  limited to the stage's draft; tool-call, turn, time and spending budgets
  end a run safely.
- Paths are resolved inside the repository, never through `..`, absolute
  paths or symbolic links. Secrets-like files are never read; tool results
  are redacted and size-bounded. Repository text is returned as untrusted
  content, and the system prompt tells the agent not to follow instructions
  in it; no operation can change a session's permissions.
- An approval records the proposal, its operations' digest, the draft
  fingerprint, the person and the time. A proposal is stale, and cannot be
  approved, when drafts or pipeline sources change after it was made.
- Change origins are `agent_assisted` (applied after a person's approval,
  who is recorded as `approved_by`) and `agent_autonomous` (approval status
  `agent_policy`, no human approver). Every tool call is logged with its
  outcome in the session's `tools.jsonl`. Sandbox previews write no private
  audit records.

### Alternatives rejected

- A single "apply" permission: cannot separate a draft edit from a build,
  an overwrite or an external tool.
- Recording autonomous changes as approved by the person who started the
  run: misrepresents who decided.

### Consequences

- ADR-0029's origin list now reads `agent_assisted` and `agent_autonomous`.
- An assisting agent still cannot change parameter access without the
  person's approval of the stage (ADR-0032).

---

## ADR-0046: Keep provider-neutral skills canonical in the repository, packaged and loaded by the runtime

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-15 |
| Source | Maintainer's three-mode agentic implementation instructions for 0.3.0, section 9 |
| Scope | Agent instructions and skills |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0040, ADR-0044 |
| Implementation | `AGENTS.md`, `docs/AGENTS.md`, `skills/`, `src/nf_splice/agents/skills/`, `src/nf_splice/agents/skills.py`, `src/nf_splice/agents/prompts.py`, `pyproject.toml` |
| Tests | `tests/test_skills.py`, `tests/test_packaging.py`, `tests/test_docs.py` |

### Context

Agents need the same procedures whether they are nf-splice's embedded agent
or an external coding agent, and whatever their vendor. Markdown that no
runtime loads drifts and misleads.

### Decision

- The root `AGENTS.md` is the development contract for this repository;
  `docs/AGENTS.md` is the run-time agent contract.
- Four skills live in `skills/<name>/SKILL.md`: `nf-splice-authoring`,
  `nf-splice-output-discovery`, `nf-splice-validation` and
  `nf-splice-agent-operations`. Each covers when to use it, prerequisites,
  tools, workflow, verification gates, failure handling, evidence reporting
  and safety boundaries, using only implemented tools and commands.
- Byte-identical copies are packaged in `nf_splice/agents/skills/`. The
  engine puts the relevant skills into every provider turn's system prompt,
  so every provider uses the same procedures. `nf-splice skills export`
  copies them to the directory an external tool discovers, such as
  `.claude/skills` for Claude Code.
- Tests fail on drift between the copies, missing sections, tool names or
  values that do not exist in the code, unresolvable commands or links, and
  skills missing from the wheel.

### Alternatives rejected

- Vendor-specific skill directories as the source: contradictory copies.
- Loading skills through the Claude SDK's settings: requires enabling
  project settings, which the least-privilege configuration disables.

### Consequences

- Changing a skill means changing `skills/` and refreshing the packaged copy.

---

## ADR-0047: Keep private authoring state in an ignored `.splice-local/` and publish only `splice/`

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-15 |
| Source | Maintainer's release-completion and multi-provider instructions for 0.3.0, section 1 |
| Scope | Working-copy filesystem layout, private state and migration |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0026, ADR-0030, ADR-0036, ADR-0038, ADR-0044 |
| Implementation | `src/nf_splice/layout.py`, `src/nf_splice/drafts/store.py`, `src/nf_splice/layers/base.py`, `src/nf_splice/agents/state.py`, `src/nf_splice/agents/sandbox.py`, `src/nf_splice/services/migration.py`, `src/nf_splice/interfaces/tui/store.py`, `src/nf_splice/cli.py` |
| Tests | `tests/test_layout.py`, `tests/test_reference_fixtures.py`, `tests/test_lifecycle.py` |

### Context

Drafts, review sidecars and session state are private working material: they
can hold research details, rejected ideas and audit records. Keeping drafts in
`splice/drafts/` mixed them with the distributable bundle, and agent sessions
lived in a development folder name. The distributable must be clean, Git
must never track private state, and work must survive mode switches and
restarts.

### Decision

- Every integration working copy has two areas: `splice/` (lower case) holds
  only published, Git-trackable bundle files; `.splice-local/` holds all
  private state: `drafts/` (one `<layer>.draft.yaml` per layer, plus
  `configs/`), `reviews/`, `sessions/<id>/` (`session.json`, redacted
  `events.jsonl`, `checkpoints/`), `sessions/wizard/`, `cache/`, `staging/`
  and `migrations/`.
- Before nf-splice writes any private file it adds `/.splice-local/` to the
  copy's `.gitignore` (once, keeping existing rules, creating the file when
  absent) and refuses to continue if Git already tracks files there; a
  person removes them from the index with `nf-splice workspace untrack
  --yes`, which never rewrites history. A `.splice-local` symbolic link is
  refused.
- An entry whose name differs from `splice` or `.splice-local` only by case
  (such as `SPLICE/`) is refused, because it collides on case-insensitive
  filesystems.
- Earlier layouts (`splice/drafts/`, `splice/drafts/.reviews/`,
  `.nf-splice-local/agent/`) are moved by `nf-splice migrate`: `--check`
  lists every move and conflict, `--apply` backs up each file, copies it,
  verifies its SHA-256 and only then removes the originals (restoring
  everything on failure), and `--rollback` restores the backup. Targets are
  never overwritten. Until migration, drafts are not read over an earlier
  layout.
- Checkpoints and draft fingerprints cover `splice/`, `.splice-local/drafts/`
  and `.splice-local/reviews/`. Previews copy only the private drafts and
  reviews, never sessions or caches. Agents cannot read `.splice-local/`
  through source tools.
- Credentials are never kept in `.splice-local/` (see the provider ADRs).

### Alternatives rejected

- Committing drafts: publishes private review material and rejected ideas.
- Relying on `.gitignore` alone: an already-tracked folder stays tracked.

### Consequences

- Drafts are not shared through Git. People keep the working copy (or back
  up `.splice-local/`) until a bundle is finished; reproducible CI uses
  decision files and validates the committed `splice/`.

> **Note (2026-10-17).** The staged-path guard also rejects the repository-root `.splice-local/`, including force-added files (ADR-0066).

> **Correction (2026-10-18).** Implementation paths updated for the unified workspace (ADR-0067); the decision is unchanged.

---

## ADR-0048: Integrate in an isolated working copy and commit only the validated bundle locally

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-15 |
| Source | Maintainer's release-completion and multi-provider instructions for 0.3.0, section 2 |
| Scope | Source isolation, Git lifecycle and remote boundaries |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0013, ADR-0044, ADR-0045, ADR-0047 |
| Implementation | `src/nf_splice/services/source.py`, `src/nf_splice/services/gitops.py`, `src/nf_splice/agents/engine.py`, `src/nf_splice/agents/operations.py`, `src/nf_splice/cli.py` |
| Tests | `tests/test_source_git_export.py`, `tests/test_agents.py` |

### Context

Integration changes files in a pipeline repository. People must be able to
try nf-splice, alone or with an agent, without risking their original
checkout, uncommitted work or remote branches, and many pipelines are not
in Git at all.

### Decision

- `nf-splice source prepare` creates an integration copy before anything is
  changed: a local Git repository is cloned onto `nf-splice/integration-<name>`
  (uncommitted changes are reported and imported only with
  `--include-uncommitted`); a plain folder is copied without symbolic links,
  work or log files and initialised as a local repository whose import
  commit uses the person's Git identity (never an invented one); a Git URL
  is cloned with the person's own credentials. Destinations are new or
  empty, never inside the source or nf-splice's own checkout. Working in
  place needs `--in-place --yes`. The copy records its origin in
  `.splice-local/integration.json`.
- `nf-splice git status|diff|commit` review and commit locally. A commit
  contains only `splice/` and `.gitignore` (plus paths the person names),
  only after the published bundle validates, never `.splice-local/`, with
  the person's Git identity. Commits made by a session carry a
  `Prepared-with: nf-splice` trailer and no impersonated author.
- Pushing is separate and explicit (`nf-splice git push --remote NAME
  --yes`), checked with a dry run first. nf-splice never pushes, creates
  remote branches, forks or pull requests on its own; agents can never be
  given that permission (`publish_external`).
- Sessions gain a `commit` stage that runs only with the `git_commit`
  permission (an approval in assisted sessions) and is otherwise reported
  as skipped.

### Alternatives rejected

- A branch in the person's existing checkout: does not protect uncommitted
  work and changes their repository.
- Requiring a Git host account: unnecessary for local work.

### Consequences

- The final report states the local Git state and that nothing was pushed.

---

## ADR-0049: Export deterministic, independently verified ZIP archives of the bundle or pipeline

| Metadata | Value |
|---|---|
| Status | Superseded |
| Date | 2026-10-15 |
| Source | Maintainer's release-completion and multi-provider instructions for 0.3.0, section 6 |
| Scope | Delivery archives |
| Supersedes | — |
| Superseded by | ADR-0060 |
| Related | ADR-0036, ADR-0047, ADR-0048 |
| Implementation | `src/nf_splice/services/export.py`, `src/nf_splice/agents/engine.py`, `src/nf_splice/cli.py` |
| Tests | `tests/test_source_git_export.py`, `tests/test_agents.py` |

### Context

Bundles are handed to platform operators and collaborators who may not use
Git. An archive must contain exactly the validated files and nothing
private, and its integrity must be checkable.

### Decision

- `nf-splice export --archive-scope bundle|pipeline [--archive-output PATH]
  [--overwrite]` works in every mode through one service. `bundle` holds
  `splice/`; `pipeline` holds the copy's pipeline files (Git-tracked files in
  a Git copy, otherwise an explicit walk) plus `splice/` under a folder named
  after the pipeline. `.splice-local/`, `.git/`, work, results, caches,
  environment and secrets files are excluded by an explicit policy, and a
  file containing credential-like content stops the export.
- Archives are made only from a valid, current build, with sorted members,
  fixed timestamps and permissions, written to a temporary file and
  renamed. The default path is `.splice-local/exports/`, so a pipeline
  archive can never contain itself; existing archives are not replaced
  without `--overwrite`.
- The archive is reopened and verified: safe member names, exactly the
  expected member set, each member's SHA-256, no private or Git content, and
  a successful validation of the bundle extracted into a temporary folder.
  The archive's path, size and SHA-256 are reported.
- Sessions export a bundle archive in an `export` stage after verification.

### Alternatives rejected

- `zip -r` of the folder or relying on `.gitignore`: includes private and
  untracked data.

### Consequences

- An archive is not a commit, and a build is not a published pull request;
  reports state each separately.

## ADR-0050: Select providers explicitly, classify their failures and keep credentials outside every project

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-15 |
| Source | Maintainer's release-completion and multi-provider instructions for 0.3.0, sections 7, 8, 11 and 12 |
| Scope | Agent providers, credentials, provider command-line interface |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0044, ADR-0045, ADR-0051, ADR-0052, ADR-0053 |
| Implementation | `src/nf_splice/agents/providers/__init__.py`, `src/nf_splice/agents/providers/base.py`, `src/nf_splice/agents/providers/claude.py`, `src/nf_splice/agents/providers/check.py`, `src/nf_splice/credentials.py`, `src/nf_splice/agents/engine.py`, `src/nf_splice/cli.py` |
| Tests | `tests/test_provider_cli.py`, `tests/test_agent_interfaces.py`, `tests/test_agents.py` |

### Context

Four real providers (`claude`, `openai`, `codex`, `opencode`) and the
offline `scripted` provider share one engine. They differ in how people sign
in, where inference runs and who pays. Providers fail for many reasons:
some are worth retrying, others (exhausted credit, revoked sign-in) must
never be retried. A credential must never reach a pipeline repository, a log,
a commit or an archive.

### Decision

- A registry names the providers. Each adapter module is imported only when
  that provider is used or diagnosed, so manual mode needs no provider SDK.
- Selection is explicit: `--provider`, or the provider and model saved with
  `nf-splice provider select`. nf-splice never routes to another provider,
  model or billing route by itself. A session may switch provider or model on
  `nf-splice session resume --provider ... --model ...`; the session's own
  record supplies the context to a provider without continuation.
- Every adapter reports failures as a `ProviderError` with one of twelve
  kinds (`auth_required`, `invalid_credentials`, `consent_required`,
  `rate_limited`, `usage_exhausted`, `budget_exhausted`,
  `provider_unavailable`, `connection_lost`, `model_incompatible`,
  `permission_denied`, `failed_turn`, `cancelled`), with redacted vendor
  diagnostics and request ID. The engine retries only `rate_limited`,
  `provider_unavailable` and `connection_lost`, at most twice, honouring
  `Retry-After`, and only when the turn has not yet touched a tool;
  otherwise it pauses the session with the reason, so it can be resumed in
  any mode or with another provider.
- Usage is recorded per provider with its billing route. Cost is recorded
  only when a provider reports it (Claude's cumulative cost is counted as
  deltas) and is otherwise `not_reported`.
- Credentials (API keys, OAuth tokens) live in the user's configuration
  folder (`$NF_SPLICE_CONFIG_DIR`, else `$XDG_CONFIG_HOME/nf-splice`, else
  `~/.config/nf-splice`), owner-only and written atomically; never in a
  project or `.splice-local/`, never printed.
- `nf-splice provider list|doctor|models|select|auth|test` shows each
  provider's sign-in method, inference location and billing route, checks
  installation and credentials (`--online` contacts the provider), and runs
  a one-tool connection test only with `--allow-remote-model`.
- Claude uses a Claude Platform (Console) API key only, passed to the Agent
  SDK with a private `CLAUDE_CONFIG_DIR`; Claude.ai subscription login is not
  used, because Anthropic does not allow third-party products to offer it
  without approval (checked 15 October 2026). Plan API credits fund the key's
  Console organisation.

### Alternatives rejected

- Falling back to another provider or to metered billing when one fails:
  silently changes who pays and where data goes.
- Storing keys in the project or the session: they would be committed,
  archived or shared.
- Importing Claude Code's subscription login: not permitted for
  third-party products.

### Consequences

- A paused session states why it stopped and how to continue.
- Live provider behaviour is verified only by the opt-in tests and
  `nf-splice provider test`; CI uses fixtures and fakes.

## ADR-0051: Use OpenAI through Sign in with ChatGPT for open-source apps and the Responses API

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-15 |
| Source | Maintainer's release-completion and multi-provider instructions for 0.3.0, section 9 |
| Scope | OpenAI provider and sign-in |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0050, ADR-0052 |
| Implementation | `src/nf_splice/agents/providers/openai_auth.py`, `src/nf_splice/agents/providers/openai.py`, `src/nf_splice/agents/providers/http.py` |
| Tests | `tests/test_openai_provider.py` |

### Context

OpenAI's Sign in with ChatGPT for open-source applications (published
September 2026) lets eligible ChatGPT Plus and Pro users use their plan for
Responses API inference without an API key. It defines the OAuth flow, the
`chatgpt.tokens.use.direct` scope and the supported inference route.

### Decision

- Sign-in follows the documented flow: first registration through
  `dynamic_agent_client` with the application name `nf-splice` and a stable
  per-computer `ext_agent_host_id`; PKCE (S256), fresh state and nonce, a
  `127.0.0.1` loopback callback; the ID token's signature (OpenAI's JWKS),
  issuer, audience (the issued client ID), expiry and nonce are verified
  before anything is saved. Each issued client ID and verified identity is
  saved as one account; several accounts can be saved and one selected.
- Plan usage is enabled only when the scope was granted. Tokens refresh
  before expiry under a cross-process lock, refresh tokens rotate, terminal
  refresh errors require signing in again, and sign-out revokes.
- Inference uses only `POST /v1/responses` with `store: false` and
  `stream: true`. The model sees nf-splice function tools only; hosted tools
  are never requested and any other call is refused. A stream that ends
  without `response.completed` is a failure and nothing from it is applied.
  OpenAI's error codes, including the subscription-sharing ones, map to the
  typed errors; usage limits pause the session and point to ChatGPT
  Settings > Usage without guessing a reset time.
- API-key mode is a separate choice (`nf-splice provider auth openai --use
  api-key --yes`), never a fallback.

### Alternatives rejected

- Reading Codex's or ChatGPT's token files, or calling ChatGPT backend
  endpoints: not supported and not permitted.
- Server-side conversation storage (`store: true`): unnecessary; the engine
  keeps the record.

### Consequences

- The `openai` extra (PyJWT with cryptography) is needed for sign-in.
- Eligibility is decided by OpenAI per account; a model list is not proof
  of access, so `nf-splice provider test` runs a real turn.

## ADR-0052: Run Codex only through a locked-down app-server whose restrictions are tested

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-15 |
| Source | Maintainer's release-completion and multi-provider instructions for 0.3.0, section 9 |
| Scope | Codex provider |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0050, ADR-0051 |
| Implementation | `src/nf_splice/agents/providers/codex.py` |
| Tests | `tests/test_codex_provider.py` |

### Context

Codex brings its own shell, file editing, web search, plugins, skills and
subagents. nf-splice may expose Codex only if those cannot bypass its tools,
and only by Codex's documented protocol.

### Decision

- Codex runs as `codex app-server` over stdio with the documented
  Responses provider route for open-source apps: the person's Sign in with
  ChatGPT token (or the API key they chose) reaches it only as
  `ACCESS_TOKEN`. No Codex login is used.
- A private `CODEX_HOME`, an allowlisted environment, web search off,
  project instruction files ignored, no MCP servers, the native-tool
  features disabled, a read-only sandbox in an empty folder and ephemeral
  threads leave the per-turn dynamic nf-splice tools as the only callable
  tools. Every approval request is cancelled; user-input, elicitation and
  unknown requests are refused; a native tool item interrupts the turn and
  pauses the session.
- Only Codex 0.162.x, whose restrictions the real-binary test verifies, is
  enabled; other versions are reported unavailable. nf-splice never
  installs Codex.
- Threads are started per turn because dynamic tools are fixed when a
  thread starts; the engine supplies its session summary instead of a
  provider continuation.

### Alternatives rejected

- Relying on the system prompt to keep Codex to nf-splice tools: not a
  restriction.
- The app-server's `chatgptAuthTokens` login: marked for OpenAI internal
  use only.

### Consequences

- A new Codex release must be verified with the real-binary test before
  `SUPPORTED` is widened.

## ADR-0053: Run OpenCode as a loopback server with deny-all permissions and a token-protected tool bridge

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-15 |
| Source | Maintainer's release-completion and multi-provider instructions for 0.3.0, section 10 |
| Scope | OpenCode provider |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0050 |
| Implementation | `src/nf_splice/agents/providers/opencode.py`, `src/nf_splice/agents/providers/mcp_bridge.py` |
| Tests | `tests/test_opencode_provider.py` |

### Context

OpenCode is an intermediary over model providers the person configures,
cloud or local. Its server API also offers shells, terminals and file
writing to authenticated clients, and its agents have native tools.

### Decision

- nf-splice launches `opencode serve` on `127.0.0.1` with a random server
  password, project configuration, model-catalogue fetching, auto-update and
  file watching disabled, an empty private folder and an allowlisted
  environment (provider keys only when named in `NF_SPLICE_OPENCODE_ENV`),
  or attaches to a loopback server; remote addresses are refused.
- Each turn registers a loopback MCP bridge with a fresh bearer token and
  code mode off, and creates a session whose permission ruleset denies
  everything except `nfsplice_*`. Permission requests are rejected; any other
  tool succeeding stops the turn and pauses the session.
- Models come from OpenCode's own catalogue (`nf-splice provider models
  opencode`); a model that cannot call tools is refused. A loopback
  endpoint is classified local (no remote-model consent and no cost); any
  other or unknown endpoint is remote.
- Only OpenCode 2.0.x (the `permissions` API) is enabled; 1.x is reported
  unavailable. nf-splice never installs OpenCode, packages or models.

### Alternatives rejected

- Exposing nf-splice tools through OpenCode plugins: code inside OpenCode
  rather than behind nf-splice's own toolbox.
- Trusting a server URL as evidence that inference is local.

### Consequences

- The real-server test proves, through a recording proxy, that a local
  model run makes no outbound connection.

## ADR-0054: Publish a consumer kit of agent and skill files for developers who build on bundles

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-16 |
| Source | Maintainer request: give developers of ingestion, the SPLICE database, web interfaces and data explorers agent and skill files for the bundle contracts |
| Scope | Documentation for bundle consumers |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0024, ADR-0027, ADR-0028, ADR-0046 |
| Implementation | `bundle-consumer-kit/`, `scripts/build_consumer_kit.py`, `docs/CONTRACTS.md` |
| Tests | `tests/test_consumer_kit.py`, `tests/test_docs.py` |

### Context

Developers who build on bundles (ingestion and the SPLICE database, web
interfaces, data explorers, job launchers) never install nf-splice. Their
coding agents need the structure, the meaning of each key and value, which
fields matter for which component, and the versioned definitions to
validate against. The nf-splice skills (ADR-0046) teach authoring a bundle,
which is a different audience.

### Decision

- A self-contained `bundle-consumer-kit/` folder holds a drop-in
  `AGENTS.md`, five role skills (`splice-bundle-contracts`,
  `splice-bundle-ingestion`, `splice-analysis-output`, `splice-web-ui`,
  `splice-job-launch`) in the common `SKILL.md` format, copies of the formal
  definitions by revision, a complete example bundle and a real
  `analysis_output.json`.
- The definitions and examples are generated by
  `scripts/build_consumer_kit.py` from `docs/schemas/` and from nf-splice's
  own services run on the multi-route fixture, and checked for drift. The
  written guidance is checked too: every key path a skill names must exist
  in the definitions, and the examples must validate with plain JSON Schema
  validators, as a consumer would use them.
- The kit is not packaged in the nf-splice wheel and is not loaded by
  nf-splice's agents; consumers copy it into their own repositories.
- Writing the kit showed that the path-pattern reference was incomplete;
  `docs/schemas/analysis-output.md` and `fields.yaml` now state the regular
  expression dialect, every placeholder and how to use the patterns from
  JavaScript.

### Alternatives rejected

- Pointing consumers at `docs/schemas/` alone: correct, but not shaped for
  roles or for coding agents, and it says nothing about what each component
  needs.
- Shipping the kit through `nf-splice skills export`: consumers do not
  install nf-splice.

### Consequences

- A contract change must regenerate the kit
  (`python scripts/build_consumer_kit.py`) and update any skill whose keys
  changed; the tests fail until it does.
- Each nf-SPLICE release's kit covers the contract revisions that release
  writes; new revisions add folders under `schemas/` beside the old ones.

## ADR-0055: Declare typed assay capabilities from a pinned SPLICE modality vocabulary

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-16 |
| Source | Maintainer's assay and modality vocabulary task for 0.3.0 (16 October 2026); SPLICE platform seed data `modality_entities.csv`, `modality_relationships.csv`, `Modalities.csv` |
| Scope | Bundle identity contract, vocabulary catalogue, authoring in all three modes |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0024, ADR-0031, ADR-0044, ADR-0045, ADR-0054 |
| Implementation | `src/nf_splice/catalogue/`, `scripts/build_assay_catalogue.py`, `src/nf_splice/domain/identity.py`, `src/nf_splice/layers/bundle.py`, `src/nf_splice/services/lifecycle.py`, `src/nf_splice/renderers/bundle_index.py`, `src/nf_splice/agents/operations.py`, `src/nf_splice/agents/engine.py`, `src/nf_splice/interfaces/tui/pages/assays.py`, `src/nf_splice/cli.py` |
| Tests | `tests/test_assay_capabilities.py`, `tests/test_tui.py`, `tests/test_consumer_kit.py` |

### Context

A pipeline can process several assays, and the SPLICE platform classifies
assays in a vocabulary DAG: modality, modality subtype, assay type and assay
method, below a root. The platform's registrations (its `Modalities` table,
such as `polya_rnaseq`) name assay entities, not top-level modalities, and
their `current` flag describes one deployment. A single free-text
`pipeline.modality` could not express several assays, invited calling an
assay a modality, and could not be checked.

### Decision

- **Catalogue.** nf-splice packages a snapshot of the vocabulary
  (`src/nf_splice/catalogue/data/assay-vocabulary.json`), compiled by
  `scripts/build_assay_catalogue.py` from the platform's seed files with
  every identifier, label, type, alias, status, edge and registration exactly
  as the source states it, pinned by a content digest and the source files'
  SHA-256. The raw sources are not committed. Its version is independent of
  the package, the contracts and the pipeline.
- **One resolver** (`Catalogue`) serves the CLI, the wizard, the agents and
  the bundle compiler. It validates the graph (broken edges, cycles, assays
  that reach no modality), keeps every path from an assay to every modality,
  never invents a level, and rejects unknown codes, non-assay entities,
  duplicates, mismatched labels or types, ambiguous names and caller-supplied
  accession identifiers with stable error codes.
- **Sources.** The packaged snapshot is the default. An API-backed source
  (the platform's `/modality-entities`, `/modality-relationships`,
  `/modalities`) checks every field, refuses conflicts with the pinned
  snapshot unless explicitly reconciled, reports additions as a stale
  snapshot, keeps accession identifiers only when the API supplies them, and
  falls back to the snapshot only when asked, saying so in its provenance.
- **Contract.** Revision 0.3.0 is unreleased, so it is changed in place:
  `pipeline.modality` is removed; `pipeline.assay_capabilities` lists typed
  capabilities (`kind`, `registered_code` for registered assays, `assay` with
  its exact `entity_type`, `assay_types`, `modality_subtypes`, `modalities`,
  `paths`); top-level `assay_vocabulary` names the snapshot and is required
  with capabilities. Bundles carry no accession, `modality_id` or `current`.
- **Authoring.** `bundle.draft.yaml` keeps only reviewed references
  (registered code or `entity:<id>`) with `evidence` (`asserted`,
  `documented`, `detected`), a rationale and sources. Labels, hierarchy and
  paths are derived on build and re-verified by `nf-splice validate`. Only a
  person may assert a capability without evidence. Generic `patch_draft` and
  `set_identity` cannot write capabilities.
- **Evidence.** Candidates are proposed only from explicit mentions of an
  assay's label, alias or code, with locations. File types and tools never
  establish an assay.
- **Legacy.** A free-text `modality` in a draft or bundle is reported, never
  converted.
- **Modes.** The identity stage offers the assay tools and a dedicated skill
  to every provider. In autonomous mode, a stage where the agent records a
  blocker stays open even when validation passes, so an undecided optional
  field becomes a resumable decision rather than a silent gap.

### Alternatives rejected

- A list of modality names: loses the assay, its type and the multi-parent
  structure, and repeats the poly(A)-as-modality error.
- Storing labels and paths in the draft: lets a person or model publish
  mismatched combinations; they are derived instead.
- Deriving accession identifiers from `modality_id` or `entity_id`: not
  authoritative.
- Filtering declarable assays by the deployment's `current` flag: confuses a
  pipeline's capability with one deployment's support.

### Consequences

- A pipeline usually has several capabilities; consumers store one link per
  capability.
- A new vocabulary snapshot is a new packaged file and digest; bundles built
  with another snapshot validate structurally and are reported as
  unverifiable rather than wrong.

> **Correction (2026-10-18).** Implementation paths updated for the unified workspace (ADR-0067); the decision is unchanged.


## ADR-0056: Discover assay capabilities from scientific evidence and require classification for ingestion readiness

| Metadata | Value |
|---|---|
| Status | Superseded |
| Date | 2026-10-16 |
| Source | Maintainer's assay-discovery correction for 0.3.0 (16 October 2026) |
| Scope | Assay discovery, identity readiness, bundle validation, session reports, all three modes |
| Supersedes | — |
| Superseded by | ADR-0069 |
| Related | ADR-0042, ADR-0044, ADR-0055 |
| Implementation | `src/nf_splice/services/assay_discovery.py`, `src/nf_splice/catalogue/data/assay-evidence-rules.json`, `src/nf_splice/layers/bundle.py`, `src/nf_splice/services/lifecycle.py`, `src/nf_splice/agents/report.py`, `src/nf_splice/agents/prompts.py`, `src/nf_splice/agents/operations.py`, `src/nf_splice/interfaces/tui/screens/assays.py`, `src/nf_splice/cli.py` |
| Tests | `tests/test_assay_discovery.py`, `tests/test_assay_capabilities.py`, `tests/test_tui.py` |

### Context

ADR-0055 made assay capabilities typed and verifiable, but discovery only
looked for literal vocabulary labels. Most pipelines never name their assays:
an RNA-seq pipeline runs STAR and Salmon without saying "poly(A) RNA-seq".
A lookup table that a person must already know how to use left such
pipelines unclassified, and an unclassified pipeline could still be reported
complete.

### Decision

- **Scientific discovery.** A deterministic service reads the pipeline's
  tools (modules, processes, containers, conda packages), parameters and
  allowed values, sample sheet columns, published outputs and documentation,
  and applies packaged, versioned evidence rules
  (`assay-evidence-rules.json`). Each rule links evidence to a vocabulary
  entity at the level the evidence supports, needs several independent
  terms, and may need specific tools; a "suggests" rule only distinguishes a
  more specific assay below an established one. Established entities are
  expanded through the vocabulary DAG into candidates with ids, level,
  status (`documented`, `supported`, `suggested`, `requires_verification`,
  `rejected`), confidence, evidence, alternatives and the question that
  would decide them. Explicit mentions remain evidence. No AI is involved.
- **Decisions are reviewed and recorded.** Candidates are never
  capabilities. People declare (`asserted`, or citing evidence) or reject
  (with a reason, kept in the review sidecar); agents declare only with
  cited evidence, or `confirmed` evidence for a person's answer that the
  person approves in AI-assisted mode.
- **Readiness levels.** A pipeline without a declared, verified assay is not
  ready for ingestion: the identity draft reports
  `missing_assay_classification` with the recommendations, so the bundle is
  not built; `validate_bundle` reports it as an error and states structural
  validity, scientific classification and ingestion readiness separately;
  session reports never say complete without all three.
- **Agents.** The identity-stage instruction carries the assessment for
  every provider; `assess_assays` and `reject_assay_candidate` join the
  assay tools. Assisted sessions ask a focused question where the evidence
  cannot decide; autonomous runs record a blocker naming the alternatives,
  which keeps the stage open until a person resolves it and the gate passes.

### Alternatives rejected

- Matching vocabulary labels only: empty results for most pipelines.
- Choosing a default assay (for example poly(A) for any RNA-seq pipeline):
  replaces uncertainty with an invented fact.
- Leaving classification optional: a bundle the platform cannot route would
  be reported as ready.

### Consequences

- Every fixture and flow that reaches readiness declares an assay.
- The evidence rules are knowledge and need review as new pipeline types
  appear; they cover the domains of the current vocabulary.


## ADR-0057: Make the six YAML drafts and native configs the authors' source of truth, seeded once and never gated on candidates

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-17 |
| Source | Maintainer's authoritative six-layer, file-first correction of 0.3.0 (17 October 2026) |
| Scope | All six draft layers, initialisation, validation, the wizard, the CLI and readiness |
| Supersedes | ADR-0038 |
| Superseded by | — |
| Related | ADR-0005, ADR-0006, ADR-0011, ADR-0026, ADR-0027, ADR-0030, ADR-0032, ADR-0036, ADR-0042, ADR-0047, ADR-0056 |
| Implementation | `src/nf_splice/layers/base.py`, `src/nf_splice/layers/bundle.py`, `src/nf_splice/layers/inputs.py`, `src/nf_splice/layers/outputs.py`, `src/nf_splice/layers/components.py`, `src/nf_splice/inspectors/parameters.py`, `src/nf_splice/inspectors/routes.py`, `src/nf_splice/inspectors/containers.py`, `src/nf_splice/services/workspace.py`, `src/nf_splice/services/readiness.py`, `src/nf_splice/services/contract_reference.py`, `src/nf_splice/interfaces/tui/widgets.py`, `src/nf_splice/interfaces/tui/pages/outputs.py`, `src/nf_splice/interfaces/tui/pages/execution.py`, `src/nf_splice/cli.py` |
| Tests | `tests/test_file_first.py`, `tests/test_layer_outputs.py`, `tests/test_layer_inputs.py`, `tests/test_containers.py`, `tests/test_tui.py`, `tests/test_reference_workflow.py` |

### Context

Drafts were meant to be the editable source (ADR-0030), but the outputs,
components and execution-profile drafts started as empty lists while the
real discoveries waited in review sidecars, every imported parameter lacked
an access policy, and a `pending_candidate` or `unconfirmed_detected_value`
blocked validation. A correct draft written in an editor could not be built
until every heuristic candidate had been accepted or rejected: 72 component
approvals and 122 parameter decisions on a real pipeline. The wizard
(ADR-0038) was built around those queues.

### Decision

- **Authority.** Each layer has one authoritative YAML draft below
  `.splice-local/drafts/`; execution profiles also name native
  `.draft.config` files (ADR-0059). A file written in any editor is an
  authored decision. Review sidecars hold provenance, advisory candidates
  and verification records, never field values, and a candidate's status is
  never a validation error. Optional review tools remain conveniences.
- **Seeding.** `nf-splice init` inspects the repository read-only and writes
  every draft once, with what the evidence supports and nothing invented:
  identity from the pipeline metadata block, `CITATION.cff`, README, Git and
  the root RO-Crate; every declared parameter with
  `x-splice-access.editable_by: []` and hidden presentation (a valid,
  least-privilege policy), or an empty contract when there is no
  `nextflow_schema.json`; an output catalogue from a previously published
  `splice/outputs.yaml` (0.3.0 or earlier layout) or one provisional entry
  per published route; every module with runtime-specific container sources,
  keeping published container IDs; a default profile with a native config
  scaffold or the earlier bundle's profiles; and an RO-Crate graph
  (ADR-0060). Unknown values stay null and are reported. Running init again
  changes no draft or config byte.
- **Safe writes versus validity.** `replace_draft` replaces a whole draft
  (complete YAML text) or one section (a JSON pointer) after checking the
  sha256 the author read, refusing unsafe YAML, a changed draft marker, a
  path escape or a concurrent edit. The content need not pass validation:
  intermediate work is kept. Malformed files are reported and never
  rewritten.
- **Substantive validation.** Layers report what the content lacks:
  unresolved seeded fields, published routes no output covers
  (`route_not_covered`, a warning, silenced by `excluded_routes` with a
  reason), modules missing from the inventory, unresolved container
  expressions, undeclared executable `params.*` references (found by a
  comment-aware index that tells real references from config-internal maps
  such as `params.genomes`), conflicting evidence for a required identity
  field.
- **Readiness dimensions.** `nf-splice validate` and session reports state
  contracts, scientific classification, runtime parameters (indispensable
  inputs with no default must be suppliable by a principal or the default
  profile's config), deployment (images the default profile needs, engine
  versus sources), provenance (RO-Crate 1.1 root properties, identity
  agreement) and publication consistency separately; ingestion readiness
  needs all of them.
- **Retained from ADR-0038.** The session-resumable Textual wizard over the
  shared services, its step rail and navigation, and CLI/TUI equivalence of
  drafts and bundles.
- **Wizard.** Every layer step offers Open YAML (in `$VISUAL`/`$EDITOR`),
  Reload, Validate, Preview JSON and Explain errors; the outputs, components
  and profiles steps edit what is in the draft, with candidates as optional
  hints. The CLI edits seeded entries by key (`configure outputs --set
  report.description=...`, `configure execution-profiles --set
  default.type=...`).
- **Discovery fixes found on a real pipeline.** Only the repository-root
  `splice/` is skipped when scanning (not `modules/splice/`); a call matched
  at a line end no longer hides the following `main:` label; nf-test
  configs are not publication routes; nf-core's `containerEngine in [...]`
  ternaries are parsed per runtime; the `container` directive is matched only
  at a line start.

### Alternatives rejected

- Keeping candidate queues as the only path to a valid draft: makes the
  file a form and the sidecar the authority.
- Seeding empty lists to force review: hides evidence the author needs.
- Treating missing access policies as errors: forces 122 decisions where
  least privilege is already a valid policy.

### Consequences

- A manually authored set of drafts validates and builds with zero
  candidate decisions (CORE-03).
- Earlier 0.3.0 work-in-progress drafts still validate: the review tools
  write the same shapes, and legacy profile and provenance shapes are read.
- Route coverage is static and can over-report; it warns rather than blocks.

> **Note (2026-10-17).** Amended by ADR-0064: an uncovered route the code always publishes is an error, not a warning; conditional and unresolved routes stay warnings. Readiness is stated through one lifecycle (ADR-0062), and review completion follows ADR-0063.

> **Note (2026-10-18).** Amended by ADR-0067, ADR-0068 and ADR-0069: the wizard is replaced by one persistent workspace with an AI dock; the output catalogue starts empty unless a published catalogue exists (no provisional entry per route), and route coverage is the `output_coverage` readiness dimension rather than a draft error; identity is imported from exact structured keys only, never the README. Implementation paths now name the workspace pages.


## ADR-0058: Review every layer with deep, high-effort AI investigation, independently of its validation gate

| Metadata | Value |
|---|---|
| Status | Superseded |
| Date | 2026-10-17 |
| Source | Maintainer's authoritative six-layer, file-first correction of 0.3.0 (17 October 2026) |
| Scope | Session engine, stages, operations, toolbox, prompts, providers, reports |
| Supersedes | ADR-0044 |
| Superseded by | ADR-0063 |
| Related | ADR-0045, ADR-0046, ADR-0050, ADR-0051, ADR-0052, ADR-0053, ADR-0056, ADR-0057 |
| Implementation | `src/nf_splice/agents/engine.py`, `src/nf_splice/agents/stages.py`, `src/nf_splice/agents/state.py`, `src/nf_splice/agents/operations.py`, `src/nf_splice/agents/toolbox.py`, `src/nf_splice/agents/prompts.py`, `src/nf_splice/agents/protocol.py`, `src/nf_splice/agents/report.py`, `src/nf_splice/agents/skills.py`, `src/nf_splice/agents/providers/`, `src/nf_splice/agents/help.py`, `src/nf_splice/agents/sandbox.py` |
| Tests | `tests/test_file_first.py`, `tests/test_agents.py`, `tests/test_agent_interfaces.py`, `tests/test_scenarios.py`, `tests/test_skills.py` |

### Context

ADR-0044 runs manual help, AI-assisted sessions and autonomous runs as three
policies over one deterministic engine. Its engine completed a layer stage
as soon as the gate passed ("already satisfied by the current files"), so a
schema-valid but scientifically poor draft was never looked at, and agents
could change drafts only one JSON pointer at a time. Providers had no common
reasoning setting.

### Decision

- **Retained from ADR-0044.** One engine, three policies; typed operations
  over the CLI's services; deterministic gates; assisted proposals staged on
  a private copy and applied only by a person's approval; autonomous changes
  recorded as `agent_autonomous` under `agent_policy`; blockers; budgets;
  checkpoints; non-destructive mode switching.
- **Reviews are not gates.** A layer stage completes only when its gate
  passes *and* a review is recorded for the current draft: an approved
  proposal, or `complete_review`. The toolbox records every read the model
  makes (files and line ranges, searches, analyses) in the stage's
  investigation trace, and refuses `complete_review` unless the pipeline's
  own sources were inspected. Reviews are `scientific` (identity, inputs,
  outputs, provenance) or `operational` (components, profiles) and carry the
  draft hash, sources fingerprint, provider, model and effort. A review is
  skipped only when the policy is `reuse_unchanged` and a completed review
  of byte-identical draft and sources exists, or when the person works
  manually.
- **Authoring tools.** `replace_draft` (whole draft or section),
  `write_config` and `read_config` (native configs), `contract_reference`
  (every authorable field), `parameter_usage`, `component_inventory` and
  `analyse_execution` join the read and draft tools; the prompts and
  provider-neutral checklists tell the model to challenge seeded content,
  map free text to fields, prefer one coherent revision and iterate against
  validation. Assay capabilities still change only through the
  vocabulary-checked tools.
- **Reasoning effort.** `Budgets.reasoning_effort` (`low` to `max`, default
  `high`, or the provider's default) travels in every turn. Adapters map it
  to their real control: Claude Agent SDK `effort` with adaptive thinking;
  Responses API `reasoning.effort` (low to high); Codex `turn/start`
  `effort` (low to xhigh); an OpenCode model variant when the model offers
  one. An unsupported value is lowered, never raised, with a notice; with no
  control nothing is sent and the notice says so. Reports state what was
  requested and applied. Effort is distinct from turns, time and cost; the
  default turn and tool budgets were raised for deep investigation.
- **Skills.** Nine canonical skills cover file-first authoring, agent
  operations, identity and assays, input access, outputs, components and
  images, execution configuration, provenance and validation; each stage
  loads its own.

### Alternatives rejected

- Skipping review when validation passes: a validator cannot judge
  scientific meaning.
- Trusting the model's statement that it reviewed: the trace is recorded by
  nf-splice, not reported by the model.
- Longer prompts instead of a reasoning control: does not configure model
  reasoning.

### Consequences

- AI sessions take more turns; scripted tests script a review per stage.
- Scripted providers prove orchestration only; live provider tests are
  opt-in and report what actually ran.

## ADR-0059: Keep profile metadata in YAML and configuration in native files; deliver images only on explicit approval

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-17 |
| Source | Maintainer's authoritative six-layer, file-first correction of 0.3.0 (17 October 2026) |
| Scope | Execution profiles, configs, resource review, container image delivery |
| Supersedes | ADR-0034 |
| Superseded by | — |
| Related | ADR-0033, ADR-0043, ADR-0045, ADR-0057 |
| Implementation | `src/nf_splice/layers/execution.py`, `src/nf_splice/inspectors/profiles.py`, `src/nf_splice/services/execution_review.py`, `src/nf_splice/services/checks.py`, `src/nf_splice/services/images.py`, `src/nf_splice/services/lifecycle.py`, `src/nf_splice/contracts/data/schemas/execution-profiles/0.3.0.schema.json` |
| Tests | `tests/test_layer_execution.py`, `tests/test_file_first.py` |

### Context

ADR-0034 generated a profile's config once from settings held in the YAML
(`generated:`), so configuration lived in two places, and a profile needed a
candidate review before it existed. Site profiles such as a Slurm cluster
that rejects `#SBATCH --mem` and allots memory per CPU need evidence-led
CPU sizing and a check of every `task.memory` use, not a copied template.
Image publication had an abstract uploader only.

### Decision

- **Retained from ADR-0034.** Exactly one explicitly chosen default; adopted
  repository configs published byte-for-byte; the two conventional parameter
  sections; no site literals, secrets, personal paths or test settings in
  production configs.
- **References, not settings.** A profile's YAML holds identity,
  description, type, executor, container engine, site parameters and
  `config: {draft: <name>.draft.config}` or `config: {adopt: <path>}`.
  The native file is the configuration, edited in any editor or with
  `write_config`, re-read at every validation and published as written
  (`config_strategy: authored`; the unreleased 0.3.0 enum changes from
  `generated` to `authored`). Section values are checked against the input
  access policy. Init seeds a `default` profile and its scaffold, or the
  earlier bundle's profiles and configs. A `generated:` block is ignored
  with a warning. Builds remove configs the previous lock lists that nothing
  publishes any more.
- **Resource review.** `analyse_execution` (`nf-splice draft resources`)
  reads selectors, labels, `memory = null` coverage, memory per core and
  every `task.memory` use with its guard; with memory per core known it
  computes the CPUs each selector needs for its intended memory. The opt-in
  `nf-splice draft check-config` asks Nextflow for the effective
  configuration (`run_nextflow`), without running the pipeline.
- **Image delivery.** `nf-splice containers plan` lists, offline, each
  container's runtime source and the Nextflow cache name for that source.
  `nf-splice containers deliver --approve-network --approve-upload` fetches
  native images or converts OCI images with an installed Apptainer, checks
  the file format, uploads to a configured S3-compatible store (settings in
  the user's config folder, credentials from the normal AWS chain; optional
  `s3` extra) without overwriting different content, reads it back, and
  records the distribution only after downloading it again from its public
  HTTPS URL. Without a public URL nothing is recorded as downloadable.

### Alternatives rejected

- Settings in YAML that regenerate configs: two competing copies.
- A universal site template: memory and CPU behaviour differ by site.
- Uploading as a side effect of authoring or building: hidden network and
  storage effects.

### Consequences

- A person can add any valid Nextflow configuration and any number of
  profiles without nf-splice templates.
- The real S3 path is exercised only by an opt-in test.

> **Note (2026-10-18).** Amended by ADR-0070: `container_engine` is optional profile metadata. It is extracted only where a configuration declares it; a profile without one is valid, and neither draft validation nor publication requires a runtime.

---

## ADR-0060: Author one RO-Crate graph, enrich it with the bundle, and make the pipeline archive a Workflow RO-Crate

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-17 |
| Source | Maintainer's authoritative six-layer, file-first correction of 0.3.0 (17 October 2026) |
| Scope | Provenance draft, published RO-Crate, archives, standards validation |
| Supersedes | ADR-0035, ADR-0049 |
| Superseded by | — |
| Related | ADR-0029, ADR-0043, ADR-0047, ADR-0048, ADR-0057 |
| Implementation | `src/nf_splice/layers/provenance.py`, `src/nf_splice/services/export.py`, `src/nf_splice/services/checks.py`, `src/nf_splice/services/readiness.py`, `src/nf_splice/cli.py` |
| Tests | `tests/test_layer_provenance.py`, `tests/test_source_git_export.py`, `tests/test_file_first.py` |

### Context

ADR-0035 made the person choose `include`, `enriched` or `generated`, with
`strategy: null` until then, and its optional nf-core generator wrote into
the pipeline's root. The published crate did not describe the `splice/`
bundle, and the pipeline archive (ADR-0049) put everything under a folder
with no crate at its root, so standard tools did not recognise it.

### Decision

- **Retained from ADR-0035 and ADR-0049.** The developer's root crate is
  never modified; identity and structural findings; reviewer provenance as a
  namespaced `CreateAction` timed at the action, never at render;
  deterministic, verified archives that exclude private state and secrets
  and never overwrite without permission.
- **One authored graph.** `provenance.draft.yaml` holds `crate` (data-entity
  IDs relative to the pipeline directory), `source` (the root crate it was
  based on) and `origin` (`adopted`, `generated`, `nf-core`, `authored`).
  Init adopts a parseable root crate as a copy, or builds a Workflow
  RO-Crate from the identity draft. The earlier `strategy` shape is read.
- **Bundle entities.** Building adds a `splice/` Dataset and a File per
  published artefact, linked from the root's `hasPart`, without checksums
  (`bundle.json` records the crate's hash). `splice/ro-crate-metadata.json`
  stays the canonical published file.
- **Standards.** Missing RO-Crate 1.1 root properties (name, description,
  licence, `datePublished`) are draft warnings and provenance readiness
  blockers, filled from the identity's licence and `released_at` when known,
  never guessed. `rocrate-validator` runs as an opt-in check
  (`external_tools`, `network` or `--offline`) on the archive layout.
- **nf-core generator.** `nf-splice configure provenance --with-nf-core`
  runs `nf-core pipelines rocrate` on an isolated copy below
  `.splice-local/tmp/`, with no terminal input, its update check disabled
  and no `--pipeline_version` checkout; the output is a candidate corrected
  from the reviewed identity, with nf-co.re hosting claims removed for
  pipelines that are not nf-core's.
- **Archives.** The complete-pipeline ZIP holds the pipeline at its root and
  the published crate as its root `ro-crate-metadata.json`, replacing a
  developer's root crate in the archive only; verification checks that
  every local file the crate names is a member. The bundle-only ZIP holds
  `splice/` and does not claim to be a self-contained Workflow RO-Crate.
  Neither embeds its own checksum or an invented download URL.

### Alternatives rejected

- A second, separately maintained root descriptor: two sources of truth.
- Calling the generator a validator: generated crates still need checking.
- A top-level folder in the pipeline archive: hides the crate from tools.

### Consequences

- Pipeline archives extracted anywhere are standard Workflow RO-Crates.
- Bundles whose identity lacks a licence or release date are not ready for
  ingestion until the author supplies them.

> **Note (2026-10-17).** Amended by ADR-0065: agents assess, regenerate and check the crate through permission-controlled operations, and standards validation is reported apart from nf-splice's structural checks.

## ADR-0061: State the authoring, access and image-provenance rules once for the file-first model

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-17 |
| Source | Maintainer's corrective implementation and consistency pass of 0.3.0 (17 October 2026), section 2 |
| Scope | Draft authority, seeded values, input access policies, container sources and distributions |
| Supersedes | ADR-0006, ADR-0030, ADR-0032, ADR-0033 |
| Superseded by | — |
| Related | ADR-0005, ADR-0011, ADR-0026, ADR-0029, ADR-0041, ADR-0045, ADR-0047, ADR-0057, ADR-0059 |
| Implementation | `src/nf_splice/layers/base.py`, `src/nf_splice/layers/inputs.py`, `src/nf_splice/services/input_policy.py`, `src/nf_splice/layers/components.py`, `src/nf_splice/inspectors/containers.py`, `src/nf_splice/services/containers.py`, `src/nf_splice/services/images.py` |
| Tests | `tests/test_layer_inputs.py`, `tests/test_containers.py`, `tests/test_file_first.py`, `tests/test_corrective.py` |

### Context

ADR-0006, ADR-0030, ADR-0032 and ADR-0033 were still Current but described
the model ADR-0057 replaced: drafts below `splice/drafts/`, seeded values
pending until confirmed, a parameter without a reviewed policy blocking
promotion, agents never writing access policies, and an image store
configured by `NF_SPLICE_IMAGE_STORE_URL`. Notes pointed at ADR-0057, but
four records each still made a normative statement that the code no longer
followed. Only one interpretation may be Current.

### Decision

- **Retained from ADR-0006.** Published files are rendered only from the
  drafts, never from raw inspection results, and a blocking issue in one
  layer does not block unrelated layers.
- **Retained from ADR-0030.** One authoritative draft per layer, a draft
  marker, explicit `null` for absence, drafts created only when absent and
  never overwritten by discovery, sidecars that never hold field values,
  and previews that are derived and never written.
- **What counts as reviewed.** A draft that validates is authored, reviewed
  content, whoever wrote it and with whatever editor. Drafts live below
  `.splice-local/drafts/` (ADR-0047). A seeded value needs no confirmation:
  it is the author's to keep or change, and no candidate status, pending
  value or confirmation is a validation error. `confirm` and the candidate
  review tools remain optional records. Unresolved or conflicting *content*
  (a null required field, conflicting evidence for a required identity
  field, an unresolved container) still blocks its layer.
- **Retained from ADR-0032.** The SPLICE-owned, engine-neutral input
  contract, the lossless nf-schema adapter, the SPLICE extensions,
  service-side enforcement and three-way re-import.
- **Least privilege is a decision.** `x-splice-access.editable_by: []` is a
  valid, deliberate policy (nobody changes the value at run time), and
  hidden presentation is its default. Every imported parameter starts
  there. Readiness checks that every indispensable input can still be
  supplied (ADR-0062); nf-splice never widens a policy to satisfy it.
- **Agents and access policies.** In an assisted session an agent's policy
  change applies only after a person approves the proposal. In an
  autonomous run it applies under the approved policy and is recorded as
  `agent_autonomous` with approval `agent_policy`, never as human review.
  The runtime principal `agent` is never granted because an AI wrote the
  draft.
- **Retained from ADR-0033.** Container references per runtime with their
  location and condition, classification of reference kinds, one logical
  container per image, stable container IDs, the published `id`/`type`/
  `uri`, `source_images` and `resolution`, and the transport protections.
- **Distributions.** A `distribution` is recorded only by nf-splice: by the
  verification operation, which downloads and checks the file, by
  `containers deliver` (ADR-0059), or, when the inventory is seeded from a
  published `splice/components.json`, by keeping a distribution the lock
  vouches for, recorded as verified and whose every runtime source is
  unchanged. A kept distribution is reported as not downloaded again;
  nothing is invented. Image delivery goes only through the explicitly
  approved S3 workflow of ADR-0059; the environment-variable store is
  removed.
- **Components.** A module that declares a container must be mapped to one
  (`container_not_mapped`). A process defined inline in a workflow file is a
  component with `path` `<file>::<PROCESS>`.

### Alternatives rejected

- Keeping the four records Current with notes: two normative texts for one
  rule.
- Treating `editable_by: []` as incomplete: forces a decision per parameter
  where least privilege is already the right default.

### Consequences

- ADR-0006, ADR-0030, ADR-0032 and ADR-0033 are historical; their retained
  rules are stated here.
- Consumers see no contract change: `path` was already a free string.

> **Note (2026-10-17).** Amended by ADR-0066: an inline process is a `workflow_process` component with `path` (its `.nf` file) and `process`, not `path: <file>::<PROCESS>`; a distribution is reused only when the lock's verification record, the distribution and the sources agree, and such reuse is a historical verification.

---

## ADR-0062: State one lifecycle: drafts valid, published, classified and ingestion ready are separate facts

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-17 |
| Source | Maintainer's corrective implementation and consistency pass of 0.3.0 (17 October 2026), section 3 |
| Scope | `status`, `draft validate`, `build`, `validate`, `export`, the wizard, session completion and reports |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0036, ADR-0056, ADR-0057, ADR-0061 |
| Implementation | `src/nf_splice/services/readiness.py`, `src/nf_splice/services/lifecycle.py`, `src/nf_splice/cli.py`, `src/nf_splice/interfaces/tui/pages/finish.py`, `src/nf_splice/agents/report.py`, `src/nf_splice/agents/stages.py` |
| Tests | `tests/test_corrective.py`, `tests/test_tui.py` |

### Context

ADR-0057 introduced six readiness dimensions, but only `nf-splice validate`
and session reports showed them. `build` said "Built N file(s).",
`status` said "Bundle ready to publish", the wizard's last step said
"Bundle valid: yes", and `BundleReport` called a bundle without structural
or classification errors "ingestion ready". A bundle could be published,
and look finished, while a required input could not be supplied by anyone.

### Decision

- `nf-splice.services.readiness.lifecycle()` is the one statement every
  interface makes: whether the drafts validate, whether the bundle is
  published and current, whether it is structurally valid and
  scientifically classified, and whether it is ready for SPLICE ingestion,
  with one headline (`Drafts do not validate yet`, `Drafts validate, but the
  bundle is not published`, `Published, but not ready for SPLICE
  ingestion`, `Published and ready for SPLICE ingestion`) and actionable
  reasons by dimension.
- Publishing a structurally valid bundle for further review stays possible.
  `build`, `status`, `validate`, `export`, the wizard's Review, Build and
  Done steps, the build gate's summary and session reports print the
  lifecycle; `draft validate` says it checks drafts only. `validate` exits
  2 unless the bundle is ingestion ready.
- A dimension that could not be assessed is not ready. A null or empty
  default supplies nothing. Components that declare only Conda packages
  block deployment under a container engine; components that declare no
  software environment are noted as using the execution host's software.
- Everything is computed offline from the repository; no provider or
  network is needed.

### Alternatives rejected

- Refusing to publish until ingestion ready: a bundle is also reviewed
  after publishing, and readiness can depend on deployment facts outside
  the drafts.
- A single "valid" flag: hides which dimension fails.

### Consequences

- `BundleReport.levels()` no longer reports ingestion readiness; consumers
  read `lifecycle` (`--json`).

> **Note (2026-10-18).** Amended by ADR-0068: readiness gains the `output_coverage` dimension, so a valid but deliberately limited catalogue can be published while ingestion readiness reports the uncovered routes. The workspace states the lifecycle the same way as the CLI (ADR-0067); implementation paths now name its pages and the removed assay-discovery tests.

---

## ADR-0063: Complete a layer review only with stage-specific evidence, an assessment of the draft and cited support

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-17 |
| Source | Maintainer's corrective implementation and consistency pass of 0.3.0 (17 October 2026), section 4 |
| Scope | Session engine, review controls, toolbox, prompts, scripted provider, reports |
| Supersedes | ADR-0058 |
| Superseded by | — |
| Related | ADR-0045, ADR-0046, ADR-0050, ADR-0056, ADR-0057, ADR-0064, ADR-0065 |
| Implementation | `src/nf_splice/agents/review_scope.py`, `src/nf_splice/agents/toolbox.py`, `src/nf_splice/agents/engine.py`, `src/nf_splice/agents/operations.py`, `src/nf_splice/agents/state.py`, `src/nf_splice/agents/prompts.py`, `src/nf_splice/agents/providers/scripted.py` |
| Tests | `tests/test_corrective.py`, `tests/test_file_first.py`, `tests/test_agents.py`, `tests/test_other_pipelines.py` |

### Context

ADR-0058 made a review necessary even when a draft validates, but accepted
`complete_review` after one recorded source inspection of any kind. One
read of `main.nf` could "review" an outputs catalogue whose publishing
configs were never opened, and an unchanged draft could be accepted
without saying what was checked.

### Decision

- **Retained from ADR-0058.** One engine, three policies; reviews
  independent of the gates; the investigation trace recorded by nf-splice
  from the model's own calls; review kinds, draft hash, sources
  fingerprint, provider, model and effort; the reuse policy for
  byte-identical drafts and sources; the authoring tools; reasoning effort
  and its per-provider mapping; nine skills.
- **Review scope.** For each layer stage, `review_scope` derives from the
  repository the evidence classes that apply to this pipeline, each
  required or advisory, with its files or analyses: identity (the current
  draft, assay evidence through the vocabulary tools, the pipeline's
  metadata and documentation; alternative routes advisory), inputs (the
  draft, parameter usage, `nextflow_schema.json`, workflow code, configs
  that set values), outputs (the draft, traced routes, the entry workflow
  and every workflow file, every config that declares `publishDir`, the
  example outputs supplied; subworkflows advisory), components (the draft,
  the module inventory, `modules.json`, every module with an unresolved
  item; container overrides advisory), profiles (the draft, the execution
  analysis, every profile's own config, the pipeline's resource config;
  `task.memory` modules advisory), provenance (the draft, the crate
  assessment, the reviewed identity, the root crate; standards check and
  authorship advisory). Evidence that does not exist in the repository is
  not applicable, never missing. No count of calls is required.
- **Completion.** `complete_review` and `submit_stage_proposal` are refused
  while required evidence is uninspected, and when cited evidence names a
  file never read; evidence must cite files (`path` or `path:line`) or
  analyses that were run. `complete_review` also needs an assessment of
  the draft (omissions, incorrect assumptions, unsupported declarations,
  confirmations); an unchanged draft needs explicit confirmations. An
  outputs review must address each uncovered alternative route
  (ADR-0064). Uncertainties and blockers are recorded, never answered by
  guessing.
- **Record.** Each review records its basis (`revised` or
  `verified_unchanged`), evidence, assessment, the coverage of every class
  and the gaps left, apart from draft validity.
- Deterministic discovery is the starting point; the prompt tells the model
  to look beyond it. The scripted provider's `{"follow": "review_scope"}`
  step makes the suggested calls for orchestration tests only.

### Alternatives rejected

- A fixed number of files or calls: pipelines differ; volume is not
  coverage.
- Trusting the model's list of what it checked: the trace is nf-splice's.

### Consequences

- AI sessions read more of each pipeline before finishing a stage.
- Scripted tests prove the records and refusals, never a model's judgement.

---

## ADR-0064: Keep outputs and components pipeline-defined and classify uncovered routes by evidence

| Metadata | Value |
|---|---|
| Status | Superseded |
| Date | 2026-10-17 |
| Source | Maintainer's corrective implementation and consistency pass of 0.3.0 (17 October 2026), sections 5, 7 and 8 |
| Scope | Output catalogue validation, seeding and formats, component inventory, test fixtures |
| Supersedes | — |
| Superseded by | ADR-0068 |
| Related | ADR-0027, ADR-0042, ADR-0057, ADR-0061, ADR-0063 |
| Implementation | `src/nf_splice/layers/outputs.py`, `src/nf_splice/domain/outputs.py`, `src/nf_splice/inspectors/outputs.py`, `src/nf_splice/renderers/outputs.py`, `src/nf_splice/layers/components.py`, `src/nf_splice/interfaces/tui/screens/outputs.py` |
| Tests | `tests/test_corrective.py`, `tests/test_other_pipelines.py`, `tests/test_layer_outputs.py`, `tests/test_file_first.py` |

### Context

ADR-0057 reported every uncovered published route as a warning, so an
output the code always publishes could be missing from a catalogue that
validated. Real-pipeline testing focused on bulk RNA-seq: the output
formats nf-splice accepted were a closed genomics list (an imaging
pipeline's OME-TIFF and Zarr outputs could not be described, although the
contract allows any format), seeded categories came from a table of RNA-seq
tool names, and processes defined inline in a workflow file were missing
from the inventory.

### Decision

- **Route classes.** An uncovered route is *established* when the code
  always publishes it (confirmed, with no branch, `when:`, switch, `saveAs`
  or run-time path): an error, `route_not_covered`. *Conditional* or
  configuration-dependent routes are warnings,
  `conditional_route_not_covered`, naming the condition. Routes static
  analysis cannot resolve are warnings, `route_unverified`, never blockers.
  Each is resolved by adding or correcting an output, or by an
  `excluded_routes` entry with a reason and an optional `kind`
  (`intermediate`, `false_positive`, `out_of_scope`). The catalogue stays
  the union of every route, whatever one example run took. No
  candidate-by-candidate approval returns.
- **Formats.** An output's format is any lower-case identifier; the
  recognised list (now including TIFF, OME-TIFF, Zarr and H5AD) only
  suggests formats from file names.
- **Categories.** A seeded category is the first literal directory the
  pipeline publishes to; nf-splice prescribes no category vocabulary.
- **Inline processes** are inventoried with their own container references
  (ADR-0061).
- **Fixtures.** A multi-assay imaging-based spatial transcriptomics pipeline
  and a minimal custom pipeline without `nextflow_schema.json`,
  `modules.json` or nf-core conventions are exercised end to end in all
  three modes.

### Alternatives rejected

- Blocking every uncovered route: static analysis over-reports conditional
  and dynamic routes.
- A larger closed list of formats: still prescribes a domain.

### Consequences

- An established output can no longer be silently missing from a
  validating catalogue.
- No contract changes: the contract already accepted any format string.

> **Note (2026-10-17).** ADR-0066 confirms established uncovered routes as errors and replaces the inline-process representation with `workflow_process` components.

---

## ADR-0065: Let agents assess, regenerate and check the RO-Crate through permission-controlled operations

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-17 |
| Source | Maintainer's corrective implementation and consistency pass of 0.3.0 (17 October 2026), section 6 |
| Scope | Provenance stage operations, standards-check reporting, CLI |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0043, ADR-0045, ADR-0060, ADR-0063 |
| Implementation | `src/nf_splice/services/crate_review.py`, `src/nf_splice/services/checks.py`, `src/nf_splice/agents/operations.py`, `src/nf_splice/agents/stages.py`, `src/nf_splice/cli.py` |
| Tests | `tests/test_corrective.py`, `tests/test_layer_provenance.py` |

### Context

ADR-0060 added nf-core generation on an isolated copy, archive layout and
an opt-in `rocrate-validator` check, but only for the command line; agents
still chose between the earlier `include|enriched|generated` strategies and
could not run the generator or the validator. A structural pass could be
read as a standards pass.

### Decision

- `analyse_ro_crate` assesses the repository's crate and the authored graph
  and recommends `keep`, `adopt`, `correct` or `regenerate` with reasons,
  stating whether nf-core's generator is installed and applicable.
- `provenance_strategy` takes `adopt`, `correct` or `regenerate` (the
  earlier names are read).
- `generate_ro_crate` runs `nf-core pipelines rocrate` on an isolated copy
  (ADR-0060) and needs `external_tools` and `network`; nf-splice never
  installs nf-core. The result is reconciled with the reviewed identity.
- `validate_ro_crate` and `nf-splice draft check-crate` check the draft
  graph as it would be published: nf-splice's structural and identity
  checks, and separately the Workflow RO-Crate 1.0 profile with
  `rocrate-validator` (`external_tools`; offline without `network`),
  reported as `passed`, `failed`, `not_run` or `not_applicable`, with a
  statement that only structural checks are established when the standards
  check did not run.
- Missing tools or permissions give a result with the reason, so an agent
  can report progress or record a blocker.

### Alternatives rejected

- Running the generator implicitly: hidden external effects.
- One combined pass/fail: conflates nf-splice's checks with the standard.

### Consequences

- The provenance stage can be completed by an agent without any external
  tool; standards validation is reported as not run in that case.

## ADR-0066: Settle the maintainer's four corrective decisions: route errors, private state, process components and image reuse

| Metadata | Value |
|---|---|
| Status | Superseded |
| Date | 2026-10-17 |
| Source | Maintainer's decisions on the four questions left by the corrective pass of 0.3.0 (17 October 2026) |
| Scope | Output coverage, repository hygiene, the components contract, image verification reuse |
| Supersedes | — |
| Superseded by | ADR-0068 |
| Related | ADR-0024, ADR-0033, ADR-0040, ADR-0047, ADR-0059, ADR-0061, ADR-0064 |
| Implementation | `src/nf_splice/layers/outputs.py`, `scripts/check_staged_paths.py`, `src/nf_splice/contracts/data/schemas/components/0.3.0.schema.json`, `src/nf_splice/layers/components.py`, `src/nf_splice/renderers/bundle_index.py`, `src/nf_splice/services/lifecycle.py`, `src/nf_splice/services/readiness.py`, `src/nf_splice/cli.py` |
| Tests | `tests/test_corrective.py`, `tests/test_other_pipelines.py`, `tests/test_dev_workspace.py`, `tests/test_contracts.py` |

### Context

The corrective pass left four questions for the maintainer: whether an
established uncovered route should block publication, whether a
repository-root `.splice-local/` may be staged, how a process defined
inline in a workflow file is represented (ADR-0061 used `path:
<file>::<PROCESS>`), and whether a lock hash is enough evidence to reuse a
verified image file.

### Decision

- **Established routes stay errors** (ADR-0064, confirmed). Conditional
  and unresolvable routes stay warnings; a justified `excluded_routes`
  entry resolves an error; no candidate-by-candidate approval returns.
- **Private state is never staged.** Everything under the repository-root
  `.splice-local/` is ignored and rejected by the staged-path guard,
  including force-added files. `splice/` and versioned fixtures under
  `tests/fixtures/` stay committable.
- **Inline processes are `workflow_process` components.** The components
  contract (0.3.0, unreleased, changed in place) types a component as
  `workflow_module` (a module directory, no `process`) or
  `workflow_process` (`path` is the repository-relative `.nf` file,
  `process` the process name, required). `path` is never overloaded. IDs
  stay stable and unique (the file and the process name) and earlier
  published IDs are kept by path and process.
- **Image reuse needs agreeing evidence.** The lock records each published
  verification (`distributions`: checksum, address, size, a digest of the
  container's source images, `fresh` or `historical`). A distribution is
  reused without downloading only when the lock vouches for
  `components.json`, its record matches the distribution, the
  distribution is consistent (HTTPS, `sif`/`img`, the cache name of these
  sources) and the sources are unchanged. A reused verification is
  `historical`: nf-splice never claims a lock hash or record proves an
  image is reachable now. `nf-splice containers reverify --approve-network`
  is the fresh check; it records a match as `fresh` and reports, without
  changing, a changed or unreachable file.

### Alternatives rejected

- Keeping `path: <file>::<PROCESS>`: one field with two meanings, which
  ingestion would have to parse.
- Reusing on the lock's file hash alone: says nothing about the image
  itself.

### Consequences

- The components contract gains `process` and a second `type`; consumers
  key components by `id`.
- Bundles built before the lock recorded verifications reuse no image file
  until it is verified again.

---

## ADR-0067: Work in one persistent workspace with an AI dock, safe pauses, takeover and same-session resume

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-18 |
| Source | Unified Manual, Ask AI, Assisted and Autonomous TUI implementation specification for 0.3.0 (18 October 2026) |
| Scope | The Textual interface, its view model, agent coordination, session resume, themes, responsiveness and the CLI's person option |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0014, ADR-0045, ADR-0057, ADR-0062, ADR-0063 |
| Implementation | `src/nf_splice/interfaces/tui/app.py`, `src/nf_splice/interfaces/tui/coordinator.py`, `src/nf_splice/interfaces/tui/dock.py`, `src/nf_splice/interfaces/tui/model.py`, `src/nf_splice/interfaces/tui/navigation.py`, `src/nf_splice/interfaces/tui/pages/`, `src/nf_splice/interfaces/tui/editors.py`, `src/nf_splice/interfaces/tui/themes.py`, `src/nf_splice/interfaces/tui/store.py`, `src/nf_splice/agents/engine.py`, `src/nf_splice/agents/state.py`, `src/nf_splice/drafts/yamlio.py`, `src/nf_splice/cli.py` |
| Tests | `tests/test_tui.py`, `tests/test_tui_agents.py`, `tests/test_tui_themes.py`, `tests/test_tui_performance.py`, `tests/test_agent_interfaces.py` |

### Context

The wizard of ADR-0038 and ADR-0057 was a sequence of screens. Ask AI, the
assisted session and the autonomous run each had a screen of their own, so
a person switching between manual work and AI help lost their place, and
closing a session view looked like stopping it. Selecting a row could
re-run a repository-wide scan (a p95 of 375 ms per assay row on a real
pipeline, with a 10 s blocking start), and validation ran on the
interface thread.

### Decision

- **One workspace.** A persistent top bar (pipeline, mode, agent state),
  a step rail with each step's state, the task pages (welcome, overview,
  identity, assays, parameters, outputs, software, execution, provenance,
  review, publish), an action bar and a status line. Every page offers
  *Ask AI about this screen* and a contextual *Assist* action; the AI dock
  opens beside the page (over it on narrow terminals) with Ask, Assist and
  Autonomous cards. Closing the dock is presentation only.
- **One owner of agent work.** An application-owned `AgentCoordinator`
  runs the shared session engine in a background thread and projects its
  persisted state as an immutable snapshot with one state for the header:
  off, ready, thinking, proposal waiting, running, needs your input, pause
  requested, paused, blocked, completed, failed or stopped. *Pause
  requested* is shown until the engine has actually stopped at a safe
  point; *stop* cancels the session for good. Ask uses read-only tools and
  may run while a session works.
- **Focused assistance.** `SessionEngine.assist(stage, actor, guidance)`
  investigates one stage on request and stops at its proposal; nothing is
  applied until a person approves, and a proposal made before the drafts
  changed is withdrawn rather than applied. `reject` withdraws a proposal
  with the person's reason.
- **Interventions and resume.** A blocker records the JSON pointer of the
  field it concerns, a checkpoint and, once resolved, its resolution. The
  dock shows each open intervention with an *Open the field* action that
  jumps to the exact page and field (`navigation.target_for`). While the
  agent may write drafts, manual writes are refused with an offer to pause;
  after the person edits, `SessionEngine.resume(actor, note)` continues the
  same session from the current drafts, reopening blocked stages and
  withdrawing stale proposals. Restarting the interface reopens the latest
  unfinished session as paused; a cancelled or completed one is never
  reopened. Quitting while the agent works pauses it safely first.
- **Attribution.** The person is named by `--user` or `NF_SPLICE_USER`
  (`--actor` and `NF_SPLICE_ACTOR` are removed). Agent work, approvals,
  pauses and resumes need a named person; the dock asks for one. A remote
  provider's consent is asked in the dock before any repository context is
  sent; a provider without structured tool calling is refused.
- **Responsiveness.** Pages render from an immutable `WorkspaceModel` built
  in a worker and cached by the bytes of every draft and config; workers
  carry generation numbers so a stale result is dropped. Row selection,
  input changes and navigation read only the model: no scan, parse or
  validation in an event handler. Draft parses are cached by content hash
  and the round-trip tree is built only for edits. Targets, measured on the
  synthetic scale fixture: cached row selection p95 below 100 ms and cached
  navigation p95 below 250 ms; slower work shows progress and never freezes
  input.
- **Forms and safety.** A form remembers the draft hash it was filled from;
  saving after the file changed on disk offers reload, compare or cancel and
  never overwrites. Inspect-only mode (`nf-splice tui --inspect-only`)
  writes nothing. *Start fresh* backs every draft up under
  `.splice-local/backups/` before recreating the drafts from exact metadata.
- **Themes.** Six themes (SPLICE Night by default, SPLICE Day, Ocean Amber,
  Violet Gold and two high-contrast themes) defined as tokens; every text
  pair meets 4.5:1 and every control boundary 3:1, measured in tests, also
  under simulated colour-vision deficiencies for status text. States carry
  a glyph and words, never colour alone. The choice is saved in the user's
  configuration folder.

### Alternatives rejected

- Separate screens per mode: the person loses context and a closed screen
  looks like a stopped session.
- Re-validating on every selection: correct but unusable on large
  pipelines.
- Letting manual edits and agent writes interleave: either can silently
  overwrite the other.

### Consequences

- The wizard's screens, `state.py` and `steps.py` are removed with no
  compatibility layer; `--actor` is gone.
- Headless tests drive the same widgets a person uses over real services
  and files; a scripted provider stands in for the model.

> **Note (2026-10-19).** Amended by ADR-0071: Welcome is capability-aware (its options depend on the working copy and on verified AI readiness), the workspace shows AI actions only for a verified provider, and draft creation needs a working copy or recorded in-place consent.

---

## ADR-0068: Author the output catalogue; make route coverage an ingestion-readiness dimension and version analysis output independently

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-18 |
| Source | Unified Manual, Ask AI, Assisted and Autonomous TUI implementation specification for 0.3.0 (18 October 2026), the approved scoped output-coverage policy |
| Scope | Output seeding and editing, route coverage, readiness, the analysis-output version, and the decisions of ADR-0064 and ADR-0066 it restates |
| Supersedes | ADR-0064, ADR-0066 |
| Superseded by | — |
| Related | ADR-0027, ADR-0028, ADR-0042, ADR-0047, ADR-0057, ADR-0061, ADR-0062 |
| Implementation | `src/nf_splice/layers/outputs.py`, `src/nf_splice/inspectors/outputs.py`, `src/nf_splice/services/readiness.py`, `src/nf_splice/agents/operations.py`, `src/nf_splice/agents/toolbox.py`, `src/nf_splice/interfaces/tui/editors.py`, `src/nf_splice/interfaces/tui/patterns.py`, `src/nf_splice/cli.py`, `scripts/check_staged_paths.py`, `src/nf_splice/contracts/data/schemas/components/0.3.0.schema.json`, `src/nf_splice/layers/components.py`, `src/nf_splice/renderers/bundle_index.py` |
| Tests | `tests/test_layer_outputs.py`, `tests/test_corrective.py`, `tests/test_tui.py`, `tests/test_other_pipelines.py`, `tests/test_reference_workflow.py`, `tests/test_dev_workspace.py`, `tests/test_contracts.py` |

### Context

`nf-splice init` wrote one provisional output per published route, with
guessed titles and categories, and kept candidate accept, reject, merge and
split tools to clean them up. On a real pipeline that produced dozens of
speculative entries a person had to delete. ADR-0064 and ADR-0066 made an
established uncovered route a validation error, so a deliberately limited
catalogue (the outputs a platform actually wants to show) could not be
published at all. The analysis-output schema version defaulted to the
pipeline's release, conflating two unrelated versions.

### Decision

- **Authored catalogue.** A new output draft starts with no entries; only a
  previously published `splice/outputs.yaml` (written by people) seeds it.
  Published routes are evidence to browse (`nf-splice draft routes`, the
  workspace's route browser, the agents' `route_coverage`), never entries.
  Outputs are added, edited and removed by key (`configure outputs
  --add-output FILE`, `--set`, the two-step editor, `add_output` and
  `remove_output`); the candidate accept, reject, merge and split
  operations are removed. A draft without outputs reports "describe at
  least one output SPLICE should expose".
- **Coverage is readiness, not validity.** Route coverage no longer appears
  among draft errors. `route_coverage()` reports *complete*, *incomplete*
  (an established or conditional route no output covers and no exclusion
  explains), *unverified* (only routes static analysis cannot resolve) or
  *not assessed*. Readiness gains the `output_coverage` dimension: it blocks
  ingestion readiness while coverage is incomplete and is not assessed when
  it cannot be established. A valid, limited catalogue can be published;
  the lifecycle then says it is published but not ingestion ready.
  `excluded_routes` entries (a glob or process, a reason and an optional
  `kind`: `intermediate`, `false_positive`, `out_of_scope`) explain routes
  deliberately left out.
- **Analysis-output version.** `analysis_output_schema_version` versions a
  workflow's `analysis_output.json` shape. It comes from an explicit value
  or a previously published catalogue and otherwise stays null for the
  author to set; it never defaults to the pipeline version.
- **Restated from ADR-0064.** An output's format is any lower-case
  identifier (the recognised list only suggests formats from file names);
  categories are free text and nf-splice prescribes no vocabulary; route
  classes are established, conditional and unverified as before.
- **Restated from ADR-0066.** Everything under the repository-root
  `.splice-local/` is ignored and refused by the staged-path guard, even
  force-added. Inline processes are `workflow_process` components (`path`
  the `.nf` file, `process` the name); module directories are
  `workflow_module`. A verified image file is reused without downloading
  only on agreeing lock, record, distribution and source evidence, recorded
  as `historical`; `nf-splice containers reverify --approve-network` is the
  fresh check.

### Alternatives rejected

- Seeding one entry per route: speculative entries a person must delete,
  with invented titles.
- Keeping uncovered established routes as errors: forbids deliberately
  scoped catalogues and conflates contract validity with completeness.
- Defaulting the analysis-output version to the pipeline release: the two
  change for unrelated reasons.

### Consequences

- The AGENTS.md rule against seeding discoverable lists empty does not
  apply to the output catalogue: outputs are authored, and route coverage
  reports what is missing.
- Earlier drafts with provisional route entries can be replaced with *Start
  fresh from exact metadata*, which keeps a backup.

---

## ADR-0069: Infer no science deterministically: import identity from exact keys and let people declare assays

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-18 |
| Source | Unified Manual, Ask AI, Assisted and Autonomous TUI implementation specification for 0.3.0 (18 October 2026) |
| Scope | Identity import, ORCID iDs, assay capabilities, ingestion readiness, agent assay tools |
| Supersedes | ADR-0056 |
| Superseded by | — |
| Related | ADR-0031, ADR-0055, ADR-0057, ADR-0062 |
| Implementation | `src/nf_splice/inspectors/identity.py`, `src/nf_splice/inspectors/repository.py`, `src/nf_splice/domain/identity.py`, `src/nf_splice/layers/bundle.py`, `src/nf_splice/agents/operations.py`, `src/nf_splice/agents/prompts.py`, `src/nf_splice/agents/report.py`, `src/nf_splice/interfaces/tui/pages/assays.py`, `src/nf_splice/interfaces/tui/pages/identity.py` |
| Tests | `tests/test_inspection.py`, `tests/test_assay_capabilities.py`, `tests/test_tui.py`, `tests/test_other_pipelines.py`, `tests/test_layer_bundle.py` |

### Context

ADR-0056 scored assays from tools, parameters and prose with packaged
evidence rules. The scores were heuristics presented with confidence, they
re-scanned the repository whenever a row was selected, and a person still
had to decide. Identity import read the README and copied long prose into
the description; a pipeline directory inside another Git repository took
that repository's remote as its URL.

### Decision

- **Exact keys only.** Identity values are imported from a documented
  allowlist of structured keys: the pipeline metadata block in
  `nextflow.config`, `CITATION.cff`, the root dataset of
  `ro-crate-metadata.json`, the integration record's `source_remote`, an
  exact Git release tag, and the `origin` remote only when no integration
  record names the upstream and the directory is its own repository. The
  README and other prose are sources to browse, never values. Values are
  bounded (600 characters for a description, 300 otherwise); longer text is
  not imported.
- **ORCID iDs** are normalised to `https://orcid.org/…` after checking the
  ISO 7064 check digit; an invalid iD is refused or dropped, never
  repaired.
- **People declare assays.** No deterministic service infers a pipeline's
  assays; the evidence rules and `assess_assays` are removed. A person
  ticks assays from the pinned vocabulary (ADR-0055); a tick is recorded as
  `asserted` with a fixed rationale stating who declared it. Agents may
  declare an assay only with cited sources they read, and record a blocker
  when the sources cannot decide.
- **Readiness keeps classification.** A pipeline without a declared assay
  reports `missing_assay_classification` and is not ingestion ready
  (ADR-0062).

### Alternatives rejected

- Keeping the evidence rules as hints: they still read as findings and
  cost a scan per interaction.
- Importing README prose: long, unstructured and often wrong for the
  field.

### Consequences

- Manual mode makes no scientific inference; AI help is explicit, cited and
  reviewable.
- `services/assay_discovery.py` and `assay-evidence-rules.json` are deleted.

---

## ADR-0070: The container engine is optional profile metadata; authoring a bundle never needs a runtime

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-18 |
| Source | Round-2 offline context-adequacy evaluation (autonomous sessions on an ambiguous align-and-count pipeline and the nf-core/rnaseq checkout) |
| Scope | Execution-profile contract, draft validation, published bundle, deployment readiness, agent profile operations |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0022, ADR-0059, ADR-0062 (amends the requiredness carried by both) |
| Implementation | `src/nf_splice/contracts/data/schemas/execution-profiles/0.3.0.schema.json`, `src/nf_splice/layers/execution.py`, `src/nf_splice/inspectors/splice_tree.py`, `src/nf_splice/inspectors/profiles.py`, `src/nf_splice/services/readiness.py`, `src/nf_splice/agents/operations.py`, `src/nf_splice/services/contract_reference.py` |
| Tests | `tests/test_layer_execution.py`, `tests/test_corrective.py` |

### Context

Both the execution-profile contract (ADR-0022, retained by ADR-0059) and the
draft validator treated `container_engine` as a required field. A repository
that documents no runtime then forced a choice: fabricate an engine or record
a blocker that stalls the stage. The round-2 evaluations showed both costs —
an ambiguous pipeline correctly blocked the whole profiles stage on the field,
and an engine-neutral `debug` profile was authored as debug-on-Docker to
avoid a null. The assumption behind the requirement was wrong at its root:
nf-splice authors SPLICE bundles; it is not a workflow execution engine, and
nothing in authoring, validating or publishing a bundle needs an installed
or even named runtime. The site decides which of the declared images its
engine consumes.

### Decision

- **Optional metadata, extracted never invented.** `container_engine` is
  optional execution-profile metadata. Seeding extracts it only from an
  explicitly declared engine in the relevant Nextflow configuration; when
  nothing is declared the field stays null and the config scaffold carries
  no engine block. No default is invented for any site.
- **No gate, no blocker.** A missing engine is neither a draft validation
  error nor a publication blocker: the 0.3.0 execution-profiles schema (not
  yet released) drops the field from `required` and admits `null`; the
  published document records `null`; the published-tree checker accepts
  absence. Deployment readiness checks sources against a runtime only when
  the default profile names one, and notes the absence otherwise.
- **Validate what is supplied.** A supplied value must be one of the
  `ContainerEngine` vocabulary, must appear in the candidate's detected
  engines when there are any, and a profile whose native config enables a
  different engine is reported as a genuine contradiction
  (`engine_conflict`, a warning). The Slurm site scaffold keeps its explicit
  `singularity`.
- **Images are not engines.** Component container images and their
  engine-specific alternatives are declarations for a profile's runtime
  choice, not the runtime itself; the component-side rule that source images
  name a concrete runtime is unchanged. `ContainerRuntime` (image sources)
  and `ContainerEngine` (profile metadata) stay distinct vocabularies.

### Alternatives rejected

- A neutral `any` member in `ContainerEngine`: hides the absence behind a
  fake value, and validation against it means nothing.
- Keeping the hard requirement and accepting the blocker as honest friction:
  it makes a site decision block the stages downstream of authoring, which
  the evaluation showed agents resolve by inventing values.
- Silent acceptance with no contradiction check: a profile that names docker
  while its config enables only singularity is a real defect worth surfacing.

### Consequences

- The two evaluation blockers shaped by this field become ordinary draft
  states; the ambiguous pipeline's profiles stage can complete.
- Deployment readiness of an engine-free default reports a note, not a
  block; ingestion readiness still demands every other dimension.
- The unreleased 0.3.0 execution-profiles schema is relaxed in place rather
  than revised, because no bundle has been published against it; consumers
  of draft bundles on the wip branch regenerate with `nf-splice build`.

## ADR-0071: One first-run journey: task-oriented help, a safe working copy, a capability-aware Welcome

| Metadata | Value |
|---|---|
| Status | Current |
| Date | 2026-10-19 |
| Source | Blocking first-run researcher UAT of 0.3.0 (help output, README and guides, `source prepare`, the Welcome page and form rendering) |
| Scope | CLI help and entry points, source isolation, the workspace's Welcome page, AI provider readiness, form control styling, user documentation |
| Supersedes | — |
| Superseded by | — |
| Related | ADR-0062, ADR-0067 (amends the Welcome page and AI availability it describes) |
| Implementation | `src/nf_splice/interfaces/help.py`, `src/nf_splice/cli.py`, `src/nf_splice/services/source.py`, `src/nf_splice/agents/providers/readiness.py`, `src/nf_splice/interfaces/tui/pages/start.py`, `src/nf_splice/interfaces/tui/app.py`, `src/nf_splice/interfaces/tui/launcher.py`, `src/nf_splice/interfaces/tui/provider_setup.py`, `src/nf_splice/interfaces/tui/tui.tcss`, `README.md`, `docs/guide/getting-started.md` |
| Tests | `tests/test_first_run.py`, `tests/test_cli.py`, `tests/test_tui.py`, `tests/test_tui_agents.py` |

### Context

A new researcher's first contact with 0.3.0 contradicted itself. Root
`--help` drew about 25 commands in Rich panels as wide as the terminal,
architecture first. The README told people to run `init` in the pipeline
itself, the getting-started guide to prepare a copy first, the workspace
and AI guides to start elsewhere; the working-copy guide promised the
original is never changed while `init` changed it. `source prepare` ended by
asking for another command with a long absolute path. The Welcome page
offered AI actions whether or not any provider worked. Form controls used
Textual's `tall` border, whose partial-block glyphs (U+258A and U+258E)
repeat on every row and, in fonts whose block glyphs do not fill the cell
height, show as a column of square blocks; a `Select` had two such frames,
one on itself and one on its `SelectCurrent`.

### Decision

- **Help is organised by task.** Root `--help` names the starting points
  (`nf-splice`, `nf-splice source prepare PATH`, `nf-splice tui`) and the
  everyday authoring, validation and AI commands; `--help-all` lists every
  command by task with each group's subcommands. All help is plain text from
  Click's formatter, at most 100 columns, wrapped without breaking at hyphens,
  with no panels and no escape sequences. Command help stays complete.
- **One lifecycle, several interfaces.** Pipeline, safe working copy,
  Welcome, a chosen mode, the shared services, review and publish. Drafts
  are created only where nf-splice is authorised: a copy made by `source
  prepare`, a folder whose in-place consent is recorded (`source prepare
  --in-place --yes`, `init --in-place`, or *Work in this folder instead…* on
  Welcome), or a folder that already has drafts. `init`, the workspace and
  `session start` otherwise refuse and say how to make a copy.
- **Interactive hand-off.** In a terminal, `source prepare` opens the
  workspace on the new copy at Welcome; `--no-open`, `--json` and
  non-terminal output keep the old behaviour. A bare `nf-splice` in a
  terminal opens the workspace on the current folder at Welcome, or, outside
  a pipeline, a chooser of remembered working copies (kept in the person's
  configuration folder) and of a folder or URL to prepare. Without a
  terminal it prints the help and exits with status 2; it never prompts.
  `--help` and `--version` are eager and never open the workspace.
- **Readiness is verified, never assumed.** AI readiness has five levels
  (not configured, set-up incomplete, configured but not verified, verified,
  previously verified but unavailable). Only a passing connection test for
  the same provider, model, sign-in method and account makes it verified;
  the record holds no secret and lives in the person's preferences. Welcome
  offers Assisted and Autonomous integration, and the workspace shows its
  AI actions, only when verified; otherwise it offers manual integration and
  a guided set-up over the existing provider services. Remote-model consent
  for repository context is still asked in the dock; approvals, scopes and
  validation are unchanged.
- **Controls are framed with box-drawing lines.** Inputs, text areas,
  selects (their `SelectCurrent` and overlay), radio sets and dialogs use
  `round` or `heavy` borders; no vertically repeated partial-block border
  remains. Labelled fields stack below the wide layout so controls keep a
  usable width.

### Alternatives rejected

- Keeping Rich help and narrowing it with `rich_help_panel` groups: the
  panels still stretch to the terminal and colour codes leak into pipes.
- A second welcome or launcher workspace: the chooser only picks a folder;
  everything else is the one workspace (ADR-0067).
- Treating a saved provider or an installed SDK as ready: it is exactly the
  misleading state the UAT reported.
- Refusing every command outside a working copy: read-only commands and
  existing in-place drafts keep working; only creating drafts needs consent.

### Consequences

- `init` in an original pipeline now fails with guidance; CI authorises its
  disposable checkout with `init --in-place`.
- The README quick start, the guides, root help and Welcome describe the
  same journey and are tested together (`tests/test_first_run.py`).
- A provider must pass `nf-splice provider test` (or the workspace's test)
  before the workspace offers agent modes; `session start` warns but runs.

