<div align="center">
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="assets/splice_logo_acronym_black.png">
    <source media="(prefers-color-scheme: dark)" srcset="assets/splice_logo_acronym_white.png">
    <img src="assets/splice_logo_acronym_black.png" alt="SPLICE logo" width="180">
  </picture>

# nf-SPLICE

Build and maintain the integration harness that prepares a Nextflow pipeline
for submission to the SPLICE platform.

</div>

## What nf-SPLICE does

`nf-splice` is an assisted authoring tool for Nextflow pipeline developers. It
inspects a pipeline repository, presents the evidence it can detect, asks the
developer to resolve decisions that cannot be made safely, and builds the
reviewed files required by SPLICE.

The tool is designed to help you:

- describe pipeline inputs and outputs for the platform;
- record pipeline identity, components, execution profiles, and provenance;
- review inferred values instead of accepting hidden guesses;
- generate a consistent integration bundle under `splice/`;
- validate the bundle before committing it with the pipeline; and
- reopen and maintain an existing nf-SPLICE integration as the pipeline evolves.

`nf-splice` does not convert a pipeline automatically or replace pipeline
testing. If required information is missing or conflicting, it identifies the
affected integration layer and waits for an explicit developer decision.

## Who it is for

Use `nf-splice` if you develop or maintain a Nextflow pipeline that will be
submitted to the SPLICE platform. It works with an existing pipeline repository
and keeps the platform-specific integration separate from the pipeline's
scientific workflow logic.

```text
Nextflow pipeline repository
        │
        ▼
inspect evidence → review decisions → build and validate
        │
        ▼
SPLICE integration harness in splice/
        │
        ▼
pipeline ready for SPLICE submission
```

## Project status

nf-SPLICE is currently an early development preview. The installable package,
Python compatibility baseline, repository inspection, reviewed pipeline
identity, output discovery and review, workspace status, and terminal workspace
are available. Reviewed output contracts and per-run `analysis_output.json`
generation and validation are also available. Reviewed input projection,
software-component inventory, and safe migration from the superseded root-level
state layout are available. Reviewed execution-profile selection, safe config
materialisation, and deterministic workflow RO-Crate provenance are also
available. Complete read-only planning, bundle and lock generation, controlled
whole-integration builds, and bundle-wide validation are available.

This README tracks user-visible functionality as it becomes available. Commands
will only move into the usage guide after their behaviour is implemented and
verified.

## Installation

The current preview can be installed from a local clone:

```bash
git clone https://github.com/Beatson-CompBio/nf-SPLICE.git
cd nf-SPLICE
python -m pip install .
nf-splice --version
```

nf-SPLICE supports Python 3.10 through 3.14. It is designed to coexist with the
Python environment used by nf-core tooling without depending on nf-core
internals.

## Current commands

Inspect a pipeline repository and initialise its reviewed identity:

```bash
nf-splice inspect
nf-splice status
nf-splice init \
  --name my-pipeline \
  --pipeline-version 1.0.0 \
  --repository-url https://github.com/my-org/my-pipeline
```

`init` creates the version-controlled `splice/nf-splice.yaml` and creates the
`splice/` directory if needed. Values can be supplied
explicitly, or unambiguous values from `nextflow.config` and Git can be reviewed
and accepted with `--accept-detected`. Missing values, conflicting evidence,
and placeholder identifiers are rejected rather than silently defaulted.

If an earlier preview created repository-root `nf-splice.yaml` or
`nf-splice.lock.json`, inspect and reconcile it explicitly:

```bash
nf-splice migrate-state
nf-splice migrate-state --apply
```

The first command is a read-only preview. Application validates compatible
state, refuses source/destination conflicts, writes atomically, and preserves
the legacy source files. A repeated migration is byte-identical and makes no
changes.

Classify upstream parameters into their reviewed ownership boundary and build
the configurable projection:

```bash
nf-splice configure inputs \
  --set threshold=user-configurable \
  --export-unresolved unresolved-inputs.json
nf-splice build inputs --check
nf-splice build inputs
```

Input decisions classify each `nextflow_schema.json` parameter as
`user-configurable`, `platform-managed`, `execution-environment-managed`, or
`hidden-or-unsupported`. Only reviewed user-configurable parameters appear in
`splice/inputs.schema.json`. Existing upstream defaults are preserved;
ambiguous types and missing descriptions require explicit review, and the tool
does not invent scientific defaults.

Discover and review pipeline modules, tools, versions, containers, and Conda
evidence, then build the software inventory:

```bash
nf-splice configure components --accept-detected \
  --export-unresolved unresolved-components.json
nf-splice configure components \
  --set component:modules__local__tool.version=1.0 \
  --set component:modules__local__tool.container_uri=quay.io/example/tool:1.0
nf-splice build components --check
nf-splice build components
```

`--accept-detected` accepts only components without competing version or
container evidence. Conflicts stay unresolved until one detected value is
selected. Generated `splice/components.json` deterministically deduplicates
containers and retains source locations for every component.

Select the execution environments that SPLICE officially supports, classify
their platform type, and select the source config to register for each one:

```bash
nf-splice configure execution-profiles \
  --set profile:local.type=development \
  --set profile:local.description="Supported local execution" \
  --set profile:local.executor=local \
  --set profile:local.container_engine=singularity \
  --set profile:local.config_source=conf/local.config \
  --export-unresolved unresolved-profiles.json
nf-splice build execution-profiles --check
nf-splice build execution-profiles
```

Profiles detected in `nextflow.config` remain candidates until each is
explicitly selected or rejected. Every selected profile requires explicit
`type`, `description`, `executor`, `container_engine`, and `config_source`
values. Detected executor and container-engine evidence is shown as guidance
and constrains inconsistent selections; it is not silently accepted. Every
selected profile also requires exactly one explicitly chosen,
repository-local source `.config` outside `splice/`. The tool copies that file
byte-for-byte; it never combines configs or generates their content. The build
writes `splice/execution-profiles.json` and its referenced
`splice/configs/*.config` files together. It blocks embedded
credentials, personal paths, literal HPC accounts, production test/demo
settings, and reviewed scientific parameter overrides before writing any
target. A JSON decision file is useful when several profiles must be selected
or rejected in one review.

There is no limit on the number of selected profiles or on how many share the
same `type` or `executor`. Use the required description to distinguish profiles
with otherwise similar registrations. nf-splice assigns every selected profile
a deterministic unique `id` derived from its exact Nextflow source-profile name;
developers do not supply IDs. The platform document uses the stable keys `id`,
`name`, `description`, `type`, `engine`, `executor`, `container_engine`, and
`config`. `type`, `engine`, `executor`, and `container_engine` use controlled
vocabularies validated by both authoring and inspection.

Generate the pipeline RO-Crate with nf-core tooling, explicitly approve it, and
include it in the integration:

```bash
nf-core pipelines rocrate .
nf-splice configure provenance --set provenance.include=true
nf-splice build provenance --check
nf-splice build provenance
```

`ro-crate-metadata.json` must already be a regular file at the pipeline
repository root. If it is absent, nf-splice stops and instructs the developer to
run `nf-core pipelines rocrate .`, then retry. nf-splice does not create,
complete, or normalise RO-Crate metadata. After explicit inclusion review it
validates the RO-Crate structure and copies the root file byte-for-byte to
`splice/ro-crate-metadata.json`, leaving the developer-owned source unchanged.

Discover output candidates from pipeline source and optional completed output
evidence:

```bash
nf-splice configure outputs --publish-directory results \
  --contract-version 1.0.0 \
  --export-unresolved unresolved-outputs.json
nf-splice tui
```

Each command inspects the current directory by default. Use
`--repository PATH` to work with a different repository. Output discovery uses
native workflow outputs, process declarations, `publishDir` declarations,
module metadata, an optional example tree or publish directory, and a recognised
existing `splice/outputs.yaml`. Candidates remain unresolved until accepted,
rejected, merged, or split through an explicit decision file, repeatable
`--set CANDIDATE.FIELD=VALUE` options, or the terminal review form.

`inspect` reports detected evidence and existing `splice/` safety warnings,
`status` adds authoring and integration-layer readiness, and `tui` presents the
same shared result with an output candidate table, supporting evidence, and
vocabulary-backed review fields. The terminal workspace also exposes the same
input, component, execution-profile, and provenance review services as the CLI.
Equivalent CLI and terminal reviews use the same validation and produce
identical canonical state.

After every output decision is resolved and the output-contract version is
reviewed, preview and build the two deterministic output contracts:

```bash
nf-splice build outputs --check
nf-splice build outputs
```

The build writes `splice/outputs.yaml` and `splice/outputs.schema.json` from
reviewed authoring state only. `--check` prints the same file-level diff without
writing. A repeated build is byte-identical and leaves both files unchanged.
Differing recognised contracts require their displayed diff to be reviewed and
an explicit `--replace-existing`; malformed or unknown target content is never
overwritten.

For each completed run, generate the separate runtime inventory from exactly
one completed publish directory, native output index, or output-tree listing:

```bash
nf-splice analysis-output generate \
  --publish-directory results \
  --sample-metadata samplesheet.csv \
  --run-metadata run-metadata.json \
  --output-directory results
nf-splice analysis-output validate results/analysis_output.json
```

The generator classifies only produced outputs covered by the reviewed static
contract, handles optional outputs by omission, captures sample or library
identity from reviewed path patterns, and validates the resulting
`analysis_output.json` against `splice/outputs.schema.json` before writing it.
Unclassified produced paths fail by default and can only be omitted with the
explicit `--allow-unclassified` option. Optional checksums are available for a
live completed publish directory.

Preview the complete desired integration, build it only from reviewed state,
and validate every managed file and source relationship:

```bash
nf-splice plan all
nf-splice plan all --json
nf-splice build all --check --non-interactive
nf-splice build all --non-interactive
nf-splice validate
```

`plan` and `--check` never write. `build all` preflights every target before
the first write and refuses unresolved decisions, malformed recognised files,
unknown target content, and unreviewed replacement of differing generated
files. After reviewing a displayed diff, use `--replace-existing` only for
differing recognised generated artefacts. `--json` emits a stable result for
planning, every layer build, complete builds, and validation. A second complete
build from unchanged reviewed state is byte-identical.

`build bundle` refreshes only `bundle.json`, `README.md`, and
`nf-splice.lock.json`, and succeeds only when all referenced layer artefacts
already match current reviewed state. Normally, prefer `build all`.

## Intended workflow

A typical integration follows this flow:

1. Run `nf-splice inspect` in the pipeline repository.
2. Review detected evidence and unresolved decisions.
3. Initialise the version-controlled `splice/nf-splice.yaml` authoring state.
4. Configure and review each required integration layer.
5. Preview each reviewed layer with `nf-splice build LAYER --check`.
6. Preview with `nf-splice plan all` and `nf-splice build all --check`.
7. Build all reviewed integration layers under `splice/`.
8. Run `nf-splice validate` before committing and submitting the pipeline.

CLI and terminal UI workflows will use the same authoring state and application
rules, so developers can choose the interface that suits their workflow.

## Integration files

nf-SPLICE separates reviewed developer choices from generated platform files:

```text
splice/
├── nf-splice.yaml              reviewed, version-controlled authoring state
├── bundle.json                 platform bundle entry point
├── README.md                   generated bundle inventory and ownership guide
├── nf-splice.lock.json         generator, Git, source, and managed-file hashes
├── inputs.schema.json          reviewed configurable input projection
├── outputs.yaml                reviewed output catalogue
├── outputs.schema.json         runtime analysis-output contract
├── components.json             reviewed component and container inventory
├── execution-profiles.json     reviewed platform profile registrations
├── configs/*.config            byte-identical developer source-config copies
└── ro-crate-metadata.json      byte-identical developer root RO-Crate copy
```

The completed `splice/` bundle will describe the pipeline's inputs, outputs,
software components, supported execution profiles, configurations, workflow
metadata, and bundle provenance.

Existing files are inspected before generation. nf-SPLICE does not silently
delete unknown content or overwrite unresolved collisions.

For a complete tutorial, command reference, TUI walkthrough, file ownership
contracts, and recovery procedures, see the [authoring and operation guide](docs/USAGE.md).

The static output layer contains:

```text
splice/outputs.yaml         reviewed output catalogue materialisation
splice/outputs.schema.json  validation contract for analysis_output.json
```

The currently available input, software, execution, and provenance layers
contain:

```text
splice/inputs.schema.json       reviewed user-configurable parameter projection
splice/components.json          reviewed tools, versions, containers, and evidence
splice/execution-profiles.json  officially supported execution environments
splice/configs/*.config         validated configuration for selected profiles
splice/ro-crate-metadata.json   reviewed workflow RO-Crate metadata
```

`analysis_output.json` belongs to one completed run and is not part of the
static repository integration bundle or canonical authoring state.

## Authoring principles

- Detection produces evidence and candidates, not automatic acceptance.
- Reviewed and rejected choices survive later inspection runs.
- Missing or conflicting decisions block only the affected layer.
- Generated files are deterministic for the same reviewed state.
- Static integration authoring remains separate from per-run
  `analysis_output.json` generation.

## License

nf-SPLICE is available under the [MIT License](LICENSE).
