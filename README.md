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
Python compatibility baseline, read-only repository inspection, workspace
status, and terminal workspace are available. Authoring, planning, build, and
validation workflows are being delivered incrementally and are not yet
available in the current release.

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

Run the current read-only workflows from a Nextflow pipeline repository:

```bash
nf-splice inspect
nf-splice status
nf-splice tui
```

Each command inspects the current directory by default. Use
`--repository PATH` to inspect a different repository. `inspect` reports
detected evidence and existing `splice/` safety warnings, `status` adds
authoring and integration-layer readiness, and `tui` presents the same shared
result in a keyboard-navigable terminal interface.

The planned `init`, `configure`, `plan`, `build`, and `validate` command names
are visible in command help, but they exit explicitly as unavailable until their
reviewed application behaviour is implemented.

## Intended workflow

As the authoring commands become available, a typical integration will follow
this flow:

1. Run `nf-splice inspect` in the pipeline repository.
2. Review detected evidence and unresolved decisions.
3. Initialise the version-controlled `nf-splice.yaml` authoring state.
4. Configure and review each required integration layer.
5. Preview the proposed file changes with `nf-splice plan`.
6. Build the reviewed integration under `splice/`.
7. Run `nf-splice validate` before committing and submitting the pipeline.

CLI and terminal UI workflows will use the same authoring state and application
rules, so developers can choose the interface that suits their workflow.

## Integration files

nf-SPLICE separates reviewed developer choices from generated platform files:

```text
nf-splice.yaml       reviewed, version-controlled authoring state
nf-splice.lock.json  generator provenance and generated-file hashes
splice/              materialised SPLICE integration harness
```

The completed `splice/` bundle will describe the pipeline's inputs, outputs,
software components, supported execution profiles, configurations, workflow
metadata, and bundle provenance.

Existing files are inspected before generation. nf-SPLICE does not silently
delete unknown content or overwrite unresolved collisions.

## Authoring principles

- Detection produces evidence and candidates, not automatic acceptance.
- Reviewed and rejected choices survive later inspection runs.
- Missing or conflicting decisions block only the affected layer.
- Generated files are deterministic for the same reviewed state.
- Static integration authoring remains separate from per-run
  `analysis_output.json` generation.

## License

nf-SPLICE is available under the [MIT License](LICENSE).
