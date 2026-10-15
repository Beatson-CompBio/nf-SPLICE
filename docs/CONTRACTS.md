# Building on SPLICE bundles

This page is for developers of platforms, ingestion services and other tools
that read SPLICE workflow bundles. It explains what a bundle contains, how
to read it and how its formats are versioned. Each file has a key-by-key
reference in [`schemas/`](schemas/README.md).

## What a bundle contains

A bundle is the `splice/` directory of a workflow repository:

```text
splice/
├── bundle.json               entry point: identity, contract revisions, file index
├── inputs.schema.json        input parameters (JSON Schema 2020-12)
├── outputs.schema.json       output catalogue + schema of each job's analysis_output.json
├── components.json           modules and container images
├── execution-profiles.json   execution profiles and the default
├── configs/<profile>.config  Nextflow configuration of each profile
├── ro-crate-metadata.json    RO-Crate provenance
├── outputs.yaml              human-readable copy of the output catalogue
├── README.md                 description for people
└── nf-splice.lock.json       hashes of every published file
```

The five JSON files at the top are the **contracts**: formats with a
published, versioned definition that consumers implement.

| File | Contract family | Revision | Reference |
| --- | --- | --- | --- |
| `bundle.json` | `https://schemas.splice-data.io/workflow-bundle/bundle` | `0.3.0` | [bundle](schemas/bundle/README.md) |
| `inputs.schema.json` | `https://schemas.splice-data.io/workflow-bundle/inputs` | `0.3.0` | [inputs](schemas/inputs/README.md) |
| `outputs.schema.json` | `https://schemas.splice-data.io/workflow-bundle/outputs` | `0.3.0` | [outputs](schemas/outputs/README.md) |
| `components.json` | `https://schemas.splice-data.io/workflow-bundle/components` | `0.3.0` | [components](schemas/components/README.md) |
| `execution-profiles.json` | `https://schemas.splice-data.io/workflow-bundle/execution-profiles` | `0.3.0` | [execution-profiles](schemas/execution-profiles/README.md) |

Two further formats matter to integrators:

- [`analysis_output.json`](schemas/analysis-output.md): the inventory each
  completed job produces, validated by the bundle's `outputs.schema.json`.
- [Companion files](schemas/companion-files.md): `outputs.yaml`, the
  RO-Crate, the profile configurations, the lock and the README.

There is no `outputs.json`. Output metadata lives only in
`outputs.schema.json`.

## Reading a bundle

1. Read `bundle.json`. Check `schema_id` and `schema_version`, and reject
   revisions you do not support.
2. For each entry in `schemas`, open the file at `path` and validate it
   against the family revision given by `version`.
3. Check that the workflow identity in every file (`pipeline`,
   `x-splice-pipeline` or `x-output-catalog.pipeline`) matches
   `bundle.json`.
4. Read output metadata from `outputs.schema.json` → `x-output-catalog`.
   Validate each job's `analysis_output.json` against the same file.
5. Resolve container images from `components.json`. Use `distribution` when
   present and verify its `sha256` after download; otherwise use
   `source_images`. If `require_downloadable_images` is `true` and an image
   cannot be downloaded, reject the bundle rather than fall back.
6. Run jobs with `default_execution_profile` unless an operator chooses
   another profile.

## Identity and versions

Each file states which contract it follows:

- Data documents (`bundle.json`, `components.json`,
  `execution-profiles.json`) carry `schema_id`, `schema_version` and
  `generated_by` at the top level.
- JSON Schema documents (`inputs.schema.json`, `outputs.schema.json`) keep
  their standard `$schema` and a workflow-specific `$id`, and carry the
  contract in `x-splice-contract`.

Several independent version numbers appear in a bundle. Do not mix them up:

| Version | Where | Changes when |
| --- | --- | --- |
| Contract revision | `schema_version`, `x-splice-contract.version` | A contract family's format changes. |
| Workflow version | `pipeline.version` | The workflow is released. |
| Output schema version | `x-output-catalog.analysis_output_schema_version` | The workflow's `analysis_output.json` changes. |
| Generator version | `generated_by.version` | A different nf-splice release writes the files. |
| Lock format | `nf-splice.lock.json` → `schema_version` | The lock format changes. |

## Getting the definitions

The family URIs are identifiers, not live web addresses. Validation is fully
offline:

- The definitions are packaged with nf-splice. Print one with
  `nf-splice schema show <family>`.
- The same files are in this repository at
  `docs/schemas/<family>/v<revision>/schema.json`, each with an
  `example.json`.

## Validating

With nf-splice:

```bash
nf-splice schema validate splice/components.json --json
nf-splice schema check --repository . --json
nf-splice validate --json
```

`schema validate` checks one file. `schema check` checks all five files of a
bundle. `validate` also checks cross-file identity, the output catalogue
copy, draft markers and the lock hashes.

Without nf-splice, the definitions are standard JSON Schema 2020-12. For
example, in Python:

```python
import json
from jsonschema import Draft202012Validator

schema = json.load(open("docs/schemas/components/v0.3.0/schema.json"))
document = json.load(open("splice/components.json"))
Draft202012Validator(schema).validate(document)
```

For `inputs.schema.json` and `outputs.schema.json`, also check the document
itself as a schema of its own dialect (2020-12 and draft-07 respectively).

## Compatibility

Revision `0.3.0` is the first supported revision of every family. Bundles
from earlier pre-release test versions of nf-splice are not supported
contracts; rebuild them with nf-splice 0.3.0.

A contract revision never changes once published. A new revision is needed
to remove or rename a key, narrow a type or an allowed set of values, change
a fixed value, close an object or make a key required. Adding an optional
key is compatible.

`nf-splice schema check --against OLD --family F` reports the differences
between two revisions.

Each nf-splice release states the revision it writes for every family, even
when a family did not change. `nf-splice schema list --json` prints this
registry.

| nf-splice | bundle | inputs | outputs | components | execution-profiles |
| --- | --- | --- | --- | --- | --- |
| 0.3.0 | 0.3.0 | 0.3.0 | 0.3.0 | 0.3.0 | 0.3.0 |

## Terms

The terms job, sample and run have precise meanings in these formats. See
the [glossary](GLOSSARY.md).
