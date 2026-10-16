---
name: splice-bundle-contracts
description: Structure, versions, identity and validation of SPLICE workflow bundles (bundle.json, inputs.schema.json, outputs.schema.json, components.json, execution-profiles.json) and job analysis_output.json files. Use whenever code reads, validates or relies on any of these files; the other SPLICE skills build on it.
---

# SPLICE bundle contracts

## When to use

Use this skill before writing any code that opens a SPLICE bundle or an
`analysis_output.json`, and whenever you need to know what a file, key or
version number means. It does not require nf-splice.

## The files

A bundle is one folder (`splice/` in the workflow's repository) for one
released version of one workflow.

| File | Contract family | Holds |
| --- | --- | --- |
| `bundle.json` | `bundle` | Entry point: identity, credits, contract revisions, file index, default profile |
| `inputs.schema.json` | `inputs` | Input parameters as JSON Schema 2020-12, with SPLICE access, UI, data and engine keys |
| `outputs.schema.json` | `outputs` | The output catalogue (`x-output-catalog`) and the JSON Schema (draft-07) that validates each job's `analysis_output.json` |
| `components.json` | `components` | Workflow modules and container images |
| `execution-profiles.json` | `execution-profiles` | Reviewed ways to run the workflow, each with a configuration file |

Companion files are not contracts: `configs/<profile>.config` (Nextflow
configuration, used through `execution-profiles.json`),
`ro-crate-metadata.json` (RO-Crate 1.1 provenance), `outputs.yaml` (a human
copy of the catalogue; never parse it), `nf-splice.lock.json` (SHA-256 of
every published file) and `README.md`.

Per job, not per bundle: `analysis_output.json`, the inventory of what one
completed job published. See the `splice-analysis-output` skill.

Family URIs are `https://schemas.splice-data.io/workflow-bundle/<family>`.
They identify a format; they are not web addresses.

## Reading a bundle

1. Open `bundle.json`. Check `bundle_format` is `splice-pipeline-bundle`,
   `schema_id` is the bundle family URI and `schema_version` is a revision
   you support.
2. Validate `bundle.json` against `schemas/bundle/v<revision>/schema.json`.
3. For each entry of `schemas` (keyed by family URI), open the file at
   `path`, and validate it against `schemas/<family>/v<version>/schema.json`.
   Use `files` (`inputs_schema`, `outputs_schema`, `components`,
   `execution_profiles`, `ro_crate`, `outputs_catalogue`) to find files;
   never hard-code names.
4. Check that every file names the same workflow as `bundle.json`
   `pipeline` (`id`, `name`, `version`, `engine`): it is repeated as
   `pipeline` in `components.json` and `execution-profiles.json`, as
   `x-splice-pipeline` in `inputs.schema.json` and as
   `x-output-catalog.pipeline` in `outputs.schema.json`.
5. Optionally check integrity: for every path in
   `nf-splice.lock.json` → `managed_files`, recompute the SHA-256 and compare.
6. Reject the whole bundle when any step fails. A partially valid bundle is
   not usable.

## How each file declares its revision

- Data documents (`bundle.json`, `components.json`,
  `execution-profiles.json`) carry `schema_id`, `schema_version` and
  `generated_by` at the top level.
- The JSON Schema documents (`inputs.schema.json`, `outputs.schema.json`)
  keep their standard `$schema` and a workflow-specific `$id`, and declare
  the contract in `x-splice-contract` (`id`, `version`, `generated_by`).
  Their `$id` identifies this workflow's schema, not the contract family.

## Version numbers: keep them apart

| Version | Where | Changes when | Use it to |
| --- | --- | --- | --- |
| Contract revision | `schema_version`; `x-splice-contract.version`; the `version` of each `schemas` entry | A format changes | Choose the validator; reject unsupported revisions |
| Workflow version | `pipeline.version` | The workflow is released | Identify what ran; show to users |
| Output schema version | `x-output-catalog.analysis_output_schema_version` | The workflow's job inventory changes | Match `analysis_output.json` to its schema |
| Generator version | `generated_by.version` | Another nf-splice release wrote the file | Diagnostics only |
| Lock format | `nf-splice.lock.json` → `schema_version` | The lock format changes | Read the lock |

## Validation

The definitions are standard JSON Schema 2020-12 documents. Validate fully
offline from `schemas/`.

Python (`jsonschema`):

```python
import json
from jsonschema import Draft202012Validator

schema = json.load(open("schemas/components/v0.3.0/schema.json"))
document = json.load(open("splice/components.json"))
Draft202012Validator(schema).validate(document)
```

JavaScript or TypeScript (Ajv): use the 2020-12 build, `ajv/dist/2020`, with
`ajv-formats` for `uri`, `email` and `date-time`.

Two extra checks:

- `inputs.schema.json` is itself a schema: compile it with a 2020-12
  validator; you will use it to validate submitted parameters.
- `outputs.schema.json` is itself a draft-07 schema: compile it with a
  draft-07 validator; you will use it to validate each job's
  `analysis_output.json`. In Ajv use the default (draft-07) build for it.

Published files never contain `x-splice-draft`; the definitions reject it.

## Compatibility

- A contract revision never changes once published. Removing or renaming a
  key, narrowing a type or an allowed set, changing a fixed value, closing
  an object or making a key required needs a new revision. Adding an
  optional key is compatible.
- Objects are closed ("no other keys are allowed") wherever the definition
  says `additionalProperties: false`; parameter definitions in
  `inputs.schema.json` are open JSON Schema.
- Support explicit revisions. Keep each revision's validator; dispatch on the
  declared revision.
- Revision `0.3.0` is the first supported revision of every family.

## Terms

| Term | Meaning | Not |
| --- | --- | --- |
| Workflow | The pipeline a bundle describes, identified by `pipeline.id` | — |
| Bundle | The published `splice/` folder for one workflow version | Drafts or source code |
| Job | One submitted execution of a workflow version | A sample or a run |
| Sample | One biological or experimental sample | One of its runs |
| Run | A platform file-level or acquisition-level unit of one sample, with a platform `run_id` and a parent `sample_id` | A Nextflow execution |
| Output type | One entry of `x-output-catalog.output_types`, identified by `key` | A file |
| Output record | One entry of `files` in an `analysis_output.json` | — |

Engine identifiers (`job_metadata.engine_execution_id`,
`job_metadata.nextflow.session_id`, `job_metadata.nextflow.run_name`)
describe the engine's execution of a job. They are never a platform run.

## Example

`examples/bundle/` is a complete valid bundle of `multiroute` 1.0.0, a small
RNA-seq workflow with alternative aligners (STAR or HISAT2) and optional
Salmon quantification. `examples/analysis_output.json` is one job of it that
took the STAR route. Use them as test fixtures.
