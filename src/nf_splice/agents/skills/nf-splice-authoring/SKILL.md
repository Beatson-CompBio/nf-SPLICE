---
name: nf-splice-authoring
description: Author a SPLICE workflow bundle for a Nextflow pipeline with nf-splice, file first. The six YAML drafts and the native .draft.config files are the source of truth; seeded content is a scaffold to challenge, not an authority. Use when integrating a pipeline with SPLICE, in any mode.
---

# nf-splice authoring (file first)

## When to use

Use this skill whenever you create, review or change a pipeline's SPLICE
integration: the drafts below `.splice-local/drafts/` and the bundle built
from them in `splice/`. It applies equally to a person editing files, an
AI-assisted session and an autonomous run.

## Prerequisites

- An integration copy of the Nextflow pipeline (`nf-splice source prepare
  <folder-or-git-url>`), so the original is never changed.
- nf-splice never runs the pipeline. Example output of an earlier run is
  optional evidence of the routes that run took.

## How the files fit together

- One authoritative YAML draft per layer: `bundle.draft.yaml` (identity and
  assays), `inputs.draft.yaml` (the runtime input contract),
  `outputs.draft.yaml` (the output catalogue), `components.draft.yaml`,
  `execution-profiles.draft.yaml` and `provenance.draft.yaml` (the RO-Crate
  graph). Execution profiles also name native Nextflow configs in
  `.splice-local/drafts/configs/*.draft.config`, which hold the
  configuration itself.
- `nf-splice init` seeds every draft once from repository evidence (and from
  an earlier `splice/` bundle, if any) and never overwrites one afterwards.
  Seeded content is provisional: correct it.
- The `.review.json` sidecars below `.splice-local/reviews/` are provenance
  (events, advisory discovery candidates, verification records). They never
  hold field values and a candidate's status never blocks validation.
- `splice/` is generated. Never edit it; rebuild it from the drafts.
- `bundle.json` is the bundle index. Call it that, never by the name of
  Nextflow's own configuration block for pipeline metadata.

## Workflow

1. **Read** the current draft (`read_draft`, or open the file) and the field
   contract (`contract_reference`), then the real sources: main workflow,
   subworkflows, modules, configs, schema, documentation.
2. **Challenge** the seeded content: what is missing, wrong or only a guess?
   Form alternatives and check them against the code.
3. **Author** the best complete content in one coherent revision:
   `replace_draft` for a whole section (for example `/outputs`) or the whole
   file, `write_config` for a native config, or the targeted tools
   (`set_identity`, `set_parameter_access`, `update_output`). People simply
   edit the files in any editor.
4. **Validate** (`validate_layer`, `nf-splice draft validate <layer>`), read
   the issues, revise and validate again. A saved draft does not have to
   validate yet; nothing is lost while you iterate.
5. **Review**: in AI modes, call `complete_review` once the content matches
   the evidence, even if the draft already validated before you started.
6. **Build** with `nf-splice build all` (or `build_bundle` when permitted),
   then `nf-splice validate`, which reports readiness by dimension.

Discovery candidates (`list_pending`, `accept_output`, `reject_output`,
`accept_unambiguous_components`, `review_profile`, `confirm_values`) are
optional conveniences for people who prefer a table. They are never
required: a valid draft builds with every candidate untouched.

## Verification gates

- `validate_layer` reports no errors for the layer.
- `preview_build` reports no blockers before building.
- `validate_bundle` and the readiness dimensions decide whether the built
  bundle is valid and ready for ingestion. Passing a gate is not a review.

## Failure handling

- A refused write saying the file changed on disk: read it again and base the
  revision on the current file; never overwrite someone's edit.
- `unresolved` issues: a seeded entry still lacks a required value; supply it
  from evidence or leave it and say why.
- `route_not_covered` warnings: a published route matches no output; add an
  output or list it under `excluded_routes` with a reason.
- `identity_not_ready` on other layers: fix the identity first.
- `syntax`: the YAML cannot be read; it is reported, never rewritten.

## Evidence reporting

State where each value came from: a file and line, an analysis tool, an
example output, or the person. Mark what only a run could confirm as
unresolved. nf-splice records which files you inspected; report those, not
what you could have read.

## Safety boundaries

Change files only through the tools. Never edit the pipeline's own code or
`splice/`, never invent identifiers, checksums, URLs, people or licences,
never publish contact details without a person's consent, and never call a
layer ready before its validation passes.
