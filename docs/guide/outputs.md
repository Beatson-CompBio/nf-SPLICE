# Outputs

The outputs layer is the catalogue of everything the pipeline can publish,
across all its routes: what each output is, how to recognise it by path and
whether it belongs to the job, a sample or a run. The platform uses it to
classify and display the results of every job. See
[Output routes and evidence](output-coverage.md) for how alternative and
optional routes are found and checked.

- **Draft:** `.splice-local/drafts/outputs.draft.yaml`, the only output draft
- **Published:** `outputs.schema.json` (with the catalogue) and
  `outputs.yaml` (a readable copy)

## The seeded catalogue

`nf-splice init` fills the draft for you:

- from a previously published `splice/outputs.yaml` (the 0.3.0 layout or an
  earlier one), which people already reviewed; otherwise
- with one entry per output the pipeline publishes, found by tracing its
  publication rules (`publishDir` in processes and configuration) across
  every route. Outputs a process declares but nothing publishes are not
  included.

Seeded entries are first guesses: titles from emit names, categories from
the directory the pipeline publishes to (`^segmentation/...` gives
`segmentation`; nf-splice prescribes no category list), formats from file
names, scopes from the path. What cannot be known is empty, for example a
description, and validation says so (`unresolved`). Example results from a
real run add evidence:

```bash
nf-splice configure outputs --example-output-tree example-results
```

That updates discovery hints; it never changes your draft.

## Author the catalogue

Edit the file. You may correct any entry, add outputs discovery never saw,
delete false ones, or replace the whole list:

```yaml
contract:
  schema_version: 1.0.0
categories:
  quality_control:
    title: Quality control
outputs:
  - key: multiqc_report
    title: MultiQC report
    description: Quality-control summary of the whole job.
    category: quality_control
    formats: [html]
    scopes: [job]
    entity_types: [file]
    path_patterns: ['^multiqc/multiqc_report\.html$']
  - key: star_alignment
    title: STAR alignment
    description: Coordinate-sorted STAR alignment per sample.
    category: alignment
    formats: [bam]
    scopes: [sample]
    entity_types: [file]
    path_patterns: ['^star/{sample}\.Aligned\.sortedByCoord\.out\.bam$']
excluded_routes:
  - process: SAMTOOLS_STATS
    reason: Intermediate statistics are summarised by MultiQC.
```

Or edit one entry by its key from the command line:

```bash
nf-splice configure outputs \
  --set report.description="Job report." \
  --set report.category=job_report \
  --set report.scopes=job
```

| Field | Meaning |
| --- | --- |
| `key` | Stable identifier, lower-case with `_` |
| `title`, `description` | What users see |
| `category` | Free-text grouping chosen for the pipeline, such as `quality_control` or `segmentation` |
| `stage` | Optional free-text processing stage |
| `scopes` | `job`, `sample` and/or `run` |
| `formats` | Any lower-case format names, such as `html`, `bam`, `ome-tiff`, `zarr` |
| `entity_types` | `file` or `directory` |
| `path_patterns` | Regular expressions anchored with `^` and `$` |
| `labels` | Optional name/value pairs, such as the aligner |

`excluded_routes` is draft-only: published routes you leave out on purpose,
by `process` or by `glob`, each with a `reason` and, optionally, a `kind`:
`intermediate` (a file the platform need not classify), `false_positive`
(static discovery reported a route the pipeline does not publish) or
`out_of_scope`.

## Scopes and path patterns

The scope says which unit owns an output. Path patterns are matched against
paths relative to the job's publish directory:

| Scope | Pattern must contain | Example pattern |
| --- | --- | --- |
| `job` | no placeholder | `^multiqc/multiqc_report\.html$` |
| `sample` | `{sample}` | `^quant/{sample}/counts\.tsv$` |
| `run` | `{run}`, and `{sample}` unless a sample sheet maps runs to samples | `^qc/{sample}/{run}\.json$` |

## Coverage

Validation compares the catalogue with the routes the pipeline publishes,
and says how firm the evidence for each uncovered route is:

| Finding | When | Severity |
| --- | --- | --- |
| `route_not_covered` | The code always publishes the path: no branch, `when:`, switch, `saveAs` or run-time path | error |
| `conditional_route_not_covered` | The route runs only under a condition (named in the message), or its paths depend on configuration | warning |
| `route_unverified` | Static analysis could not resolve whether or what the route publishes | warning |

Resolve each by adding or correcting an output, or by excluding the route
with a reason (`kind: false_positive` when the analysis is wrong). An
alternative route stays in the catalogue even if your example run took
another branch: the catalogue is the union of every route. Only
established routes block the build, because static analysis over-reports
routes decided at run time.

## Set the job output schema version

Each job's `analysis_output.json` is validated by a schema whose version you
choose. `init` starts it at the pipeline's version when that is X.Y.Z; raise
it when the outputs change:

```bash
nf-splice configure outputs --contract-version 1.0.0
```

## Discovery hints (optional)

The wizard lists discovery candidates under *Discovery hints* and can turn
one into an entry (accept, merge, split) or record that it does not apply
(reject). `nf-splice configure outputs --decision-file` applies such actions
from a file, which some teams like in CI. None of this is required: a valid
catalogue builds with every hint untouched.

## Preview the result

```bash
nf-splice preview outputs --format json
```

The preview shows exactly what would be published. It is never written.

Field references: [`outputs.schema.json`](../schemas/outputs/README.md) and
[`analysis_output.json`](../schemas/analysis-output.md).
