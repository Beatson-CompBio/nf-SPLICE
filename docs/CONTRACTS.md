# Building on SPLICE bundles

This page is for developers of platforms, ingestion services and other tools
that read SPLICE workflow bundles. It explains what a bundle contains, how
to read it and how its formats are versioned. Each file has a key-by-key
reference in [`schemas/`](schemas/README.md).

You do not need nf-splice to build on bundles. If you work with a coding
agent, start with the [agent and skill files](#agent-and-skill-files-for-your-coding-agent)
below.

## Agent and skill files for your coding agent

The [bundle consumer kit](../bundle-consumer-kit/README.md) gives your coding
agent (Claude Code, Codex, Cursor, GitHub Copilot or any agent that reads
`AGENTS.md` or skill files) the structure of a bundle, the meaning of every
key and value, and how to validate against the versioned schemas. Copy it
into your own repository; it contains:

- [`AGENTS.md`](../bundle-consumer-kit/AGENTS.md): drop-in rules for any
  repository that consumes bundles;
- the formal definitions of every contract revision, offline, in
  [`schemas/`](../bundle-consumer-kit/schemas/);
- a complete validated example bundle and a real `analysis_output.json` of
  one of its jobs, in [`examples/`](../bundle-consumer-kit/examples/);
- one skill per kind of work:

| Skill | For developers who build | What it covers |
| --- | --- | --- |
| [`splice-bundle-contracts`](../bundle-consumer-kit/skills/splice-bundle-contracts/SKILL.md) | Anything that reads a bundle (always) | Files, families, the five version numbers, identity, validation, compatibility, terms |
| [`splice-bundle-ingestion`](../bundle-consumer-kit/skills/splice-bundle-ingestion/SKILL.md) | Ingestion into the SPLICE database or any store | What to store from each file and each job, and which component needs it; keys and relations; re-ingestion; integrity; personal data |
| [`splice-analysis-output`](../bundle-consumer-kit/skills/splice-analysis-output/SKILL.md) | Data explorers, results views, result ingestion | Every key of `analysis_output.json`, job/sample/run scopes, linking records to the catalogue, path classification (including from JavaScript) |
| [`splice-web-ui`](../bundle-consumer-kit/skills/splice-web-ui/SKILL.md) | Web interfaces | Which keys and labels to show on catalogue, detail, launch and results pages; access and visibility in forms; what the server must enforce |
| [`splice-job-launch`](../bundle-consumer-kit/skills/splice-job-launch/SKILL.md) | Job runners and launch APIs | Authorising and validating parameters, engine binding, profiles and operator settings, verified container images, recording the job |

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
   another profile. Each profile's `config_strategy` is `authored` (a native
   Nextflow config written for the bundle) or `adopted` (a repository config
   published unchanged); either way, the config at its `path` is what to use.

`ro-crate-metadata.json` is one Workflow RO-Crate describing the repository,
with the `splice/` directory and each published file as entities. In a
pipeline archive exported by nf-splice, every repository file sits at the
archive root, beside a `ro-crate-metadata.json` identical to the bundle's.

## Assay capabilities

`bundle.json` → `pipeline.assay_capabilities` lists every assay the workflow
can process, classified by the SPLICE modality vocabulary: the assay itself
(an `ASSAY_METHOD` or `ASSAY_TYPE`), the assay types and modality subtypes
above it, every top-level modality it belongs to, and every path between
them. A registered assay carries its platform `registered_code` (such as
`polya_rnaseq`). `assay_vocabulary` identifies the vocabulary snapshot.

- An assay is not a modality: group and filter by `modalities`.
- An assay can belong to several modalities; keep every path.
- Capabilities describe the workflow, not one job, and not what a particular
  deployment ingests. Resolve each `registered_code` to your deployment's
  registration and report the ones it does not support rather than dropping
  them.
- Bundles carry no platform accession identifiers.
- A bundle without assay capabilities is not ready for ingestion: nf-splice
  does not publish one. `nf-splice validate` reports readiness as separate
  dimensions: contracts, scientific classification, runtime parameters,
  deployment, provenance and publication.

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
| Assay vocabulary snapshot | `assay_vocabulary.snapshot` and `.digest` | The SPLICE modality vocabulary the assay capabilities were classified with changes. |

## Getting the definitions

The family URIs are identifiers, not live web addresses. Validation is fully
offline:

- The same files are in this repository at
  `docs/schemas/<family>/v<revision>/schema.json`, each with an
  `example.json`, and in the
  [bundle consumer kit](../bundle-consumer-kit/README.md) at
  `schemas/<family>/v<revision>/`.
- They are also packaged with nf-splice. Print one with
  `nf-splice schema show <family>`.

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
