# Contract migration: nf-splice 0.1.0 → 0.3.0

> nf-splice 0.1.0 was a pre-release test version. Its files were never a
> supported contract, and integrations should implement 0.3.0 only, starting
> from [Building on SPLICE bundles](CONTRACTS.md). This note records how the
> 0.1.0 test files map to 0.3.0, for anyone converting leftover test bundles
> with `nf-splice migrate drafts`.

Frozen 0.1.0 test files live in `tests/fixtures/legacy-0.1.0/`; 0.3.0
examples in `docs/schemas/*/v0.3.0/example.json`.

## Summary of changes

| Area | 0.1.0 | 0.3.0 |
| --- | --- | --- |
| Contract identity | `schema_version: "1.0"` in three files, none in the schemas | Five family URIs `https://schemas.splice-data.io/workflow-bundle/{bundle,inputs,outputs,components,execution-profiles}`, revision `0.3.0`; `x-splice-contract` in JSON Schema documents |
| Bundle index | `bundle_format`, `schema_version: "1.0"`, `pipeline{id,name,version,engine}`, `files` | Same `bundle_format` and `files`; `schema_id`, `schema_version: "0.3.0"`, `generated_by`, rich ordered `pipeline`, opt-in `maintainers`, five-family `schemas` map, `default_execution_profile` |
| Authoring state | `splice/nf-splice.yaml` | Per-layer drafts in `splice/drafts/`; `nf-splice.yaml` is read-only migration input |
| Output scopes | `run` = workflow-wide, `sample`, `library` | `job` = workflow job, `sample`, `run` = platform file-level run with `run_id` and parent `sample_id`; `library` is never a scope |
| Output categories | Controlled enum (`run_report`, …) | Free text; `job_report` suggested for job outputs |
| Output catalogue for runtime | `outputs.yaml` | `outputs.schema.json` → `x-output-catalog` only |
| Job metadata | top-level `platform_run_id`, `workflow_run_id`, `nextflow_session_id`, `nextflow_run_name`, `run_metadata` | top-level `job_id_short`/`job_id_long` (required) and `job_metadata{engine, engine_execution_id, nextflow{session_id, run_name}, annotations}` |
| Inputs | Filtered copy with only user-configurable parameters | Every runnable parameter, lossless nf-schema import, `x-splice-access.editable_by` per parameter |
| Containers | `{id, type, uri}` with heuristic type | Same keys plus `source_images` per runtime, verified `distribution`, `resolution`; `type`/`uri` describe a verified download or a native registry reference |
| Profiles | Eight keys per profile | Plus `default`, `config_strategy`, `site_parameters`; top-level `default_profile` |
| RO-Crate | Root file copied unchanged | Reviewed `include`, `enriched` or `generated` strategy; root never modified |
| Lock | format 1.0 with `selected_evidence` | format 2.0 with `contracts`, source roles and RO-Crate provenance |

## Field mapping: output scopes

Migration is selected by the **source contract version**, never by string
replacement.

| 0.1.0 value | 0.3.0 value | Rule |
| --- | --- | --- |
| `run` | `job` | Always (workflow-wide output). |
| `sample` | `sample` | Always. |
| `library` | `run` | Only with an explicit reviewed mapping that library identifiers are platform run identifiers (`nf-splice migrate drafts --map-library-to-run`, rewriting `{library}` to `{run}`). Otherwise a migration blocker. |
| category `run_report` | `job_report` | Reported transformation; other categories stay literal. |

Before (0.1.0 record):

```json
{"path": "qc/S1/S1_L001.json", "category": "quality_control",
 "output_type": "library_qc", "scope": "library", "library_id": "S1_L001"}
```

After (0.3.0 record, with the reviewed mapping and a samplesheet `run_id`):

```json
{"path": "qc/S1/S1_L001.json", "category": "quality_control",
 "output_type": "library_qc", "scope": "run", "run_id": "S1_L001",
 "sample_id": "S1"}
```

## Field mapping: job metadata

| 0.1.0 (`--run-metadata`) | 0.3.0 (`--job-metadata`) |
| --- | --- |
| `job_id_short`, `job_id_long`, `config_profile`, `execution_timestamp` | unchanged, top level |
| `workflow_run_id` | `job_metadata.engine_execution_id` |
| `nextflow_session_id` | `job_metadata.nextflow.session_id` |
| `nextflow_run_name` | `job_metadata.nextflow.run_name` |
| `run_metadata.*` and unknown keys | `job_metadata.annotations.*` |
| `platform_run_id` | **rejected**: neither a job nor a platform run; supply job ids explicitly |

`--run-metadata` remains as a deprecated alias that converts these fields.

## Input permissions

| 0.1.0 classification | 0.3.0 `editable_by` | visibility |
| --- | --- | --- |
| `user-configurable` | `[user]` | unchanged |
| `platform-managed` | `[platform]` | unchanged |
| `execution-environment-managed` | `[platform]` | `hidden` |
| `hidden-or-unsupported` | `[]` | `hidden` |

Access is never widened by migration. Agents (`agent`) must be granted
explicitly.

## Platform deployment order

1. Upgrade ingestion/DEX to read 0.3.0: dispatch on `bundle.json`
   `schema_version` (`1.0` legacy, `0.3.0` new) and implement the read order
   in `CONTRACTS.md`.
2. Keep the 0.1.0 reader for existing bundles; a legacy bundle's
   `analysis_output.json` keeps 0.1.0 semantics (nf-splice reproduces it
   byte-for-byte from a legacy contract).
3. Only then onboard 0.3.0 bundles. An unmodified 0.1.0 consumer cannot read
   a 0.3.0 bundle (new `schema_version`, scopes and job metadata); no
   compatibility export is produced.

## Migrating a repository

```bash
nf-splice migrate drafts --repository . --json
nf-splice migrate drafts --repository . --apply --map-library-to-run
nf-splice draft validate --repository .
nf-splice configure execution-profiles --default profile-local-6c6f63616c
nf-splice build all --replace-existing
nf-splice validate
```

The preview lists every transformed, defaulted, unmapped, permission and
blocking value. Applying creates only absent drafts; the legacy
`nf-splice.yaml` and the published 0.1.0 files remain byte-identical until a
reviewed publication replaces the published files.

## Consumer test recipe

```bash
nf-splice schema validate docs/schemas/bundle/v0.3.0/example.json
nf-splice schema show outputs > outputs-family.schema.json
nf-splice analysis-output validate analysis_output.json --repository .
```
