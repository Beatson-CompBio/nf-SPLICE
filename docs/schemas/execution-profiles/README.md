# `execution-profiles.json`

Workflow execution profile catalogue.

| | |
| --- | --- |
| Contract family | `https://schemas.splice-data.io/workflow-bundle/execution-profiles` |
| Revision | `0.3.0` |
| Formal schema | [`v0.3.0/schema.json`](v0.3.0/schema.json) |
| Example | [`v0.3.0/example.json`](v0.3.0/example.json) |

`execution-profiles.json` lists the reviewed ways to run the workflow,
each with its own Nextflow configuration file under `configs/`, and names
one default.

- **Written by:** `nf-splice build all`, from the reviewed
  `.splice-local/drafts/execution-profiles.draft.yaml`.
- **Read by:** platforms that choose a configuration when they launch a
  job.

Profiles never contain site accounts, queues or credentials. Values an
operator must supply are listed in `site_parameters`.

## Fields

A key marked required must be present whenever the object that
contains it is present. A section whose object accepts no other
keys says so.

### Top-level keys

No other top-level keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `schema_id` | always `"https://schemas.splice-data.io/workflow-bundle/execution-profiles"` | yes | Contract family URI. Use it to choose the validator for this file. |
| `schema_version` | always `"0.3.0"` | yes | Contract revision of this file. This is not the nf-splice version or the pipeline version. |
| `generated_by` | object | yes | Tool that wrote the file. |
| `pipeline` | object | yes | Identity of the workflow this file belongs to. It repeats the identity in `bundle.json` so a detached file can be matched to its bundle. |
| `default_profile` | lower-case letter, then letters, digits, `_` or `-` | no | Identifier of the default profile. Matches one `profiles[].id`, and that profile has `default: true`. |
| `profiles` | array of objects (at least 1) | yes | Execution profiles. |

### `generated_by`

Tool that wrote the file. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | non-empty string | yes | Generator name, for example `nf-splice`. |
| `version` | non-empty string | yes | Generator release that wrote the file. |

### `pipeline`

Identity of the workflow this file belongs to. It repeats the identity in `bundle.json` so a detached file can be matched to its bundle. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | lower-case letters, digits and `-` | yes | Stable workflow identifier. Use it as the primary key for the workflow. |
| `name` | non-empty string | yes | Workflow name. |
| `version` | non-empty string | yes | Released version of the workflow. |
| `engine` | non-empty string | yes | Workflow engine that runs the workflow. Always `nextflow` in this revision. |
| `repository_url` | URL | no | Canonical source repository of the workflow. |

### `profiles[]` (each item)

Execution profiles. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | lower-case letter, then letters, digits, `_` or `-` | yes | Stable profile identifier. |
| `name` | non-empty string | yes | Display name. |
| `description` | non-empty string | yes | What the profile is for. |
| `type` | one of `test`, `development`, `production` | yes | Intended use: `test`, `development` or `production`. |
| `engine` | one of `nextflow` | yes | Workflow engine. |
| `executor` | non-empty string | yes | Nextflow executor, for example `local` or `slurm`. |
| `container_engine` | any JSON value | no | Container runtime this profile declares, for example `singularity` or `docker`. Optional: `null` when the profile declares none — the deployment site decides which runtime consumes the declared images. |
| `config` | `configs/<profile id>.config` | yes | Configuration file of the profile, relative to the bundle directory. Pass it to the engine, for example with `nextflow run -c`. |
| `default` | boolean | yes | Whether this is the default profile. |
| `config_strategy` | one of `adopted`, `authored` | yes | `adopted`: a byte-identical copy of a configuration owned by the workflow repository. `authored`: the native Nextflow configuration written for this bundle (by a person or an agent) in nf-splice's editable drafts. |
| `site_parameters` | array of objects | no | Operator settings. |

### `profiles[].site_parameters[]` (each item)

Operator settings. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | non-empty string | yes | Setting name. |
| `description` | non-empty string | yes | What to configure. |

## Example

<details>
<summary>Complete <code>execution-profiles.json</code></summary>

```json
{
  "schema_id": "https://schemas.splice-data.io/workflow-bundle/execution-profiles",
  "schema_version": "0.3.0",
  "generated_by": {
    "name": "nf-splice",
    "version": "0.3.0"
  },
  "pipeline": {
    "id": "example-pipeline",
    "name": "example-pipeline",
    "version": "1.2.3",
    "engine": "nextflow"
  },
  "default_profile": "profile-slurm-736c75726d",
  "profiles": [
    {
      "id": "profile-slurm-736c75726d",
      "name": "Slurm",
      "description": "SPLICE Slurm production execution.",
      "type": "production",
      "engine": "nextflow",
      "executor": "slurm",
      "container_engine": "singularity",
      "config": "configs/profile-slurm-736c75726d.config",
      "default": true,
      "config_strategy": "authored",
      "site_parameters": [
        {
          "name": "queue",
          "description": "Operator-managed Slurm partition."
        }
      ]
    }
  ]
}
```

</details>

---

Generated by `scripts/generate_schema_docs.py` from the packaged
definition and `docs/schemas/fields.yaml`. Edit those, not this page.
