---
name: nf-splice-output-discovery
description: Author the output catalogue for a Nextflow pipeline as a skilled bioinformatician would - the union of outputs it may publish across all routes (alternative aligners, optional steps, conditional QC) - rewriting the seeded draft where the evidence says so, using example results correctly and keeping the catalogue distinct from a job's analysis_output.json.
---

# nf-splice output discovery and scientific authoring

## When to use

Use this skill when authoring or reviewing
`.splice-local/drafts/outputs.draft.yaml`, deciding what belongs in the
catalogue, or interpreting example results.

## Two different products

| | Output catalogue | `analysis_output.json` |
| --- | --- | --- |
| Where | `splice/outputs.schema.json` (`x-output-catalog`) and `splice/outputs.yaml` | Written per completed job, outside the bundle |
| Meaning | Every output type the pipeline **may** publish across its supported routes | The files **one job actually published** |
| Built from | The authored draft, checked against static route evidence | Observed paths classified against the catalogue |

A valid `analysis_output.json` need not contain every catalogue type. Never
remove a catalogue output only because one example run lacks it. Never put a
file into `analysis_output.json` that the run did not produce.

## Prerequisites

- The identity layer is ready (outputs compile against it).
- `nf-splice init` has seeded the draft: from a previously published
  `splice/outputs.yaml` when one exists, otherwise one provisional entry per
  published route. Seeded categories, scopes and titles are first guesses.
- Optional: authorised example outputs (a results directory, a saved
  listing or an output index).

## Tools

`read_draft`, `contract_reference`, `analyse_routes`, `read_source`,
`search_source`, `list_example_outputs`, `reconcile_example_outputs`,
`replace_draft`, `update_output`, `set_output_contract_version`,
`validate_layer`, `assess`. Optional hints: `list_pending`, `accept_output`,
`reject_output`, `merge_outputs`, `split_output`.

## Workflow

1. `analyse_routes` separates **published** outputs (reached by a
   `publishDir` rule in a process, a configuration `withName` selector or
   the default rule) from **declared-only** intermediates. A process
   `output:` declaration alone never proves publication.
2. Read the workflow, subworkflows and modules behind each route: the
   conditions (`params.aligner == 'star'`, `params.run_salmon`,
   `!params.skip_qc`), `saveAs` renames, dynamic prefixes and globs.
   Alternative routes are all supported: STAR and HISAT2 alignments both
   belong in the catalogue, as do optional outputs such as Salmon's.
3. Compare the current draft with that evidence, even if it validates:
   false entries, missing published outputs, wrong scopes (`job`: one per
   pipeline run; `sample`: one per sample, the pattern captures `{sample}`;
   `run`: one per platform file-level run, the pattern captures `{run}`),
   poor categories or descriptions, patterns that are too broad or narrow.
4. Write the corrected catalogue as one revision: `replace_draft` with
   section `/outputs` (and `/categories`). Keep semantically different
   outputs apart, merge only true duplicates, and add outputs discovery
   missed when the source shows they are published. List published routes
   you deliberately leave out under `excluded_routes` with a reason.
5. With an example, `reconcile_example_outputs`: every observed file should
   classify to exactly one output; unobserved types may belong to other
   routes. Never infer a product from a file extension alone.
6. `validate_layer`, read the issues (including `route_not_covered`
   warnings), revise and repeat; then `complete_review`.

## Verification gates

- `validate_layer` on `outputs` reports no errors; both files compile.
- `assess` reports coverage: every published route is covered or
  deliberately excluded, and the example reconciles with no unclassified or
  ambiguous file.

## Failure handling

- `unresolved`: a seeded entry lacks a required field; supply it from the
  module's documentation or code.
- A pattern that matches nothing in an example may still be right for
  another route; check the route before changing it.
- An ambiguous example file matches two outputs: make the patterns disjoint.

## Evidence reporting

For each output, cite the publishing rule (file:line), the route
conditions, and whether an example observed it. Say which outputs only a
different run could confirm.

## Safety boundaries

Never weaken a pattern, scope or format just to pass validation, never
present intermediates as published outputs, and never edit `splice/` or
the pipeline's code.
