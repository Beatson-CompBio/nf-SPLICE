---
name: splice-job-launch
description: Turn a job submission into a running Nextflow job from a SPLICE bundle - validate and authorise parameters, bind them to the engine, choose the execution profile and its configuration, supply operator settings, pre-fetch and verify container images, and record what is needed afterwards for analysis_output.json. Use for platform job runners, schedulers and launch APIs.
---

# Launching jobs from a SPLICE bundle

## When to use

Use this skill when you build the service that receives a job submission
(from a web form, an API or an agent) and starts the workflow on compute.
Read `splice-bundle-contracts` first.

## 1. Pin the bundle

Resolve the exact workflow version (`pipeline.id` + `pipeline.version`) and
the stored bundle for it. Record that link on the job: everything after
this step, including results, refers to this bundle.

Check engine compatibility: `pipeline.engine` is `nextflow`;
`pipeline.engine_version_min` (when present) is the minimum Nextflow version
the workflow declares.

## 2. Authorise and validate parameters

The submission is one flat object: parameter name → value.

1. **Authorise each supplied parameter** by
   `x-splice-access.editable_by` in `inputs.schema.json`:
   - a person's submission may set only parameters whose list contains
     `user`;
   - your platform sets parameters whose list contains `platform` (for
     example the output directory);
   - an AI agent acting for a person may set only parameters whose list
     contains `agent`;
   - an empty list means fixed: nobody sets it; the `default` applies.
   Reject the submission when any value comes from someone not allowed to
   set it. Do not silently drop it.
2. **Add platform values** for `platform` parameters (paths, output
   locations, platform job identifiers).
3. **Validate the complete object** against `inputs.schema.json` with a
   JSON Schema 2020-12 validator. This checks types, required parameters
   (each group's `required`), enums, ranges and patterns.
4. **Check data references**: for `x-splice-data.kind` `file`, `directory`,
   `path` or `uri`, check the value is something this job may read. For
   `samplesheet: true`, check the sample sheet before starting; its own
   schema, when the parameter's nf-schema `schema` key names one, is a file
   in the workflow repository, not in the bundle.

## 3. Bind parameters to the engine

Each parameter's `x-splice-source` says where its value goes:
`engine` (`nextflow`) and `binding`, for example `params.genome`. Write the
values into a Nextflow parameters file keyed by the name after `params.`
and pass it with `-params-file`. Do not pass parameters that are absent
from the submission and have no value; Nextflow applies the workflow's own
defaults.

## 4. Choose the profile and its configuration

From `execution-profiles.json`:

- Use the operator's or person's choice, else `default_profile` (also
  `bundle.json` → `default_execution_profile`).
- Pass the profile's `config` file (`configs/<profile id>.config`, from the
  bundle) to Nextflow with `-c`.
- `config_strategy` `adopted` means a byte-identical copy of a
  configuration from the workflow repository; `generated` means nf-splice
  wrote it.
- `site_parameters[]` (`name`, `description`) are settings the operator must
  supply for their site (accounts, queues, paths). Profiles never contain
  them; keep operator values in your platform's configuration and add them
  as another `-c` file or as environment, never in the bundle.

A typical command:

```text
nextflow run <repository_url> -r <release tag> \
  -c <bundle>/configs/<profile id>.config -c <site settings>.config \
  -params-file <job>/params.json
```

The release tag is the Git tag of `pipeline.version` (for example `1.2.3` or
`v1.2.3`; `release_url`, when present, points at it). Prefer a tag or
commit over a branch so the job runs exactly the version the bundle
describes.

## 5. Prepare container images

From `components.json` → `containers[]`, for the profile's
`container_engine`:

- When `distribution` is present (a verified image file): download
  `download_uri`, check its SHA-256 equals `sha256` (and its size
  `size_bytes`), and store it under `cache_filename` in the Singularity or
  Apptainer cache directory Nextflow uses (`NXF_SINGULARITY_CACHEDIR` or
  `NXF_APPTAINER_CACHEDIR`). Nextflow then finds it without pulling.
- Otherwise use `source_images` for the runtime (`docker`, `singularity`,
  `apptainer`), which the engine pulls itself.
- When `require_downloadable_images` is `true`, every container must come
  from a verified `distribution`. If one cannot be downloaded or its hash
  does not match, refuse to start the job; do not fall back to a registry.
- `resolution.status` is `verified` (a distribution exists) or `resolved`
  (native reference only) in a published bundle.

## 6. Record the job for its results

Keep on the job: your job identifiers (`job_id_short`, `job_id_long`), the
profile `id`, the start time, the Nextflow session identifier and run name,
and the publish directory. After the job, these fill the job-level keys of
its `analysis_output.json` (`config_profile`, `execution_timestamp`,
`job_metadata`), and the publish directory is where its output records'
paths are relative to. See `splice-analysis-output`.

Engine identifiers belong to `job_metadata`. They never become a sample or
a run identifier.

The `analysis_output.json` itself is produced after the job finishes, by
classifying the published files against the bundle's output catalogue.
Platforms usually run `nf-splice analysis-output generate` for this step
on the job runner (the one place nf-splice is needed); an equivalent
implementation must follow the classification rules in
`splice-analysis-output` and validate its result against the bundle's
`outputs.schema.json`.

## Checklist

- [ ] Job pinned to one stored bundle of one workflow version.
- [ ] Every submitted value authorised by `editable_by`; violations rejected.
- [ ] Complete parameter object validated against `inputs.schema.json`.
- [ ] Values bound by `x-splice-source.binding`; passed with `-params-file`.
- [ ] Profile configuration and operator site settings passed with `-c`.
- [ ] Verified images downloaded, hashed and cached; no silent fallback.
- [ ] Job identity and engine metadata recorded for `analysis_output.json`.
