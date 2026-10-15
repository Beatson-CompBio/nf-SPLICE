# `components.json`

Workflow component and container inventory.

| | |
| --- | --- |
| Contract family | `https://schemas.splice-data.io/workflow-bundle/components` |
| Revision | `0.3.0` |
| Formal schema | [`v0.3.0/schema.json`](v0.3.0/schema.json) |
| Example | [`v0.3.0/example.json`](v0.3.0/example.json) |

`components.json` lists the software the workflow runs and the container
images it needs. It keeps three things apart: the native image
references for each runtime, the modules that use them and, when one has
been verified, a downloadable image file.

- **Written by:** `nf-splice build all`, from the reviewed
  `splice/drafts/components.draft.yaml`.
- **Read by:** platforms that pre-fetch or cache images before running
  jobs, and software inventories.

To fetch an image, use `distribution` when it is present: it is a file
nf-splice downloaded and hashed itself. Otherwise use `source_images`
with the matching runtime. A registry reference such as
`quay.io/org/tool:1.0` is not a downloadable file.

## Fields

A key marked required must be present whenever the object that
contains it is present. A section whose object accepts no other
keys says so.

### Top-level keys

No other top-level keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `schema_id` | always `"https://schemas.splice-data.io/workflow-bundle/components"` | yes | Contract family URI. Use it to choose the validator for this file. |
| `schema_version` | always `"0.3.0"` | yes | Contract revision of this file. This is not the nf-splice version or the pipeline version. |
| `generated_by` | object | yes | Tool that wrote the file. |
| `pipeline` | object | yes | Identity of the workflow this file belongs to. It repeats the identity in `bundle.json` so a detached file can be matched to its bundle. |
| `require_downloadable_images` | boolean | yes | When `true`, every container has a verified `distribution`, and a platform should refuse a bundle where one cannot be downloaded rather than fall back silently. |
| `containers` | array of objects | yes | Container images. |
| `components` | array of objects | yes | Workflow modules. |

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

### `containers[]` (each item)

Container images. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | `container-` followed by 12 hexadecimal characters | yes | Stable container identifier. Modules link to it through `container_id`. |
| `type` | one of `docker`, `singularity`, `apptainer`, `oras` | yes | Runtime of `uri`: `singularity` or `apptainer` for a verified distribution, otherwise the runtime of the native reference. |
| `uri` | non-empty string | yes | The verified download URL when a distribution exists, otherwise the native reference. A convenience summary: prefer `distribution` and `source_images`, which say exactly what can be downloaded and for which runtime. |
| `source_images` | object (at least 1 key) | yes | Native references. |
| `distribution` | object | no | Verified image file. |
| `resolution` | object | yes | Readiness. |
| `legacy_ids` | array of strings: `container-` followed by 12 hexadecimal characters (no duplicates) | no | Earlier identifiers of this container, kept when a pre-release test bundle was rebuilt. Usually absent. |

### `containers[].source_images`

Native image references, one per runtime. At least one is present. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `docker` | non-empty string | no | Docker or OCI registry reference. |
| `singularity` | non-empty string | no | Singularity reference. |
| `apptainer` | non-empty string | no | Apptainer reference. |

### `containers[].distribution`

A verified, directly downloadable image file. Present only after `nf-splice containers verify` succeeded. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `download_uri` | https URL | yes | HTTPS URL of the image file. |
| `sha256` | 64 lower-case hexadecimal characters | yes | SHA-256 of the file, computed by nf-splice from the bytes it downloaded. Check it after downloading. |
| `size_bytes` | integer ≥ 1 | yes | File size in bytes. |
| `filename` | non-empty string | yes | File name of the image. |
| `format` | one of `sif`, `img` | yes | Image format: `sif` or `img`. |
| `cache_filename` | non-empty string | yes | File name Nextflow's Singularity or Apptainer cache uses for the source image. Store the file under this name to pre-populate the cache. |
| `source_runtime` | one of `singularity`, `apptainer` | yes | Runtime the file is for. |
| `source_image_digest` | `sha256:` followed by 64 hexadecimal characters | no | Digest of the upstream image, when known. |

### `containers[].resolution`

Readiness of the image. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `status` | one of `discovered`, `needs_review`, `resolved`, `needs_materialisation`, `published`, `verified`, `blocked` | yes | Readiness state. Published bundles contain `resolved` (native reference only) or `verified` (downloadable file). |
| `reasons` | array of non-empty strings | no | Machine-readable reasons for the state. |

### `components[]` (each item)

Workflow modules. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | non-empty string | yes | Stable module identifier. |
| `type` | always `"workflow_module"` | yes | Kind of component. Always `workflow_module` in this revision. |
| `name` | non-empty string | yes | Module name. |
| `path` | non-empty string | yes | Module directory in the workflow repository. |
| `namespace` | non-empty string | yes | Module namespace, such as `nf-core` or `local`. |
| `tool` | object | yes | Wrapped tool. |
| `evidence` | array of non-empty strings | yes | Repository locations the module was found from. |
| `container_id` | `container-` followed by 12 hexadecimal characters | no | Container the module runs in. Matches a `containers[].id`. |
| `conda_packages` | array of non-empty strings | no | Conda package specifications the module declares. |

### `components[].tool`

Tool the module wraps. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | non-empty string | yes | Tool name. |
| `version` | non-empty string | no | Reviewed tool version. |

## Example

<details>
<summary>Complete <code>components.json</code></summary>

```json
{
  "schema_id": "https://schemas.splice-data.io/workflow-bundle/components",
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
  "require_downloadable_images": true,
  "containers": [
    {
      "id": "container-72b9a77e52e7",
      "type": "singularity",
      "uri": "https://images.example.org/quay.io-biocontainers-fastqc-0.12.1--hdfd78af_0.img",
      "source_images": {
        "docker": "quay.io/biocontainers/fastqc:0.12.1--hdfd78af_0",
        "singularity": "https://depot.galaxyproject.org/singularity/fastqc:0.12.1--hdfd78af_0"
      },
      "distribution": {
        "download_uri": "https://images.example.org/quay.io-biocontainers-fastqc-0.12.1--hdfd78af_0.img",
        "sha256": "0000000000000000000000000000000000000000000000000000000000000000",
        "size_bytes": 123456789,
        "filename": "quay.io-biocontainers-fastqc-0.12.1--hdfd78af_0.img",
        "format": "img",
        "cache_filename": "quay.io-biocontainers-fastqc-0.12.1--hdfd78af_0.img",
        "source_runtime": "singularity"
      },
      "resolution": {
        "status": "verified"
      }
    }
  ],
  "components": [
    {
      "id": "modules__nf-core__fastqc",
      "type": "workflow_module",
      "name": "fastqc",
      "path": "modules/nf-core/fastqc",
      "namespace": "nf-core",
      "tool": {
        "name": "fastqc",
        "version": "0.12.1"
      },
      "evidence": [
        "modules/nf-core/fastqc/main.nf"
      ],
      "container_id": "container-72b9a77e52e7"
    }
  ]
}
```

</details>

---

Generated by `scripts/generate_schema_docs.py` from the packaged
definition and `docs/schemas/fields.yaml`. Edit those, not this page.
