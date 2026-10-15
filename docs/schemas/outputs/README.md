# `outputs.schema.json`

Workflow job output contract.

| | |
| --- | --- |
| Contract family | `https://schemas.splice-data.io/workflow-bundle/outputs` |
| Revision | `0.3.0` |
| Formal schema | [`v0.3.0/schema.json`](v0.3.0/schema.json) |
| Example | [`v0.3.0/example.json`](v0.3.0/example.json) |

`outputs.schema.json` has two jobs:

1. It is the JSON Schema (draft-07) that validates the
   `analysis_output.json` each completed job produces. Its own
   `properties` and `definitions` are written for this workflow; see
   [`analysis_output.json`](../analysis-output.md).
2. Its `x-output-catalog` key holds the reviewed catalogue of every output
   the workflow can produce: what each output is, at which granularity
   it is owned (job, sample or run) and how to recognise it by path.

- **Written by:** `nf-splice build all`, from the reviewed
  `splice/drafts/outputs.draft.yaml`. `outputs.yaml` is a human-readable
  copy of the same catalogue.
- **Read by:** platforms that classify, store and display job outputs.
  Read the catalogue from this file only.

The keys below are the fixed part of the document. For the
workflow-specific runtime schema, read
[`analysis_output.json`](../analysis-output.md).

## Fields

A key marked required must be present whenever the object that
contains it is present. A section whose object accepts no other
keys says so.

### Top-level keys

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `$schema` | always `"https://json-schema.org/draft-07/schema#"` | yes | Standard JSON Schema dialect of this document. |
| `$id` | non-empty string | yes | Identifier of this workflow's schema. It is specific to the workflow and is not the contract family URI. |
| `type` | always `"object"` | yes | Type of the instance this schema validates. Always `object`. |
| `x-splice-contract` | object | yes | Contract family and revision of this JSON Schema document, kept separate from the standard `$schema` and `$id` keys. |
| `x-output-catalog` | object | yes | Output catalogue of the workflow. |
| `x-splice-draft` | must not appear | no | Draft marker used while authoring. A published file never contains it; validation rejects files that do. |

### `x-splice-contract`

Contract family and revision of this JSON Schema document, kept separate from the standard `$schema` and `$id` keys. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | always `"https://schemas.splice-data.io/workflow-bundle/outputs"` | yes | Contract family URI. |
| `version` | always `"0.3.0"` | yes | Contract revision. |
| `generated_by` | object | yes | Tool that wrote the file. |

### `x-splice-contract.generated_by`

Tool that wrote the file. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | non-empty string | yes | Generator name, for example `nf-splice`. |
| `version` | non-empty string | yes | Generator release that wrote the file. |

### `x-output-catalog`

The reviewed output catalogue. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `catalog_version` | always `"0.3.0"` | yes | Revision of the catalogue format. |
| `schema_semantics` | non-empty string | no | Short statement of how the catalogue is meant to be read. |
| `analysis_output_schema_version` | version `X.Y.Z` | yes | Version of this workflow's `analysis_output.json` schema. Reviewers raise it when the runtime document changes. |
| `pipeline` | object | yes | Workflow identity. |
| `scopes` | object | yes | Granularity definitions. |
| `categories` | object keyed by name | yes | Output categories. |
| `output_types` | array of objects (at least 1) | yes | Kinds of output. |

### `x-output-catalog.pipeline`

Workflow identity. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | lower-case letters, digits and `-` | yes | Workflow identifier. |
| `name` | non-empty string | yes | Workflow name. |
| `version` | non-empty string | yes | Workflow version. |
| `engine` | non-empty string | yes | Workflow engine. |
| `repository_url` | URL | no | Workflow repository. |

### `x-output-catalog.scopes`

Definitions of the three granularities that can own an output. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `job` | non-empty string | yes | One complete execution of the workflow. Job outputs belong to the job as a whole. |
| `sample` | non-empty string | yes | One biological sample. Sample outputs carry a `sample_id`. |
| `run` | non-empty string | yes | One file-level platform run of a sample, such as one sequencing run. Run outputs carry a `run_id` and the parent `sample_id`. |

### `x-output-catalog.categories.*` (each entry)

Categories used by `output_types`, keyed by category name. Names are free text. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `title` | non-empty string | no | Display title of the category. |
| `description` | non-empty string | no | Description of the category. |

### `x-output-catalog.output_types[]` (each item)

Kinds of output. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `key` | lower-case letter, then letters, digits or `_` | yes | Stable identifier. Records in `analysis_output.json` refer to it as `output_type`. |
| `title` | non-empty string | yes | Display title. |
| `description` | non-empty string | yes | What the output contains, written for scientists. |
| `category` | non-empty string | yes | Category name, one of the keys of `categories`. |
| `stage` | non-empty string | no | Free-text processing stage, such as `alignment`. |
| `scope` | array of `job`, `sample`, `run` (at least 1, no duplicates) | yes | Granularities that can own this output: `job`, `sample` and/or `run`. |
| `entity_type` | array of `file`, `directory` (at least 1, no duplicates) | yes | Whether the output is a `file` or a `directory`. |
| `format` | array of non-empty strings (at least 1, no duplicates) | yes | Permitted formats, for example `html` or `bam`. |
| `path_patterns` | array of strings: regular expression anchored with `^` and `$` (at least 1, no duplicates) | yes | Regular expressions anchored with `^` and `$` that match the output's path relative to the job's publish directory. `{sample}` captures the `sample_id` and `{run}` captures the `run_id`. |
| `labels` | object keyed by name | no | Reviewed descriptive labels, as name-value pairs. |
| `optional` | boolean | no | Reserved. Any output may be absent from a particular job. |

## Example

<details>
<summary>Complete <code>outputs.schema.json</code></summary>

```json
{
  "$schema": "https://json-schema.org/draft-07/schema#",
  "$id": "https://github.com/org/example-pipeline/schema/analysis-output/v1.0.0",
  "title": "SPLICE example-pipeline analysis output",
  "type": "object",
  "required": [
    "files"
  ],
  "properties": {
    "files": {
      "type": "array",
      "items": {
        "$ref": "#/definitions/file_record"
      }
    }
  },
  "definitions": {
    "file_record": {
      "type": "object",
      "required": [
        "path",
        "scope"
      ],
      "properties": {
        "path": {
          "type": "string"
        },
        "scope": {
          "enum": [
            "job",
            "sample",
            "run"
          ]
        }
      }
    }
  },
  "x-splice-contract": {
    "id": "https://schemas.splice-data.io/workflow-bundle/outputs",
    "version": "0.3.0",
    "generated_by": {
      "name": "nf-splice",
      "version": "0.3.0"
    }
  },
  "x-output-catalog": {
    "catalog_version": "0.3.0",
    "schema_semantics": "Every reviewed output type; each completed job may contain any produced subset.",
    "analysis_output_schema_version": "1.0.0",
    "pipeline": {
      "id": "example-pipeline",
      "name": "example-pipeline",
      "version": "1.2.3",
      "engine": "nextflow"
    },
    "scopes": {
      "job": "Produced once for the whole workflow job.",
      "sample": "Produced per biological sample.",
      "run": "Produced per platform file-level run belonging to a sample."
    },
    "categories": {
      "job_report": {
        "title": "Job reports"
      }
    },
    "output_types": [
      {
        "key": "multiqc_report",
        "title": "MultiQC report",
        "description": "Job-wide MultiQC report.",
        "category": "job_report",
        "scope": [
          "job"
        ],
        "entity_type": [
          "file"
        ],
        "format": [
          "html"
        ],
        "path_patterns": [
          "^multiqc/multiqc_report\\.html$"
        ]
      }
    ]
  }
}
```

</details>

---

Generated by `scripts/generate_schema_docs.py` from the packaged
definition and `docs/schemas/fields.yaml`. Edit those, not this page.
