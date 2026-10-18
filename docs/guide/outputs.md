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

## The starting catalogue

`nf-splice init` starts the catalogue empty, unless a previously published
`splice/outputs.yaml` (the 0.3.0 layout or an earlier one) exists: people
wrote that, so its entries are kept. nf-splice does not turn published
routes into entries: titles, descriptions and scientific meaning are yours
to write (ADR-0068). The routes are evidence you can list at any time:

```bash
nf-splice draft routes
```

It lists every route the code publishes, whether an output covers it, is
excluded with a reason, or is missing, and never writes a file. Until the
catalogue has an entry, validation says *describe at least one output
SPLICE should expose*.

## Author the catalogue

Edit the file, or add complete entries from a file:

```bash
nf-splice configure outputs --add-output qc-outputs.yaml
```

A draft looks like this:

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

Coverage compares the catalogue with the routes the pipeline publishes. It
is not a draft error: a valid catalogue that deliberately describes only
some outputs can be published. It is the `output_coverage` readiness
dimension, so such a bundle is *published, but not ready for SPLICE
ingestion* until every route is covered or excluded:

| Uncovered route | When | Effect |
| --- | --- | --- |
| established | The code always publishes the path: no branch, `when:`, switch, `saveAs` or run-time path | coverage incomplete |
| conditional | The route runs only under a condition (named), or its paths depend on configuration | coverage incomplete |
| unverified | Static analysis could not resolve whether or what the route publishes | coverage not assessed |

Resolve each by adding or correcting an output, or by excluding the route
with a reason (`kind: false_positive` when the analysis is wrong). An
alternative route stays in the catalogue even if your example run took
another branch: the catalogue is the union of every route.

## Set the job output schema version

Each job's `analysis_output.json` is validated by a schema whose version you
choose. It versions the shape of that document, not the pipeline: it is
never copied from the pipeline release. `init` takes it from a published
catalogue, otherwise leaves it empty for you to set, and you raise it when
the outputs change:

```bash
nf-splice configure outputs --contract-version 1.0.0
```

## In the workspace

The **Outputs** page lists the catalogue with each entry's scope, formats
and patterns. **+ Add output** opens a two-step editor: first what is
produced (title, a key generated from it, description, category, formats),
then where it is published, with a path-pattern builder that turns an
example path such as `quantification/SAMPLE1/counts.tsv` into
`^quantification/{sample}/counts\.tsv$` and checks it. **Duplicate**,
**Edit** and **Remove** work on the selected entry. **Browse routes** shows
the routes read-only and excludes one with a reason.

## Preview the result

```bash
nf-splice preview outputs --format json
```

The preview shows exactly what would be published. It is never written.

Field references: [`outputs.schema.json`](../schemas/outputs/README.md) and
[`analysis_output.json`](../schemas/analysis-output.md).
