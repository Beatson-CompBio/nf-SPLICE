# `bundle.json`

Workflow bundle index.

| | |
| --- | --- |
| Contract family | `https://schemas.splice-data.io/workflow-bundle/bundle` |
| Revision | `0.3.0` |
| Formal schema | [`v0.3.0/schema.json`](v0.3.0/schema.json) |
| Example | [`v0.3.0/example.json`](v0.3.0/example.json) |

`bundle.json` is the entry point of a SPLICE workflow bundle. It identifies
the workflow, credits its authors, lists the contract revision of every
other file and says where each file is.

- **Written by:** `nf-splice build all`, from the reviewed
  `.splice-local/drafts/bundle.draft.yaml`.
- **Read by:** anything that ingests a bundle. Read this file first, then
  follow `schemas` and `files` to the other four contracts.

## Fields

A key marked required must be present whenever the object that
contains it is present. A section whose object accepts no other
keys says so.

### Top-level keys

No other top-level keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `bundle_format` | always `"splice-pipeline-bundle"` | yes | Marks the file as a SPLICE workflow bundle index. |
| `schema_id` | always `"https://schemas.splice-data.io/workflow-bundle/bundle"` | yes | Contract family URI. Use it to choose the validator for this file. |
| `schema_version` | always `"0.3.0"` | yes | Contract revision of this file. This is not the nf-splice version or the pipeline version. |
| `generated_by` | object | yes | Tool that wrote the file. |
| `pipeline` | object | yes | Identity of the workflow this file belongs to. It repeats the identity in `bundle.json` so a detached file can be matched to its bundle. |
| `maintainers` | array of objects | no | **Personal data. Published only with recorded consent.** Public maintainer contacts. |
| `schemas` | object keyed by name | yes | Contract revision and path of each of the five files. |
| `files` | object | yes | File index. There is no `outputs.json`: output metadata lives in `outputs.schema.json`. |
| `default_execution_profile` | lower-case letter, then letters, digits, `_` or `-` | no | Profile to run when the operator does not choose one. Matches a `profiles[].id` in `execution-profiles.json`. |

### `generated_by`

Tool that wrote the file. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | non-empty string | yes | Generator name, for example `nf-splice`. |
| `version` | non-empty string | yes | Generator release that wrote the file. |

### `pipeline`

Workflow identity and descriptive metadata. Only `id`, `name`, `version`, `engine` and `repository_url` are required; every other key appears only when it was reviewed. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | lower-case letters, digits and `-` | yes | Stable workflow identifier. Use it as the primary key for the workflow. |
| `name` | non-empty string | yes | Workflow name. |
| `version` | non-empty string | yes | Released version of the workflow. |
| `engine` | one of `nextflow` | yes | Workflow engine that runs the workflow. Always `nextflow` in this revision. |
| `title` | non-empty string | no | Display title. |
| `description` | non-empty string | no | One- or two-sentence summary for listings and search. |
| `long_description` | non-empty string | no | Longer description for a detail page. |
| `readme` | non-empty string | no | README reference or text. |
| `repository_url` | http or https URL | yes | Canonical source repository of the workflow. |
| `project_url` | http or https URL | no | Project website, when it differs from the repository. |
| `release_url` | http or https URL | no | Release page of this exact version. Validation checks that it matches `version`. |
| `authors` | array of objects | no | Credited authors of the workflow, in citation order. People who only reviewed the integration are not authors. |
| `funders` | array of objects | no | Funding bodies. Award identifiers appear only when they were sourced, never guessed. |
| `citation` | object (at least 1 key) | no | How to cite the workflow. At least one of the keys below is present. |
| `licence` | non-empty string | no | Licence identifier, preferably an SPDX identifier such as `MIT`. |
| `licence_url` | http or https URL | no | Link to the licence text. |
| `documentation_url` | http or https URL | no | User documentation of the workflow. |
| `support_url` | http or https URL | no | Public support page, published only when approved. |
| `engine_version_min` | non-empty string | no | Minimum engine version the workflow declares. |
| `engine_versions_tested` | non-empty string | no | Engine version or range the workflow was tested with. |
| `keywords` | array of non-empty strings (no duplicates) | no | Free-text keywords for search. There is no controlled vocabulary. |
| `pipeline_type` | non-empty string | no | Free-text kind of workflow, for grouping in a catalogue. |
| `modality` | non-empty string | no | Free-text data modality, for grouping in a catalogue. |
| `released_at` | date-time (RFC 3339) | no | Release date and time, when sourced. |

### `pipeline.authors[]` (each item)

Credited authors of the workflow, in citation order. People who only reviewed the integration are not authors. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | non-empty string | yes | Name of the person or organisation. |
| `type` | one of `person`, `organization` | no | Whether the author is a person or an organisation. |
| `affiliation` | non-empty string | no | Affiliation of the author. |
| `orcid` | `https://orcid.org/` followed by an ORCID iD | no | ORCID identifier of a person, as a full URL. |
| `role` | non-empty string | no | Contribution role, as free text. |

### `pipeline.funders[]` (each item)

Funding bodies. Award identifiers appear only when they were sourced, never guessed. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | non-empty string | yes | Funder name. |
| `award_id` | non-empty string | no | Award or grant identifier. |
| `award_title` | non-empty string | no | Award title. |
| `url` | http or https URL | no | Funder or award web page. |

### `pipeline.citation`

How to cite the workflow. At least one of the keys below is present. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `doi` | DOI such as `10.5281/zenodo.123` | no | DOI without a resolver prefix, for example `10.5281/zenodo.123`. |
| `url` | http or https URL | no | Citation web page. |
| `text` | non-empty string | no | Formatted citation text. |
| `cff_path` | non-empty string | no | Repository path of the workflow's `CITATION.cff` file. |

### `maintainers[]` (each item)

Public maintainer contacts. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | non-empty string | yes | **Personal data. Published only with recorded consent.** Contact name. |
| `role` | non-empty string | no | Contact role. |
| `affiliation` | non-empty string | no | Contact affiliation. |
| `contact_url` | http or https URL | no | Public contact page. |
| `email` | e-mail address | no | **Personal data. Published only with recorded consent; never taken from Git.** Public contact e-mail address. |

### `schemas.*` (each entry)

One entry per contract family, keyed by family URI. All five families are always present. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `version` | version `X.Y.Z` | yes | Contract revision of the referenced file. Reject revisions your code does not support. |
| `path` | relative path inside the bundle (no leading `/`, no `..`) | yes | Path of the referenced file. |

### `files`

Paths of the bundle's files, relative to the directory that holds `bundle.json`. No other keys are allowed.

| Key | Type | Required | Description |
| --- | --- | --- | --- |
| `inputs_schema` | relative path inside the bundle (no leading `/`, no `..`) | yes | Path of `inputs.schema.json`. |
| `outputs_catalogue` | relative path inside the bundle (no leading `/`, no `..`) | yes | Path of `outputs.yaml`, a human-readable view of the output catalogue. Programs should read `outputs_schema` instead. |
| `outputs_schema` | relative path inside the bundle (no leading `/`, no `..`) | yes | Path of `outputs.schema.json`, which holds the output catalogue. |
| `ro_crate` | relative path inside the bundle (no leading `/`, no `..`) | yes | Path of the published RO-Crate. |
| `components` | relative path inside the bundle (no leading `/`, no `..`) | yes | Path of `components.json`. |
| `execution_profiles` | relative path inside the bundle (no leading `/`, no `..`) | yes | Path of `execution-profiles.json`. |

## Example

<details>
<summary>Complete <code>bundle.json</code></summary>

```json
{
  "bundle_format": "splice-pipeline-bundle",
  "schema_id": "https://schemas.splice-data.io/workflow-bundle/bundle",
  "schema_version": "0.3.0",
  "generated_by": {
    "name": "nf-splice",
    "version": "0.3.0"
  },
  "pipeline": {
    "id": "example-pipeline",
    "name": "example-pipeline",
    "version": "1.2.3",
    "engine": "nextflow",
    "title": "Example pipeline",
    "description": "Example RNA-seq quantification workflow.",
    "repository_url": "https://github.com/org/example-pipeline",
    "project_url": "https://org.example.org/example-pipeline",
    "release_url": "https://github.com/org/example-pipeline/releases/tag/1.2.3",
    "authors": [
      {
        "name": "Ada Example",
        "type": "person",
        "affiliation": "Example Institute",
        "orcid": "https://orcid.org/0000-0002-1825-0097",
        "role": "author"
      },
      {
        "name": "Example Institute",
        "type": "organization",
        "role": "maintainer"
      }
    ],
    "funders": [
      {
        "name": "Example Research Council",
        "award_id": "ERC-123"
      }
    ],
    "citation": {
      "doi": "10.5281/zenodo.0000000"
    },
    "licence": "MIT",
    "licence_url": "https://opensource.org/licenses/MIT",
    "documentation_url": "https://github.com/org/example-pipeline#readme",
    "engine_version_min": "24.04.0",
    "keywords": [
      "rna-seq",
      "quantification"
    ]
  },
  "schemas": {
    "https://schemas.splice-data.io/workflow-bundle/bundle": {
      "version": "0.3.0",
      "path": "bundle.json"
    },
    "https://schemas.splice-data.io/workflow-bundle/inputs": {
      "version": "0.3.0",
      "path": "inputs.schema.json"
    },
    "https://schemas.splice-data.io/workflow-bundle/outputs": {
      "version": "0.3.0",
      "path": "outputs.schema.json"
    },
    "https://schemas.splice-data.io/workflow-bundle/components": {
      "version": "0.3.0",
      "path": "components.json"
    },
    "https://schemas.splice-data.io/workflow-bundle/execution-profiles": {
      "version": "0.3.0",
      "path": "execution-profiles.json"
    }
  },
  "files": {
    "inputs_schema": "inputs.schema.json",
    "outputs_catalogue": "outputs.yaml",
    "outputs_schema": "outputs.schema.json",
    "ro_crate": "ro-crate-metadata.json",
    "components": "components.json",
    "execution_profiles": "execution-profiles.json"
  },
  "default_execution_profile": "profile-slurm-736c75726d"
}
```

</details>

---

Generated by `scripts/generate_schema_docs.py` from the packaged
definition and `docs/schemas/fields.yaml`. Edit those, not this page.
