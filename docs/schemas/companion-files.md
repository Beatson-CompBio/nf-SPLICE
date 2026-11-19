# Companion files

Besides the five contract files, a published bundle contains files that
support people and tools but are not contracts a consumer must implement.

| File | For | Read by programs? |
| --- | --- | --- |
| `README.md` | People browsing the bundle | No |
| `outputs.yaml` | People reviewing the output catalogue | No: read `outputs.schema.json` |
| `ro-crate-metadata.json` | Provenance and FAIR metadata | Optional, with RO-Crate tools |
| `configs/<profile>.config` | The Nextflow engine | Yes, through `execution-profiles.json` |
| `nf-splice.lock.json` | Integrity and change tracking | Optional |

## `outputs.yaml`

A human-readable copy of the output catalogue in `outputs.schema.json`. It
is regenerated from the same reviewed draft, so the two never disagree, and
`nf-splice validate` checks that they match. Programs should read
`x-output-catalog` from [`outputs.schema.json`](outputs/README.md) instead.

| Key | Description |
| --- | --- |
| `catalogue_format_version` | Revision of this file's format, `0.3.0`. |
| `schema_version` | Version of the workflow's `analysis_output.json` schema. |
| `pipeline` | Workflow identity: `id`, `name`, `version`, `engine`, `repository_url` and, when known, `release_url`. |
| `schema_id` | Identifier of the workflow's `analysis_output.json` schema. |
| `categories[]` | Categories in use: `key`, with an optional `title` and `description`. |
| `outputs[]` | Output types: `key`, `title`, `description`, `category`, `scope`, `entity_type`, `format`, `path_patterns`, and optional `stage` and `labels`. |

## `ro-crate-metadata.json`

The workflow's RO-Crate (RO-Crate 1.1, following Workflow RO-Crate
conventions). Depending on what was reviewed, it is one of the following:

- the developer's own root RO-Crate, unchanged (`include`);
- a reviewed copy of it with corrected identity and credited authors
  (`enriched`);
- a minimal crate generated from the reviewed identity (`generated`).

The developer's file in the workflow repository is never modified. Enriched
and generated crates record nf-splice as the creating software. See the
[provenance guide](../guide/provenance.md).

## `configs/<profile>.config`

One Nextflow configuration file per execution profile, named after the
profile's `id`. An adopted configuration is a byte-identical copy of a file
from the workflow repository. A generated one contains two marked sections:

```text
// ***** User Pipeline Input Params *****
// ***** SPLICE Pipeline Input Params *****
```

Configurations never contain accounts, queues, private paths or
credentials. Settings the operator must provide are listed in the profile's
`site_parameters`.

## `nf-splice.lock.json`

Records what was published and from what, so a later build can detect
changes and hand edits.

| Key | Description |
| --- | --- |
| `schema_version` | Lock format, `2.0`. |
| `generator.name`, `generator.version` | Tool and release that published the bundle. |
| `repository.url`, `repository.revision` | Workflow repository and the Git commit it was at, or `null` when unknown. |
| `contracts` | Contract revision of each of the five families, keyed by family URI. |
| `sources` | Repository files the bundle was built from, keyed by path: `sha256` and `role` (`input-schema-evidence`, `adopted-config` or `ro-crate-source:<strategy>`). |
| `provenance.ro_crate_strategy` | How the authored RO-Crate graph began: `adopted`, `generated`, `nf-core` or `authored`. |
| `provenance.ro_crate_source_sha256` | Hash of the root RO-Crate the published one was based on, or `null`. |
| `provenance.ro_crate_sha256` | Hash of the published RO-Crate. |
| `managed_files` | Every published file except the lock itself, keyed by path, with its `sha256`. |
| `distributions` | Present when an image file is published: nf-splice's record of each verification, keyed by container ID, with the verified `sha256`, `download_uri` and `size_bytes`, a `source_images_sha256` digest of the container's sources, and `verification`: `fresh` (nf-splice downloaded and checked the file for this bundle) or `historical` (reused from an earlier bundle's verification without downloading it again). It records past verifications; it never shows a file is reachable now. |

To check a bundle's integrity, recompute the SHA-256 of each file in
`managed_files` and compare. `nf-splice validate` does this and also
reports files that were edited by hand after publication.

## `README.md`

A short description of the bundle: the workflow, the contract revision of
each file and the purpose of each file. It is regenerated on every build.
