# Using nf-splice 0.3.0

This walkthrough takes a Nextflow pipeline from an empty repository to a
validated SPLICE workflow bundle, first with the command line and then with
the guided wizard. Both use the same services and produce identical files.

## 1. Files and lifecycle

```text
splice/
  drafts/                         editable, authoritative working files
    bundle.draft.yaml             identity and metadata
    inputs.schema.draft.yaml      input contract (JSON Schema 2020-12 in YAML)
    outputs.draft.yaml            the only output draft
    components.draft.yaml         components and containers
    execution-profiles.draft.yaml profiles and the default
    ro-crate-metadata.draft.yaml  RO-Crate strategy
    configs/<id>.draft.config     generated configs (native Nextflow)
    .reviews/<layer>.review.json  evidence, candidates, review events
  bundle.json  inputs.schema.json  outputs.yaml  outputs.schema.json
  components.json  execution-profiles.json  ro-crate-metadata.json
  configs/<id>.config  README.md  nf-splice.lock.json
```

Drafts carry an `x-splice-draft` marker, write unknown values as `null` and
are never overwritten by discovery. Readiness is derived from their current
bytes every time. Detected values are suggestions until confirmed or edited.
Edit drafts directly whenever you like; nf-splice applies its own changes as
targeted patches and reports conflicts instead of overwriting yours.

## 2. Inspect

```bash
nf-splice inspect
nf-splice status --json
```

Both are read-only.

## 3. Initialise

```bash
nf-splice init --accept-detected --contract-version 1.0.0
```

`init` reads `nextflow.config` (the Nextflow metadata scope), Git, `CITATION.cff`,
`README.md` and any root RO-Crate as evidence, seeds `bundle.draft.yaml`,
imports `nextflow_schema.json`, discovers outputs, components and profiles,
and creates only absent drafts. `--accept-detected` confirms unanimous
detected identity values; conflicting evidence is left `null` for you to
decide. Pass `--name`, `--pipeline-version`, `--repository-url`,
`--description`, `--title` or `--licence` to author values directly.

Global option `--actor "Your Name"` (or `NF_SPLICE_ACTOR`) labels review
events; Git e-mail is never used.

## 4. Identity

```bash
nf-splice configure identity --set description="Quantifies RNA-seq reads." \
  --set 'authors=[{"name": "Ada Lovelace", "orcid": "https://orcid.org/0000-0002-1825-0097"}]'
nf-splice draft inspect bundle
nf-splice draft confirm bundle /pipeline/licence
```

Issues are reported per JSON pointer (placeholders, invalid URLs or ORCIDs,
release URL not matching the version, contradictory minimum Nextflow
version, maintainer contacts without publication consent).

## 5. Inputs

```bash
nf-splice configure inputs --set genome=user,agent --set outdir=platform \
  --set max_cpus=platform --visibility max_cpus=hidden
```

Every parameter stays in the contract and needs one `editable_by` policy
(`user`, `platform`, `agent`, or empty for fixed). Visibility is presentation
only. If `nextflow_schema.json` changes, `nf-splice configure inputs --reimport`
merges the upstream change without resetting your edits (overlaps block).

## 6. Outputs

```bash
nf-splice configure outputs --example-output-tree example-results --export-unresolved pending.json
nf-splice configure outputs \
  --set 'output:0123456789abcdef.key=multiqc_report' \
  --set 'output:0123456789abcdef.category=job_report' \
  --set 'output:0123456789abcdef.scopes=job' \
  --set 'output:fedcba9876543210.action=reject' \
  --set 'output:fedcba9876543210.reason=Not published'
nf-splice configure outputs --decision-file decisions.yaml
nf-splice preview outputs --format json
```

Candidate IDs are stable. Scopes are `job`, `sample` (`{sample}` in the
pattern) or `run` (`{run}` in the pattern). Categories and stages are free
text. A decision file holds `actions` of `accept`, `reject`, `merge`, `split`
and `version`. The JSON preview is derived and never written.

## 7. Components and images

```bash
nf-splice configure components --accept-detected --require-downloadable true
nf-splice configure components --set 'component:modules__local__multi.docker=quay.io/a/b:1'
nf-splice containers verify container-0123456789ab https://images.example.org/image.img
```

See [`CONTAINERS.md`](CONTAINERS.md).

## 8. Execution profiles

```bash
nf-splice configure execution-profiles \
  --set profile:local.type=development \
  --set profile:local.description="Local development." \
  --set profile:local.executor=local \
  --set profile:local.container_engine=singularity \
  --set profile:local.config_source=conf/local.config
nf-splice configure execution-profiles --slurm-default
nf-splice configure execution-profiles --default profile-local-6c6f63616c
```

`config_source` adopts a repository config byte-for-byte; `generate=true`
creates an editable generated config with the
`// ***** User Pipeline Input Params *****` and
`// ***** SPLICE Pipeline Input Params *****` sections. Exactly one default
must be chosen. Site settings are operator configuration.

## 9. Provenance

```bash
nf-splice configure provenance
nf-splice configure provenance --strategy enriched
```

See [`PROVENANCE.md`](PROVENANCE.md).

## 10. Validate and publish

```bash
nf-splice draft list
nf-splice draft validate
nf-splice draft diff outputs
nf-splice draft promote outputs
nf-splice plan --json
nf-splice build all --check
nf-splice build all
nf-splice validate --json
```

A single ready layer can be promoted while others remain drafts.
`build all` publishes the whole bundle only when every layer is ready;
writes are staged and the lock and `bundle.json` are written last. Updating
published files needs `--replace-existing` after reviewing the diff. A
published file edited by hand is preserved and blocks publication until you
reconcile it into the draft or name it with `--overwrite-edited`. After an
interrupted publication run `nf-splice draft recover`. Raw patches can be
previewed and applied with `nf-splice draft edit <layer> --patch ops.json
[--apply]`.

## 11. Job outputs

```bash
nf-splice analysis-output generate --publish-directory results \
  --job-metadata job.json --sample-metadata samples.csv --output-directory results
nf-splice analysis-output validate results/analysis_output.json
```

`job.json` holds `job_id_short`/`job_id_long` and optional `job_metadata`.
The sample metadata CSV may contain a `run_id` column mapping platform runs
to samples. `--run-metadata` is a deprecated 0.1.0 alias.

## 12. The wizard

```bash
nf-splice tui
nf-splice tui --no-session
```

See [`TUI.md`](TUI.md). For optional AI assistance see
[`AGENTS.md`](AGENTS.md).

## 13. CI

The committed drafts are the reproducible decisions. In CI:

```bash
nf-splice draft validate
nf-splice build all --check --json
nf-splice validate --json
nf-splice schema check --json
```

## Troubleshooting

| Message | Meaning |
| --- | --- |
| `unconfirmed_detected_value` | A detected value is still unreviewed: confirm or edit it. |
| `conflicting_evidence` | Sources disagree; set the field explicitly. |
| `pending_candidate` | A discovered candidate needs accept/reject/merge/split. |
| `access_unreviewed` | A parameter has no `x-splice-access`. |
| `identity_mismatch` | Run `nf-splice draft sync-identity`. |
| `needs_materialisation` | A required downloadable image is not verified. |
| `edited after it was published` | A published file was changed by hand. |
| `legacy_bundle` | Run `nf-splice migrate drafts`. |
