# Execution profiles

The execution-profiles layer lists the reviewed ways to run the pipeline,
each with its own Nextflow configuration file, and names one default. It is
published as `execution-profiles.json` and `configs/<profile>.config`.

- **Draft:** `.splice-local/drafts/execution-profiles.draft.yaml`, plus
  `.splice-local/drafts/configs/<profile>.draft.config` for generated configurations
- **Required:** at least one supported profile and exactly one default

## 1. Review the detected profiles

`nf-splice init` detects the `profiles` in your Nextflow configuration. Each
becomes a candidate such as `profile:local`. Support a profile by describing
it and choosing where its configuration comes from:

```bash
nf-splice configure execution-profiles \
  --set profile:local.type=development \
  --set profile:local.description="Local development." \
  --set profile:local.executor=local \
  --set profile:local.container_engine=singularity \
  --set profile:local.config_source=conf/local.config
```

| Field | Values |
| --- | --- |
| `type` | `test`, `development` or `production` |
| `description` | What the profile is for |
| `executor` | A Nextflow executor, such as `local`, `slurm`, `pbspro` or `awsbatch` |
| `container_engine` | `singularity`, `apptainer`, `docker`, `podman`, `conda` and others |
| `config_source` | A configuration file to adopt unchanged |
| `generate` | `true` to have nf-splice write the configuration instead |

Reject a profile the platform should not offer with `.action=reject` and a
`.reason=...`.

## 2. Adopted or generated configuration

- **Adopted** (`config_source`): nf-splice publishes your file byte for byte.
  When the file changes, the next build publishes the new version; review
  the difference with `nf-splice draft diff execution-profiles` first.
- **Generated** (`generate=true`): nf-splice writes an editable draft
  configuration with two marked sections for parameter overrides:

```text
// ***** User Pipeline Input Params *****
// ***** SPLICE Pipeline Input Params *****
```

Edit the generated draft in `.splice-local/drafts/configs/` like any other draft.

## 3. Add the SPLICE Slurm profile (optional)

For the SPLICE cluster, add a ready-made production profile:

```bash
nf-splice configure execution-profiles --slurm-default
```

It uses the Slurm executor and Singularity. It contains no site values:
the queue and account options are listed as `site_parameters` for the
platform operator to supply.

## 4. Choose the default

Exactly one profile is the default. Profile identifiers are listed under
`profiles` in the draft:

```bash
nf-splice configure execution-profiles --default profile-local-6c6f63616c
```

## What never goes into a profile

Accounts, queues, private paths, credentials and organisation addresses are
operator configuration. nf-splice blocks configurations that contain them.

Field reference:
[`execution-profiles.json`](../schemas/execution-profiles/README.md).
