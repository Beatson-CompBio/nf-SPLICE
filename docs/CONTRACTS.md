# SPLICE workflow-bundle contracts

nf-splice publishes exactly five public JSON contract families plus two
companion artefacts. Families are engine-neutral: another generator (for
example for Snakemake) can emit the same revisions. Vocabulary is defined in
[`GLOSSARY.md`](GLOSSARY.md); decisions in ADR-0024, ADR-0027, ADR-0028,
ADR-0032 to ADR-0036.

| Published file | Family URI | Revision (nf-splice 0.3.0) | Field reference |
| --- | --- | --- | --- |
| `bundle.json` | `https://schemas.splice-data.io/workflow-bundle/bundle` | `0.3.0` | [bundle](schemas/bundle/README.md) |
| `inputs.schema.json` | `https://schemas.splice-data.io/workflow-bundle/inputs` | `0.3.0` | [inputs](schemas/inputs/README.md) |
| `outputs.schema.json` | `https://schemas.splice-data.io/workflow-bundle/outputs` | `0.3.0` | [outputs](schemas/outputs/README.md) |
| `components.json` | `https://schemas.splice-data.io/workflow-bundle/components` | `0.3.0` | [components](schemas/components/README.md) |
| `execution-profiles.json` | `https://schemas.splice-data.io/workflow-bundle/execution-profiles` | `0.3.0` | [execution-profiles](schemas/execution-profiles/README.md) |

The URIs are identifiers and planned documentation locations, not deployed
URLs; validation is fully offline from packaged definitions. Each family has
a formal definition (`docs/schemas/<family>/v0.3.0/schema.json`, identical to
the wheel-packaged copy), an example and a generated per-key reference.

Companion artefacts with their own validation, outside the five families:
`outputs.yaml` (developer-readable output catalogue, `catalogue_format_version`
`0.3.0`), `ro-crate-metadata.json` (RO-Crate 1.1 / Workflow RO-Crate), the
lock `nf-splice.lock.json` (format `2.0`) and `README.md`. There is **no**
`outputs.json`.

## Identity of documents

- JSON Schema documents (`inputs.schema.json`, `outputs.schema.json`) keep a
  standard `$schema` dialect (2020-12 and draft-07 respectively) and their own
  per-pipeline `$id`; the family URI and revision are in `x-splice-contract`.
- Data documents (`bundle.json`, `components.json`, `execution-profiles.json`)
  carry `schema_id`, `schema_version` and `generated_by`.
- Every detached file repeats the workflow identity envelope (`id`, `name`,
  `version`, `engine`) so it can be checked against `bundle.json`.

## Release-to-contract registry

`nf-splice schema list --json` prints the packaged registry
(`src/nf_splice/contracts/data/registry.json`). Every nf-splice release has an
explicit row; a later release that does not change a family re-registers the
same revision. Pipeline versions, the per-pipeline
`analysis_output_schema_version`, the lock format and the tool version are
separate concepts.

| nf-splice | bundle | inputs | outputs | components | execution-profiles |
| --- | --- | --- | --- | --- | --- |
| 0.1.0 | legacy 1.0 (unregistered) | unversioned | unversioned | legacy 1.0 | legacy 1.0 |
| 0.3.0 | 0.3.0 | 0.3.0 | 0.3.0 | 0.3.0 | 0.3.0 |

## Validation commands

```bash
nf-splice schema list --json
nf-splice schema show outputs
nf-splice schema validate splice/components.json --json
nf-splice schema check --repository . --json
nf-splice validate --json
```

`schema validate` checks one document (JSON Schema documents are first checked
as schemas of their dialect, then for SPLICE extensions). `schema check`
validates all five published files. `validate` additionally checks the
`schemas` map, cross-file identity, the YAML/JSON output projection, draft
markers, forbidden files and lock hashes.

## Ingestion read order

1. Read `bundle.json`; reject unknown `schema_version`s (bundle 1.0 is a
   legacy 0.1.0 bundle).
2. Use `schemas` and `files` to locate the other four documents; validate
   each against its family revision.
3. Check every identity envelope against `bundle.json` `pipeline`.
4. Read output metadata only from `outputs.schema.json` → `x-output-catalog`
   (YAML is for developers). Validate each job's `analysis_output.json`
   against the same file.
5. Resolve images from `components.json`: use `distribution` for verified
   downloads (check `sha256`), otherwise the native `source_images`. If
   `require_downloadable_images` is true and an image cannot be fetched,
   fail the ingestion of that bundle rather than guessing.
6. Select `default_execution_profile` unless the operator chooses another.

## `x-output-catalog`

The embedded catalogue lists every reviewed output type with free-text
`category`/`stage`, `scope` (`job`, `sample`, `run`), `entity_type`, `format`
and anchored `path_patterns` (`{sample}` captures `sample_id`, `{run}`
captures the platform `run_id`). Each completed job produces one
`analysis_output.json` with records at job, sample or run granularity; run
records carry both `run_id` and the parent `sample_id`, and the document
carries `job_id_short`/`job_id_long` plus engine-qualified `job_metadata`.

## Compatibility policy

A family revision is immutable. Removing or renaming keys, narrowing types or
enums, changing constants, closing objects or adding requiredness requires a
new revision, a migration path and fixtures (`nf-splice schema check
--against OLD --family F` reports such changes). Additive optional keys are
compatible. Consumers that only understand 0.1.0 bundles cannot read 0.3.0
bundles without an adapter; see
[`CONTRACT_MIGRATION_0.3.0.md`](CONTRACT_MIGRATION_0.3.0.md).
