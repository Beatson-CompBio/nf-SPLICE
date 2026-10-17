---
name: splice-analysis-output
description: Read, validate and interpret a SPLICE job's analysis_output.json, the inventory of everything one completed job published, together with the bundle's output catalogue. Explains job, sample and run scopes, every key, how records link to output types, and how path patterns classify files (including from JavaScript). Use for data explorers, results views, result ingestion and any code that handles job outputs.
---

# Reading `analysis_output.json`

## When to use

Use this skill when code receives an `analysis_output.json`, shows a job's
results, lets people explore outputs across jobs and samples, or ingests job
results. Read `splice-bundle-contracts` first for versions and validation.

## The idea

- The bundle's **output catalogue** (`outputs.schema.json` →
  `x-output-catalog`) lists every *kind* of output the workflow may publish,
  across all its routes: alternative tools, optional steps, conditional
  branches.
- One **job** takes one route. Its `analysis_output.json` lists the outputs
  it *actually* published, one record per file or directory, each pointing
  at its kind with `output_type`.
- So a job's document normally contains a subset of the catalogue. Kinds
  from routes the job did not take are simply absent. Never report that as
  missing data.

In `examples/`: the `multiroute` catalogue has `star_alignment`,
`hisat2_alignment` and `salmon_quantification`; the example job took the
STAR route without Salmon, so it has `star_alignment` and `star_log`
records but none for HISAT2 or Salmon.

## Validate, then link

1. Find the bundle of the job's workflow version (`pipeline_name`,
   `pipeline_version`; `schema_id` equals that bundle's
   `outputs.schema.json` `$id`).
2. Validate the document against that `outputs.schema.json` with a draft-07
   validator. The schema is specific to the workflow: it pins `schema_id`,
   `analysis_output_schema_version`, `pipeline_name` and `pipeline_version`,
   and lists the allowed `output_type` and `category` values. A valid
   document therefore cannot belong to another workflow version.
3. For each record, look up `x-output-catalog.output_types[]` where
   `key` = `output_type`, for its `title`, `description`, `category`,
   `stage` and `labels`; and `x-output-catalog.categories[category]` for the
   category's `title` and `description`.

## Document keys

| Key | Meaning |
| --- | --- |
| `analysis_output_schema_version` | Version of the workflow's job-inventory schema that validated it |
| `schema_id` | Identifier of that schema (the `$id` of `outputs.schema.json`) |
| `pipeline_name`, `pipeline_version` | The workflow version that ran |
| `repository_url`, `release_url` | Where the workflow and that release live (optional) |
| `job_id_short`, `job_id_long` | Your platform's job identifiers, short form (for example `A123`) and UUID; at least one is present |
| `job_metadata` | Job-wide engine details: `engine`, `engine_execution_id`, `nextflow.session_id`, `nextflow.run_name`, and free-form platform `annotations` |
| `config_profile` | Execution profile the job ran with (an `id` from `execution-profiles.json`) |
| `publish_directory` | The directory record paths are relative to |
| `execution_timestamp` | When the job ran (RFC 3339) |
| `files` | The output records |

Engine identifiers identify the engine's execution of the job. They are
never a sample or a run.

## Output records

| Key | Always | Meaning |
| --- | --- | --- |
| `path` | yes | Relative to `publish_directory`. Never absolute, never `..` |
| `output_type` | yes | The catalogue `key` of this kind of output |
| `category` | yes | The output type's category |
| `scope` | yes | `job`, `sample` or `run`: which unit owns the output |
| `entity_type` | yes | `file` or `directory` |
| `format` | yes | For example `html`, `tsv`, `bam`, `ome-tiff`; one of the output type's formats, never from a fixed list |
| `sample_id` | for `sample` and `run` | The sample that owns it, or the run's parent sample |
| `run_id` | for `run` | The platform run that owns it |
| `stage` | no | Processing stage from the catalogue |
| `labels` | no | Descriptive name-value labels from the catalogue |
| `library_id` | no | Descriptive library label; never a scope |
| `read` | no | Read of a pair, for example `R1` |
| `aligner` | no | Aligner that produced it |
| `size_bytes` | no | Size of a file |
| `checksum`, `checksum_algorithm` | no | For example a `sha256` of the file |
| `storage_uri` | no | Long-term storage location, when your platform adds it |

No other keys are allowed in a record.

### Scopes and identifiers

| `scope` | `sample_id` | `run_id` | Attach the record to |
| --- | --- | --- | --- |
| `job` | absent | absent | The job |
| `sample` | required | absent | The sample (within this job) |
| `run` | required (parent) | required | The run, and through it the sample |

A **sample** is one biological sample; a **run** is one platform
file-level unit of a sample, such as one sequencing run. Several runs can
share a sample. Read mates (`R1`, `R2`) are not runs.

## How paths were classified

nf-splice classifies each published path by matching it, relative to the
publish directory, against every output type's `path_patterns`. You need
this when you classify paths yourself (for example, files arriving before
the document exists) or show the patterns.

- Patterns are **Python `re`** regular expressions anchored with `^` and
  `$`.
- Named groups capture fields: `(?P<sample_id>...)`, `(?P<run_id>...)`,
  and optionally `library_id`, `aligner`, `stage`, `read`.
- Patterns may contain placeholders, expanded before matching:
  `{sample}` → `(?P<sample_id>[^/]+)`, `{run}` → `(?P<run_id>[^/]+)`,
  `{library}` → `(?P<library_id>[^/]+)`, `{aligner}` →
  `(?P<aligner>[^/]+)`, `{stage}` → `(?P<stage>[^/]+)`, `{read}` →
  `(?P<read>[^/]+)`, `{any}` → `[^/]+`, `{anypath}` → `.+`.
- Scope: `run` when a `run_id` was captured and the type allows `run`;
  otherwise `sample` when a `sample_id` was captured and allowed; otherwise
  `job`.

In JavaScript or TypeScript, expand placeholders, replace each `(?P<` with
`(?<`, and compile **without** the `u` or `v` flag (Python escapes
characters such as `-` as `\-`, which those flags reject):

```javascript
const PLACEHOLDERS = {
  "{sample}": "(?P<sample_id>[^/]+)", "{run}": "(?P<run_id>[^/]+)",
  "{library}": "(?P<library_id>[^/]+)", "{aligner}": "(?P<aligner>[^/]+)",
  "{stage}": "(?P<stage>[^/]+)", "{read}": "(?P<read>[^/]+)",
  "{any}": "[^/]+", "{anypath}": ".+",
};
function compilePattern(pattern) {
  let source = pattern;
  for (const [token, regex] of Object.entries(PLACEHOLDERS)) {
    source = source.split(token).join(regex);
  }
  return new RegExp(source.replaceAll("(?P<", "(?<"));
}
```

Patterns come from a reviewed bundle, but treat them as data: compile them
on the server or with a time limit if users can supply paths.

## Presenting and exploring results

- Group records by category (category `title`, falling back to the key),
  then by output type (`title`, `description`), then by scope: the job's own
  outputs, then per sample, then per run within each sample.
- Use `stage` and `labels` for filters and secondary grouping; they are
  free text chosen by the workflow's reviewers, so do not hard-code values.
- Use `format` and `entity_type` to choose a viewer or download action; a
  `directory` is a folder, not a file.
- Across jobs, compare outputs by workflow `pipeline.id` + output type `key`,
  and by `sample_id` / `run_id` from your platform. Output type keys are
  stable within a workflow version.
- Show only what exists. An output type with no records in a job is not an
  error.

## Example

`examples/analysis_output.json` is a real job of `examples/bundle/`: job
`A123`, one job-scoped MultiQC report and FastQC and STAR outputs for samples
`S1` and `S2`, with sizes and SHA-256 checksums.
