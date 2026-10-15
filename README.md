<div align="center">
  <picture>
    <source media="(prefers-color-scheme: light)" srcset="assets/splice_logo_acronym_black.png">
    <source media="(prefers-color-scheme: dark)" srcset="assets/splice_logo_acronym_white.png">
    <img src="assets/splice_logo_acronym_black.png" alt="SPLICE logo" width="180">
  </picture>

# nf-SPLICE

Author, review and maintain the SPLICE workflow bundle of a Nextflow pipeline.

</div>

## What nf-SPLICE 0.3.0 does

`nf-splice` inspects a pipeline repository, turns what it finds into
**editable draft files** with the evidence and open questions clearly marked,
and publishes a validated **SPLICE workflow bundle** under `splice/` once a
person has reviewed every decision.

- **Drafts are the source of truth.** One YAML draft per layer below
  `splice/drafts/` (identity, inputs, outputs, components, execution profiles,
  RO-Crate) plus native `.config` drafts. Edit them in any editor, through the
  CLI, the guided terminal wizard or an optional AI assistant; all routes use
  the same validated services and never overwrite each other's edits.
- **Five versioned public contracts**: `bundle.json`, `inputs.schema.json`,
  `outputs.schema.json`, `components.json` and `execution-profiles.json`, each
  with an engine-neutral family URI under
  `https://schemas.splice-data.io/workflow-bundle/`, a packaged formal
  definition and a per-key reference ([`docs/CONTRACTS.md`](docs/CONTRACTS.md)).
- **SPLICE platform units**: outputs are classified per **job** (the whole
  workflow execution), **sample** or platform **run** (a file-level unit of a
  sample). See [`docs/GLOSSARY.md`](docs/GLOSSARY.md).
- **Safe by construction**: evidence is never accepted silently, publication
  is atomic and recoverable, published files are never overwritten after
  external edits without explicit instruction, the developer's root
  RO-Crate and adopted configs are never modified, and container images are
  only marked downloadable after nf-splice has verified their checksum.
- **AI is optional and off by default.** The whole workflow works offline
  without credentials. With `nf-splice[claude]`, an assistant can propose
  changes through restricted tools; only a human approval applies them.

## Install

nf-splice supports Python 3.10 to 3.14.

```bash
python -m pip install nf-splice
python -m pip install 'nf-splice[claude]'
nf-splice --version
```

The second command adds the optional Claude Agent SDK provider; it is not
needed for any deterministic feature.

## Quick start

```bash
cd my-pipeline
nf-splice init --accept-detected --contract-version 1.0.0
nf-splice status
nf-splice tui
```

`init` creates only absent drafts from repository evidence. `tui` opens the
guided wizard, which takes you through identity, inputs, outputs, components,
execution profiles and provenance to a reviewed publication. The same steps
are available non-interactively:

```bash
nf-splice configure inputs --set genome=user,agent --set outdir=platform
nf-splice configure outputs --export-unresolved pending.json
nf-splice configure components --accept-detected --require-downloadable false
nf-splice configure execution-profiles --slurm-default
nf-splice configure provenance --strategy include
nf-splice draft validate
nf-splice plan --json
nf-splice build all
nf-splice validate
```

Each completed job then gets its own `analysis_output.json`:

```bash
nf-splice analysis-output generate --publish-directory results \
  --job-metadata job.json --sample-metadata samples.csv --output-directory results
```

The complete walkthrough is in [`docs/USAGE.md`](docs/USAGE.md).

## Existing 0.1.0 integrations

Bundles created with nf-splice 0.1.0 keep working at runtime. Migrate their
`splice/nf-splice.yaml` into drafts with a preview first:

```bash
nf-splice migrate drafts
nf-splice migrate drafts --apply
```

See [`docs/CONTRACT_MIGRATION_0.3.0.md`](docs/CONTRACT_MIGRATION_0.3.0.md) for
the field mappings and the platform rollout order.

## Privacy and security

- Git identity is only a suggestion; review events carry a public actor
  label. Contact details stay in a private local audit store outside the
  repository; public maintainer contacts are opt-in.
- No secrets, accounts, private paths or organisation endpoints are written
  into generated configs or bundles; config safety checks block them.
- Network access (image verification, uploads) and remote AI disclosure always
  require an explicit request.

## Documentation

| Topic | Document |
| --- | --- |
| Full CLI and TUI workflow | [`docs/USAGE.md`](docs/USAGE.md) |
| Contracts, registry, ingestion read order | [`docs/CONTRACTS.md`](docs/CONTRACTS.md), [`docs/schemas/`](docs/schemas/) |
| 0.1.0 → 0.3.0 migration | [`docs/CONTRACT_MIGRATION_0.3.0.md`](docs/CONTRACT_MIGRATION_0.3.0.md) |
| Vocabulary (job, sample, run; reserved words) | [`docs/GLOSSARY.md`](docs/GLOSSARY.md) |
| Terminal wizard | [`docs/TUI.md`](docs/TUI.md) |
| Containers and image distributions | [`docs/CONTAINERS.md`](docs/CONTAINERS.md) |
| RO-Crate and attribution | [`docs/PROVENANCE.md`](docs/PROVENANCE.md) |
| Optional AI assistance | [`docs/AGENTS.md`](docs/AGENTS.md) |
| Architecture decisions | [`docs/ARCHITECTURE_DECISIONS.md`](docs/ARCHITECTURE_DECISIONS.md) |
| Release record and ledger | [`docs/RELEASE_0.3.0.md`](docs/RELEASE_0.3.0.md) |

## Development

```bash
. scripts/dev-env.sh
python -m venv .nf-splice-local/venv && . .nf-splice-local/venv/bin/activate
python -m pip install -e '.[dev]'
scripts/run-checks.sh
```

All local scratch files, caches, test output and sessions stay in the
ignored `/.nf-splice-local/` workspace; `scripts/check_staged_paths.py` (also
usable as `scripts/pre-commit`) rejects staged development-only files.

## Licence

MIT; see [`LICENSE`](LICENSE).
