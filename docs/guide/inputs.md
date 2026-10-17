# Inputs

The inputs layer describes the pipeline's parameters and decides who may
change each one when a job is submitted. It is published as
`inputs.schema.json`, a standard JSON Schema the platform uses to build forms
and validate values.

- **Draft:** `.splice-local/drafts/inputs.draft.yaml`
- **Source:** your `nextflow_schema.json`, imported by `nf-splice init`
  (with no schema, the draft is an empty contract to write by hand)

## Every parameter, nobody allowed to change it yet

`init` imports every declared parameter, hidden, advanced and institutional
ones included, with its types, defaults, ranges, enums, groups, references
and nf-schema hints unchanged. Each one starts with the most conservative
policy:

```yaml
x-splice-access:
  editable_by: []      # nobody may change the value at run time
x-splice-ui:
  visibility: hidden   # forms do not show it
```

That is already a valid contract: the draft validates and builds without
deciding anything. You then open up what should be changeable.

## Access policies

| `editable_by` | Who may change it | Typical parameters |
| --- | --- | --- |
| `[platform]` | The SPLICE platform | Sample sheet or job file, output and work locations, resource limits, reference file paths |
| `[user, platform]` | The person submitting the job, and the platform | A reference genome chosen from a controlled list |
| `[user]` | The person submitting the job | Scientific thresholds, aligner or trimmer choice |
| `[user, agent]` | The person, and the platform's runtime agent | Tuning parameters an approved assistant may adjust |
| `[]` | Nobody: the default is fixed | Internal switches, logging, institutional plumbing |

Any combination of `user`, `platform` and `agent` is allowed. The runtime
principal `agent` is a role in the SPLICE platform; it has nothing to do
with an AI that helps you write the draft, and is never granted because one
did. Free-form arguments (`extra_*_args`) and switches that skip required QC
deserve particular care.

Edit the draft directly, or from the command line:

```bash
nf-splice configure inputs \
  --set genome=user,platform \
  --set outdir=platform \
  --set min_mapped_reads=user,agent
nf-splice configure inputs --visibility min_mapped_reads=standard
```

Visibility (`standard`, `advanced`, `hidden`) controls how a form presents a
parameter; it never changes who may set it. Many decisions at once:

```json
[
  {"parameter": "genome", "editable_by": ["user", "platform"], "visibility": "standard"},
  {"parameter": "outdir", "editable_by": ["platform"]}
]
```

```bash
nf-splice configure inputs --decision-file input-access.json
```

## Parameters the code reads

```bash
nf-splice draft parameters
```

lists where workflow code and configs read `params.*`: references the
contract does not declare, values a config sets for itself (such as
nf-core's `params.genomes` reference map), mentions only in comments, and
declared parameters no code reads. Validation warns about undeclared
executable references; declare one only if a job may set it.

## Can a job run?

A contract can be valid while a job still could not run. After building,
`nf-splice validate` checks the runtime-parameters dimension: every required
value and the sample sheet without a default must be suppliable by someone
(a principal in `editable_by`) or set in the default profile's config.

## When `nextflow_schema.json` changes

```bash
nf-splice configure inputs --reimport
```

This is a three-way merge: new parameters arrive with `editable_by: []` and
hidden, removed ones disappear, changed definitions are merged, and your
policies are kept. An upstream change that overlaps your own edit stops the
re-import and is reported.

## Check the layer

```bash
nf-splice draft validate inputs
```

Field reference: [`inputs.schema.json`](../schemas/inputs/README.md).
