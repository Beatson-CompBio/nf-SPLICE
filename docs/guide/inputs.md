# Inputs

The inputs layer describes the pipeline's parameters and decides who may
change each one when a job is submitted. It is published as
`inputs.schema.json`, a standard JSON Schema the platform uses to build forms
and validate values.

- **Draft:** `.splice-local/drafts/inputs.draft.yaml`
- **Source:** your `nextflow_schema.json`, imported by `nf-splice init`
- **Required:** an access policy for every parameter

## Access policies

Every parameter stays in the contract. For each one, choose who may set its
value:

| Value | Who may set it | Typical parameters |
| --- | --- | --- |
| `user` | The person submitting the job | Genome, thresholds, sample sheet |
| `platform` | The SPLICE platform | Output directory, resource limits |
| `agent` | An approved automated assistant | Optional tuning parameters |
| *(empty)* | Nobody: the value is fixed | Internal switches |

Combine values with commas. For example, `user,agent` lets both the user and
an assistant change the parameter.

```bash
nf-splice configure inputs \
  --set genome=user,agent \
  --set outdir=platform \
  --set max_cpus=platform
```

A parameter left without a policy blocks publication.

## Visibility

Visibility controls how a form presents a parameter. It never changes who
may set it.

```bash
nf-splice configure inputs --visibility max_cpus=hidden
```

Use `standard`, `advanced` or `hidden`.

## Many parameters at once

For large pipelines, put the decisions in a JSON file:

```json
[
  {"parameter": "genome", "editable_by": ["user", "agent"]},
  {"parameter": "outdir", "editable_by": ["platform"], "visibility": "hidden"}
]
```

```bash
nf-splice configure inputs --decision-file input-access.json
```

## When `nextflow_schema.json` changes

Bring upstream changes into the draft without losing your policies:

```bash
nf-splice configure inputs --reimport
```

New parameters arrive without a policy, removed parameters disappear, and
changed definitions are merged. If an upstream change conflicts with an edit
you made in the draft, the re-import stops and reports the conflict.

## Check the layer

```bash
nf-splice draft inspect inputs
```

Field reference: [`inputs.schema.json`](../schemas/inputs/README.md).
