---
name: splice-bundle-ingestion
description: Ingest SPLICE workflow bundles and job analysis_output.json files into a database (the SPLICE database or any store) so that web interfaces, data explorers and job launchers have everything they need. Covers what to store, keys and relations, re-ingestion, integrity and personal data. Use when designing schemas, migrations or ingestion code.
---

# Ingesting SPLICE bundles and job results

## When to use

Use this skill when you write code or a database design that stores bundles
or `analysis_output.json` documents. Read `splice-bundle-contracts` first:
validate before you store anything.

The guidance is independent of your storage technology. It says what each
downstream component needs; you choose tables, documents or columns.

## Principles

1. **Store the validated documents verbatim** (each file's exact bytes or
   parsed JSON), keyed by workflow version and file. Extract columns for
   querying, but keep the originals: they are what you re-validate against,
   what a launcher passes to the engine and what you show when a contract
   gains a key you do not extract yet.
2. **One workflow version is the unit of a bundle**: key it by
   `pipeline.id` + `pipeline.version`.
3. **Record the contract revision of every stored file**, from
   `bundle.json` → `schemas[*].version`. Code paths dispatch on it.
4. **Never store a bundle that failed validation**, and never store part of
   one. Ingest in one transaction.
5. **Jobs point at the exact bundle they ran with**, not at "the latest".

## What to store from a bundle

| Store | From | Needed by |
| --- | --- | --- |
| Workflow: `pipeline.id`, `name`, `engine`, `repository_url` | `bundle.json` → `pipeline` | Everything; `id` is the workflow's primary key |
| Workflow version: `pipeline.version`, `release_url`, `released_at`, plus the ingestion time | `bundle.json` → `pipeline` | Catalogue, launcher, results |
| Display metadata: `title`, `description`, `long_description`, `keywords`, `pipeline_type`, `documentation_url`, `project_url`, `support_url`, `readme` | `bundle.json` → `pipeline` | Web catalogue and search |
| Assay capabilities (below) and the vocabulary snapshot: `assay_vocabulary.snapshot`, `assay_vocabulary.digest` | `bundle.json` → `pipeline.assay_capabilities`, `assay_vocabulary` | Pipeline finder, catalogue filters, routing data to pipelines |
| Credits: `authors[]` (in order), `funders[]`, `citation`, `licence`, `licence_url` | `bundle.json` → `pipeline` | Web detail pages, citation export |
| Engine requirements: `engine_version_min`, `engine_versions_tested` | `bundle.json` → `pipeline` | Launcher compatibility checks |
| Maintainers: `maintainers[]` | `bundle.json` | Web contact section. **Personal data**: store under your privacy policy |
| Contract revision per file | `bundle.json` → `schemas` | Every reader |
| Default profile id | `bundle.json` → `default_execution_profile` | Launcher, launch form |
| `inputs.schema.json`, whole | file | Launch form and server-side validation of submissions |
| One row per parameter (below) | `inputs.schema.json` | Launch form, access enforcement, search |
| `outputs.schema.json`, whole | file | Validating each job's `analysis_output.json` |
| Output catalogue: `analysis_output_schema_version`, the schema's `$id`, `categories`, `output_types[]` (below) | `outputs.schema.json` → `x-output-catalog`, `$id` | Results views, data explorer, linking job records |
| Profiles: every key of `profiles[]`, the content of each profile's `config` file, `site_parameters[]` | `execution-profiles.json`, `configs/` | Launcher, launch form |
| Containers: `id`, `type`, `uri`, `source_images`, `distribution`, `resolution.status`; and `require_downloadable_images` | `components.json` | Launcher (image pre-fetch), software inventory |
| Components: `id`, `name`, `namespace`, `path`, `tool.name`, `tool.version`, `container_id`, `conda_packages`, `evidence` | `components.json` | Software inventory, "tools used" pages, citations. `path` is a module directory, or `<file>::<PROCESS>` (namespace `inline`) for a process defined in a workflow file; store it as an opaque string |
| RO-Crate | `ro-crate-metadata.json` | Provenance export (store as a document) |
| Integrity: `managed_files` hashes, `repository.url`, `repository.revision`, `contracts` | `nf-splice.lock.json` | Change detection, provenance ("built from commit …") |

### Parameters

Flatten `inputs.schema.json` into one record per parameter. A parameter is a
property under the root `properties` or under `$defs.<group>.properties`;
each name appears once, and a submitted parameter object is always flat.

| Field | From the parameter definition |
| --- | --- |
| `name` | its property name |
| `group`, group title and description | the `$defs` key, and that group's `title` and `description` |
| `required` | whether the name is in its group's (or the root's) `required` |
| JSON Schema facts | `type`, `default`, `enum`, `minimum`, `maximum`, `pattern`, `format`, `description` |
| nf-schema facts | `help_text`, `fa_icon`, `mimetype`, `schema` (when present) |
| Access | `x-splice-access.editable_by` (required on every parameter) |
| Presentation | `x-splice-ui.visibility`, `x-splice-ui.order`, `x-splice-ui.help_text`, `x-splice-ui.icon` |
| Data reference | `x-splice-data.kind`, `x-splice-data.samplesheet` |
| Engine binding | `x-splice-source.engine`, `x-splice-source.binding`, `x-splice-source.origin` |

Keep the whole definition as well: validation needs it, and parameters may
use any JSON Schema keyword.

### Assay capabilities

One record per `pipeline.assay_capabilities[]` entry, keyed by workflow
version and `registered_code` (registered assays) or `assay.entity_id`
(`vocabulary_assay` entries, which have no registration).

| Field | Notes |
| --- | --- |
| `kind` | `registered_assay` or `vocabulary_assay` |
| `registered_code` | The platform registration's `modality_name`; resolve it to your deployment's registration and check its entity id equals `assay.entity_id` |
| `assay.entity_id`, `assay.entity_type`, `assay.label` | The assay: an `ASSAY_METHOD` or an `ASSAY_TYPE`, never a modality |
| `assay_types[]`, `modality_subtypes[]`, `modalities[]` | Entities above the assay, each `entity_id` and `label` |
| `paths[]` | Every path from the assay to a modality, as entity ids |

- Store one pipeline–assay link per capability: a pipeline usually has
  several. A single "modality" column per pipeline cannot hold them.
- A capability your deployment does not register, or does not ingest yet,
  is stored and reported as unsupported here; never drop it.
- Store `assay_vocabulary` with the bundle and compare its `digest` with
  your vocabulary before trusting the entity ids.

### Output types

One record per `x-output-catalog.output_types[]` entry, keyed by workflow
version + `key`:

| Field | Notes |
| --- | --- |
| `key` | Stable identifier; job records refer to it as `output_type` |
| `title`, `description` | Display text, written for scientists |
| `category` | Key into `x-output-catalog.categories`; store categories with their optional `title` and `description` |
| `stage` | Optional free-text processing stage |
| `scope[]` | Which of `job`, `sample`, `run` may own it |
| `entity_type[]`, `format[]` | `file` and/or `directory`; permitted formats, free lower-case names chosen for the pipeline (`bam`, `ome-tiff`, `zarr`): never validate them against a fixed list |
| `path_patterns[]` | Python `re` patterns; see `splice-analysis-output` |
| `labels` | Optional name-value pairs |

## What to store from a job

For each completed job, validate its `analysis_output.json` against the
stored `outputs.schema.json` of the workflow version it ran, then store:

| Store | From | Notes |
| --- | --- | --- |
| The document, whole | file | Re-validation and audit |
| Job: `job_id_short` and/or `job_id_long` | top level | Your platform's job identifiers; at least one is present |
| Link to the workflow version | `pipeline_name`, `pipeline_version`, `schema_id` | Resolve the bundle by version; `schema_id` equals the `$id` of that bundle's `outputs.schema.json` |
| `analysis_output_schema_version` | top level | Equals the catalogue's `analysis_output_schema_version`; the schema enforces it, with `schema_id`, `pipeline_name` and `pipeline_version`, so a valid document cannot belong to another workflow version |
| Execution: `config_profile`, `execution_timestamp`, `publish_directory` | top level | Profile used and when; the directory record paths are relative to |
| Engine metadata: `job_metadata.*` | top level | Engine identifiers and platform `annotations`; never a platform run |
| Samples | distinct `sample_id` values | Platform sample identifiers |
| Runs | distinct `run_id` values, each with its `sample_id` | A run always belongs to one sample |
| One output record per `files[]` entry | `files` | Below |

Output record fields: `path`, `output_type` (link to the output type by
workflow version + key), `category`, `scope`, `entity_type`, `format`,
`sample_id`, `run_id`, `stage`, `labels`, `library_id`, `read`, `aligner`,
`size_bytes`, `checksum`, `checksum_algorithm`, `storage_uri`. Link a
`sample` record to its sample, a `run` record to its run and through it to
the sample, and a `job` record to the job only.

Do not create records for output types the job did not produce: the
catalogue says what *may* exist; the document says what *does*.

## Re-ingestion and changes

- **Same workflow version, identical bundle** (same lock `managed_files`
  hashes): nothing to do; ingestion is idempotent.
- **Same workflow version, different bundle**: the integration was rebuilt
  (a newer nf-splice, a corrected review). Do not overwrite silently: jobs
  already ran with the old one. Store it as a new bundle revision of that
  workflow version (keep both, mark the newer current), or reject it, by
  your policy. Compare `managed_files` hashes to see which files changed.
- **New workflow version**: a new workflow version record. Output type keys
  may carry over between versions but are only guaranteed within one
  version's catalogue; compare titles and descriptions before treating them
  as the same series.
- **New contract revision**: route to the validator and extractor for that
  revision; reject when you have none yet.

## Integrity and safety

- Verify `nf-splice.lock.json` → `managed_files` SHA-256 values on ingest
  when you receive bundles over a network or from users.
- Treat every string as untrusted text. Output `path` values are relative
  and never contain `..`; when you resolve them against storage, still check
  the result stays inside the job's folder.
- `maintainers[].name` and `maintainers[].email` are personal data, published
  only with the maintainers' consent. Authors are public credits.
- Profiles never contain credentials; `site_parameters` name the settings an
  operator must supply. Store operator values separately from the bundle.

## Checklist

- [ ] Every file validated against its declared revision before storage.
- [ ] Identity consistent across all files; keyed by `pipeline.id` + `pipeline.version`.
- [ ] Original documents kept alongside extracted fields.
- [ ] Parameters flattened with access, UI, data and binding fields.
- [ ] Output catalogue stored with categories; jobs link records by `output_type`.
- [ ] Jobs link to the exact bundle they ran with.
- [ ] Samples and runs stored with the run's parent sample.
- [ ] Re-ingestion is idempotent and never silently overwrites.
- [ ] Personal data handled by policy.
