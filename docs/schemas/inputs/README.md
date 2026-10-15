# `inputs.schema.json`

Workflow input parameter contract.

| | |
| --- | --- |
| Contract family | `https://schemas.splice-data.io/workflow-bundle/inputs` |
| Revision | `0.3.0` |
| Formal schema | [`v0.3.0/schema.json`](v0.3.0/schema.json) |
| Example | [`v0.3.0/example.json`](v0.3.0/example.json) |

`inputs.schema.json` describes the workflow's input parameters as a
standard JSON Schema 2020-12 document, so any JSON Schema validator can
check a set of parameter values. SPLICE adds `x-splice-*` keys that say
who may change each parameter, how to present it and how it maps to the
engine.

- **Written by:** `nf-splice build all`, from the reviewed
  `splice/drafts/inputs.schema.draft.yaml` (imported from
  `nextflow_schema.json`).
- **Read by:** platforms that build parameter forms, validate submitted
  values and pass them to the engine.

Parameters are ordinary JSON Schema property definitions (`type`,
`default`, `enum`, `minimum`, `pattern`, `format`, `description` and
so on), including nf-schema annotations such as `help_text` and
`fa_icon`. They sit either directly under `properties` or inside a group
under `$defs`. Groups are documentation only: a submitted parameter
object is always flat. Each parameter is defined exactly once.

## Fields

A key marked required must be present whenever the object that
contains it is present. A section whose object accepts no other
keys says so.

### Top-level keys

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `$schema` | always `"https://json-schema.org/draft/2020-12/schema"` | yes | Standard JSON Schema dialect of this document. |
| `$id` | non-empty string | yes | Identifier of this workflow's schema. It is specific to the workflow and is not the contract family URI. |
| `type` | always `"object"` | yes | Type of the instance this schema validates. Always `object`. |
| `x-splice-contract` | object | yes | Contract family and revision of this JSON Schema document, kept separate from the standard `$schema` and `$id` keys. |
| `x-splice-pipeline` | object | yes | Workflow identity. It is not a runtime parameter. |
| `$defs` | object keyed by name | no | Named parameter groups. |
| `properties` | object keyed by name | no | Parameters that belong to no group. |
| `x-splice-draft` | must not appear | no | Draft marker used while authoring. A published file never contains it; validation rejects files that do. |

### `x-splice-contract`

Contract family and revision of this JSON Schema document, kept separate from the standard `$schema` and `$id` keys. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | always `"https://schemas.splice-data.io/workflow-bundle/inputs"` | yes | Contract family URI. |
| `version` | always `"0.3.0"` | yes | Contract revision. |
| `generated_by` | object | yes | Tool that wrote the file. |

### `x-splice-contract.generated_by`

Tool that wrote the file. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | non-empty string | yes | Generator name, for example `nf-splice`. |
| `version` | non-empty string | yes | Generator release that wrote the file. |

### `x-splice-pipeline`

Workflow identity. It is not a runtime parameter. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | lower-case letters, digits and `-` | yes | Workflow identifier, as in `bundle.json`. |
| `name` | non-empty string | yes | Workflow name. |
| `version` | non-empty string | yes | Workflow version. |
| `engine` | non-empty string | yes | Workflow engine. |
| `repository_url` | URL | no | Workflow repository. |

### `$defs.*` (each entry)

Parameter groups, as in nf-schema. The root schema references them from `allOf`.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `properties` | object keyed by name | no | Parameters of one group. |
| `required` | array of strings (no duplicates) | no | Parameters of the group that must be supplied. |

### `<parameter>`

SPLICE keys that may appear on any parameter definition, whether it is under `properties` or inside a `$defs` group.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `x-splice-access` | object | yes | Access policy of the parameter. |
| `x-splice-ui` | object | no | Presentation hints. |
| `x-splice-data` | object | no | Data reference marker. |
| `x-splice-source` | object | no | Engine binding. |

### `<parameter>.x-splice-access`

Who may set the parameter's value. Enforce this on the server; it is not a presentation hint. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `editable_by` | array of `user`, `platform`, `agent` (no duplicates) | yes | Who may set the value: any of `user`, `platform` and `agent`. An empty list means the value is fixed. |

### `<parameter>.x-splice-ui`

Presentation hints. They never grant or restrict permission. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `visibility` | one of `standard`, `advanced`, `hidden` | no | `standard` shows the parameter, `advanced` shows it in an advanced section, `hidden` hides it. Hidden parameters still exist and keep their access policy. |
| `help_text` | string | no | SPLICE-specific help. nf-schema `help_text` is kept separately. |
| `icon` | string | no | Icon hint. |
| `order` | integer ≥ 0 | no | Display order within the group, lowest first. |

### `<parameter>.x-splice-data`

Marks a parameter whose value refers to data. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `kind` | one of `file`, `directory`, `path`, `uri` | yes | What the value refers to: a `file`, `directory`, `path` or `uri`. |
| `samplesheet` | boolean | no | The value is a samplesheet with its own schema. |

### `<parameter>.x-splice-source`

How the parameter maps to the engine. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `engine` | non-empty string | yes | Engine of the binding, for example `nextflow`. |
| `binding` | non-empty string | yes | Native target of the value, for example `params.genome`. |
| `origin` | non-empty string | no | Where the definition was imported from, for example `nextflow_schema.json`. |

## Example

<details>
<summary>Complete <code>inputs.schema.json</code></summary>

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://github.com/org/example-pipeline/splice/inputs.schema.json",
  "title": "example-pipeline input parameters",
  "description": "All runnable parameters of example-pipeline 1.2.3.",
  "type": "object",
  "x-splice-contract": {
    "id": "https://schemas.splice-data.io/workflow-bundle/inputs",
    "version": "0.3.0",
    "generated_by": {
      "name": "nf-splice",
      "version": "0.3.0"
    }
  },
  "x-splice-pipeline": {
    "id": "example-pipeline",
    "name": "example-pipeline",
    "version": "1.2.3",
    "engine": "nextflow"
  },
  "$defs": {
    "input_output_options": {
      "title": "Input/output options",
      "type": "object",
      "required": [
        "input"
      ],
      "properties": {
        "input": {
          "type": "string",
          "format": "file-path",
          "mimetype": "text/csv",
          "schema": "assets/schema_input.json",
          "pattern": "^\\S+\\.csv$",
          "description": "Samplesheet.",
          "x-splice-access": {
            "editable_by": [
              "user",
              "agent"
            ]
          },
          "x-splice-ui": {
            "visibility": "standard"
          },
          "x-splice-data": {
            "kind": "file",
            "samplesheet": true
          },
          "x-splice-source": {
            "engine": "nextflow",
            "binding": "params.input",
            "origin": "nextflow_schema.json#/$defs/input_output_options/properties/input"
          }
        },
        "outdir": {
          "type": "string",
          "format": "directory-path",
          "description": "Output directory.",
          "x-splice-access": {
            "editable_by": [
              "platform"
            ]
          },
          "x-splice-source": {
            "engine": "nextflow",
            "binding": "params.outdir"
          }
        }
      }
    }
  },
  "allOf": [
    {
      "$ref": "#/$defs/input_output_options"
    }
  ]
}
```

</details>

---

Generated by `scripts/generate_schema_docs.py` from the packaged
definition and `docs/schemas/fields.yaml`. Edit those, not this page.
