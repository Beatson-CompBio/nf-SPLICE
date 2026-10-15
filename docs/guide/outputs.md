# Outputs

The outputs layer is the catalogue of everything the pipeline can publish,
across all its routes: what each output is, how to recognise it by path and
whether it belongs to the job, a sample or a run. The platform uses it to
classify and display the results of every job. See
[Output routes and evidence](output-coverage.md) for how alternative and
optional routes are found and checked.

- **Draft:** `splice/drafts/outputs.draft.yaml`, the only output draft
- **Published:** `outputs.schema.json` (with the catalogue) and
  `outputs.yaml` (a readable copy)
- **Required:** at least one reviewed output, a decision on every
  discovered candidate, and a version for the job output schema

## 1. Discover candidates

`nf-splice init` finds the outputs your pipeline publishes by tracing its
publication rules (`publishDir` in processes and configuration). Outputs a
process declares but nothing publishes are not offered. Results from a real
run add evidence such as per-sample file names. Point nf-splice at an
example results directory, or a saved `ls -R` listing of one:

```bash
nf-splice configure outputs --example-output-tree example-results
```

Each discovered output becomes a *candidate* with a stable identifier such
as `output:08cff62b5636703d`. Running discovery again never changes your
earlier decisions.

## 2. List what needs review

```bash
nf-splice configure outputs --export-unresolved pending.json
```

`pending.json` lists each candidate with its suggested key, path pattern,
format and the fields still to be decided. Use `-` instead of a file name to
print to the terminal.

## 3. Accept or reject candidates

Accept a candidate by setting the fields it is missing:

```bash
nf-splice configure outputs \
  --set 'output:08cff62b5636703d.key=multiqc_report' \
  --set 'output:08cff62b5636703d.title=MultiQC report' \
  --set 'output:08cff62b5636703d.description=Quality-control summary of the whole job.' \
  --set 'output:08cff62b5636703d.category=quality_control' \
  --set 'output:08cff62b5636703d.scopes=job'
```

Reject a candidate that is not a real output:

```bash
nf-splice configure outputs \
  --set 'output:4043299e9097a563.action=reject' \
  --set 'output:4043299e9097a563.reason=Duplicate of the report pattern'
```

| Field | Meaning |
| --- | --- |
| `key` | Stable identifier, lower-case with `_` |
| `title`, `description` | What users see |
| `category` | Free-text grouping, such as `quality_control` |
| `stage` | Optional free-text processing stage |
| `scopes` | `job`, `sample` and/or `run`, comma-separated |
| `formats` | For example `html`, `tsv`, `bam`, comma-separated |
| `entity_types` | `file` or `directory` |
| `path_patterns` | Regular expressions anchored with `^` and `$` |

Categories and stages are free text; there is no fixed list.

## 4. Scopes and path patterns

The scope says which unit owns an output. Path patterns are matched against
paths relative to the job's publish directory:

| Scope | Pattern must contain | Example pattern |
| --- | --- | --- |
| `job` | no placeholder | `^multiqc/multiqc_report\.html$` |
| `sample` | `{sample}` | `^quant/{sample}/counts\.tsv$` |
| `run` | `{run}`, and `{sample}` unless a sample sheet maps runs to samples | `^qc/{sample}/{run}\.json$` |

`{sample}` captures the sample identifier and `{run}` captures the platform
run identifier.

## 5. Set the job output schema version

Each job's `analysis_output.json` is validated by a schema whose version you
choose. Start at `1.0.0` and raise it when the outputs change:

```bash
nf-splice configure outputs --contract-version 1.0.0
```

## Review many candidates at once

A decision file records all decisions in one place, which is useful in CI:

```yaml
actions:
  - action: version
    schema_version: 1.0.0
  - action: accept
    candidate_id: output:08cff62b5636703d
    output:
      key: multiqc_report
      title: MultiQC report
      description: Quality-control summary of the whole job.
      category: quality_control
      scopes: [job]
      formats: [html]
      entity_types: [file]
      path_patterns: ['^multiqc/multiqc_report\.html$']
  - action: reject
    candidate_id: output:4043299e9097a563
    reason: Duplicate of the report pattern
```

```bash
nf-splice configure outputs --decision-file output-decisions.yaml
```

The actions `merge` (several candidates become one output) and `split` (one
candidate becomes several) are also available, here and in the wizard.

## Preview the result

```bash
nf-splice preview outputs --format json
```

The preview shows exactly what would be published. It is never written to
disk.

Field references: [`outputs.schema.json`](../schemas/outputs/README.md) and
[`analysis_output.json`](../schemas/analysis-output.md).
