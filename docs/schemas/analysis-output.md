# `analysis_output.json`

The inventory of everything one completed job published. Each job of a
workflow produces exactly one `analysis_output.json`. It lists every output
file or directory, says what kind of output it is and says whether it
belongs to the job, a sample or a sequencing run.

| | |
| --- | --- |
| Validated by | The bundle's `outputs.schema.json` (JSON Schema draft-07) |
| Version | `x-output-catalog.analysis_output_schema_version` of that file |
| Written by | `nf-splice analysis-output generate`, after the job finishes |
| Read by | Platforms that register, store and display job results |

Unlike the five bundle files, this document is written for each job and its
exact schema is specific to the workflow: the permitted `output_type`
values, their categories and path patterns come from the workflow's reviewed
output catalogue. The structure below is the same for every workflow.

## Document

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `analysis_output_schema_version` | version `X.Y.Z` | yes | Version of the workflow's output schema that validated this document. |
| `schema_id` | string | yes | Identifier of that schema; equal to the `$id` of `outputs.schema.json`. |
| `pipeline_name` | string | yes | Workflow name. |
| `pipeline_version` | string | yes | Workflow version that ran. |
| `repository_url` | URL | no | Workflow repository. |
| `release_url` | URL | no | Release page of the workflow version. |
| `job_id_short` | string | one of the two | Platform job identifier in short form, for example `A123`. |
| `job_id_long` | UUID | one of the two | Platform job identifier in long form. |
| `job_metadata` | object | no | Job-wide details from the engine; see below. |
| `config_profile` | string | no | Execution profile the job ran with. |
| `publish_directory` | string | no | Directory the job published to, when generated from a directory. |
| `execution_timestamp` | date-time | no | When the job ran. |
| `files` | array of file records | yes | Every classified output of the job. An output the catalogue lists may be absent. |

At least one of `job_id_short` and `job_id_long` is present. No other
top-level keys are allowed.

### `job_metadata`

Details about the job as a whole. Engine identifiers are always qualified by
engine and never identify a platform run.

| Key | Type | Description |
| --- | --- | --- |
| `engine` | string | Engine that ran the job, for example `nextflow`. |
| `engine_execution_id` | string | The engine's own identifier for this execution. |
| `nextflow.session_id` | string | Nextflow session identifier. |
| `nextflow.run_name` | string | Nextflow run name, for example `happy_turing`. |
| `annotations` | object | Free-form annotations supplied by the platform. |

### File records

Each entry of `files` describes one output.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `path` | relative path | yes | Path relative to the job's publish directory. Never absolute, never contains `..`. |
| `output_type` | string | yes | Key of the matching entry in `x-output-catalog.output_types`. |
| `category` | string | yes | Category of that output type. |
| `scope` | `job`, `sample` or `run` | yes | Which unit owns the output. |
| `entity_type` | `file` or `directory` | yes | Whether `path` is a file or a directory. |
| `format` | string | yes | Format, for example `html`, `tsv` or `bam`. |
| `sample_id` | string | for `sample` and `run` | Sample that owns a sample record, or the parent sample of a run record. |
| `run_id` | string | for `run` | Platform run identifier of a run record. |
| `stage` | string | no | Processing stage from the catalogue. |
| `labels` | object of strings | no | Descriptive labels from the catalogue. |
| `library_id` | string | no | Descriptive library label. It is never a scope. |
| `read` | string | no | Read of a paired-end set, for example `R1`. |
| `aligner` | string | no | Aligner that produced the file. |
| `size_bytes` | integer | no | Size of a file in bytes. |
| `checksum` | string | no | Checksum of a file, when one was requested. |
| `checksum_algorithm` | string | no | Algorithm of `checksum`, for example `sha256`. |
| `storage_uri` | string | no | Location of the output in long-term storage, when the platform adds it. |

No other keys are allowed in a record. The workflow's schema also limits
each `output_type` to the categories, scopes, formats and path patterns in
its catalogue. Scope and identifiers are linked as follows:

| `scope` | `sample_id` | `run_id` |
| --- | --- | --- |
| `job` | must be absent | must be absent |
| `sample` | required | must be absent |
| `run` | required (the parent sample) | required |

## Example

A job of an RNA-seq workflow that published one job-wide report, one
per-sample file and one per-run file:

```json
{
  "analysis_output_schema_version": "1.0.0",
  "schema_id": "https://github.com/org/rnaquant/schema/analysis-output/v1.0.0",
  "pipeline_name": "rnaquant",
  "pipeline_version": "1.2.0",
  "repository_url": "https://github.com/org/rnaquant",
  "job_id_short": "A123",
  "job_id_long": "3f2c8a3e-6b1d-4c4e-9a52-1f0d2b7c9e10",
  "job_metadata": {
    "engine": "nextflow",
    "engine_execution_id": "7e1d9c2b-5a4f-4e3b-8c6d-0a1b2c3d4e5f",
    "nextflow": {
      "session_id": "7e1d9c2b-5a4f-4e3b-8c6d-0a1b2c3d4e5f",
      "run_name": "happy_turing"
    }
  },
  "config_profile": "slurm",
  "publish_directory": "/data/jobs/A123/results",
  "execution_timestamp": "2026-10-15T09:30:00Z",
  "files": [
    {
      "path": "multiqc/multiqc_report.html",
      "category": "quality_control",
      "output_type": "multiqc_report",
      "scope": "job",
      "entity_type": "file",
      "format": "html",
      "stage": "reporting",
      "size_bytes": 1843201,
      "checksum": "9f2b6c1d4e8a7f3b5c0d2e4f6a8b1c3d5e7f9a0b2c4d6e8f1a3b5c7d9e0f2a4b",
      "checksum_algorithm": "sha256"
    },
    {
      "path": "qc/S1/S1_L001.json",
      "category": "quality_control",
      "output_type": "read_qc",
      "scope": "run",
      "entity_type": "file",
      "format": "json",
      "run_id": "S1_L001",
      "sample_id": "S1",
      "size_bytes": 4096
    },
    {
      "path": "quant/S1/counts.tsv",
      "category": "quantification",
      "output_type": "gene_counts",
      "scope": "sample",
      "entity_type": "file",
      "format": "tsv",
      "sample_id": "S1",
      "size_bytes": 912384
    }
  ]
}
```

## How records are classified

`nf-splice analysis-output generate` matches each published path against the
`path_patterns` of every output type in the catalogue:

- `{sample}` in a pattern captures `sample_id`; `{run}` captures `run_id`.
- A run record needs its parent sample. It comes from `{sample}` in the
  pattern or from the sample sheet passed with `--sample-metadata`, a CSV
  with a sample column (`sample` or `sample_id`) and a `run_id` column.
- A path that matches no output type stops generation, unless
  `--allow-unclassified` is given, in which case it is left out.

## Consuming it

1. Find the bundle of the job's workflow version and load its
   `outputs.schema.json`.
2. Validate the document against that schema with any draft-07 validator.
3. Look up each record's `output_type` in `x-output-catalog.output_types` for
   its title, description and display grouping.
4. Attach job records to the job, sample records to the sample, and run
   records to the run and its parent sample.

Validate a document from the command line:

```bash
nf-splice analysis-output validate results/analysis_output.json
```

Documents written by nf-splice 0.1.0 used `scope: run` for job-wide outputs.
See the [migration guide](../CONTRACT_MIGRATION_0.3.0.md) before reading
them.
