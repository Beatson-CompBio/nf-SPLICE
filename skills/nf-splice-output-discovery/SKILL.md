---
name: nf-splice-output-discovery
description: Build the output catalogue for a Nextflow pipeline across all its routes (alternative aligners, optional steps, conditional QC), use example results correctly, and keep the catalogue distinct from a job's analysis_output.json. Use when reviewing the outputs layer.
---

# nf-splice output discovery

## When to use

Use this skill when reviewing `splice/drafts/outputs.draft.yaml`, deciding
which outputs belong in the catalogue, or interpreting example results.

## Two different products

| | Output catalogue | `analysis_output.json` |
| --- | --- | --- |
| Where | `splice/outputs.schema.json` (`x-output-catalog`) and `splice/outputs.yaml` | Written per completed job, outside the bundle |
| Meaning | Every output type the pipeline **may** publish across its supported routes | The files **one job actually published** |
| Built from | Reviewed static evidence, optionally improved by examples | Observed paths classified against the catalogue |

A valid `analysis_output.json` need not contain every catalogue type. Never
remove a catalogue output only because one example run lacks it. Never put a
file into `analysis_output.json` that the run did not produce.

## Prerequisites

- The identity layer is ready (outputs compile against it).
- Optional: one or more authorised example outputs (a results directory, a
  saved `ls -R` or `tree` listing, or an output index).

## Tools

`analyse_routes`, `list_pending` (layer `outputs`), `read_source`,
`search_source`, `list_example_outputs`, `reconcile_example_outputs`,
`discover_outputs`, `accept_output`, `reject_output`, `merge_outputs`,
`split_output`, `update_output`, `set_output_contract_version`,
`validate_layer`, `assess`.

## Workflow

1. Run `analyse_routes`. It separates **published** outputs (reached by a
   `publishDir` rule in a process, a configuration `withName` selector or the
   configuration's default rule) from **declared-only** outputs. A process
   `output:` declaration alone never proves publication; intermediates
   (`not_published`) do not belong in the catalogue.
2. Read each route's conditions (`params.aligner == 'star'`,
   `not (params.aligner == 'star')`, `params.run_salmon`, `!params.skip_qc`).
   Alternative routes are all supported possibilities: STAR and HISAT2
   outputs both belong in the catalogue, as do optional outputs such as
   Salmon's.
3. Check statuses: `confirmed_from_code` (explicit rule, reachable process),
   `inferred_unverified` (default rule, `saveAs`, run-time path values),
   `unresolved` (path computed at run time), `not_reachable` (process never
   invoked). Investigate inferred and unresolved routes in the source with
   `read_source` before accepting them; reject not-reachable ones with a
   reason.
4. For each pending candidate, accept it with a complete reviewed output or
   reject it with a reason. Keep semantically different outputs apart (STAR
   and HISAT2 alignments are separate output types), and merge only true
   duplicates. Choose scopes carefully: `job` (one per run of the pipeline),
   `sample` (per biological sample; the pattern must capture
   `(?P<sample_id>...)` or `{sample}`), `run` (per platform run). Categories
   and labels are free text; do not impose a scientific vocabulary.
5. If examples were supplied, run `reconcile_example_outputs`:
   - **classified**: maps to one output type;
   - **unclassified**: no pattern matches; investigate and extend the
     catalogue if the source justifies it, otherwise report it;
   - **ambiguous**: several patterns match; make the patterns distinct;
   - **not observed**: expected for routes the run did not take; keep them;
   - **limitations**: empty files, skipped symlinks, partial listings.
   An example is evidence of one run. When it conflicts with the source,
   say so: in an assisted session discuss it; in an autonomous run record
   it and follow the conservative, source-backed choice.
6. Without examples, rely on static evidence and say which outputs only a
   run could confirm.
7. Finish with `validate_layer` on `outputs`, then `assess` after building.

## Verification gates

- `validate_layer` (`outputs`) has no errors.
- After the build, `assess` reports three separate results: contract
  validity, observed-output compatibility (per example) and the coverage
  assessment. None implies the others. A valid bundle does not prove route
  coverage; a valid example inventory proves only one run's outputs.

## Failure handling

- Unclassified observed files make inventory generation fail by default.
  `nf-splice analysis-output generate --allow-unclassified` omits them only
  when a person chooses it, and every omitted path is reported.
- Dynamic `publishDir` paths, `saveAs` renaming and missing sample or run
  identifiers are reported as issues to resolve, not guessed.

## Evidence reporting

For each accepted output, cite the process, the publication rule location
and the route conditions. Never claim the catalogue is exhaustive: static
analysis cannot see outputs named at run time or configuration supplied at
launch.

## Safety boundaries

Example outputs are read-only evidence: never modify them. Never fabricate
observations, and never run the pipeline to obtain them.
