---
name: nf-splice-authoring
description: Author a SPLICE workflow bundle for a Nextflow pipeline with nf-splice, layer by layer (identity, inputs, outputs, components, execution profiles, provenance) through the deterministic draft services. Use when integrating a pipeline with SPLICE.
---

# nf-splice authoring

## When to use

Use this skill to integrate a Nextflow pipeline with the SPLICE platform:
create the drafts, review each layer, build the bundle in `splice/`.

## Prerequisites

- A Nextflow pipeline repository: `main.nf`, `nextflow.config`, ideally
  `nextflow_schema.json` and `modules.json`.
- nf-splice never runs the pipeline. Example output from an earlier run is
  optional evidence (see the output-discovery skill).

## How the files fit together

- `splice/drafts/*.draft.yaml` are the editable source, one per layer. Each
  has a `.review.json` sidecar recording candidates, confirmations and
  review events.
- `splice/*.json`, `splice/outputs.yaml` and `splice/README.md` are
  published files, built only from ready drafts by the transactional build.
- `bundle.json` is the bundle index. Call it that, never by the name of
  Nextflow's own configuration block for pipeline metadata.

## Workflow

Work in this order; a later layer may depend on an earlier one.

1. **Discover**: `initialise_drafts` (or `nf-splice init`) creates missing
   drafts from repository evidence and never overwrites existing ones.
2. **Identity** (`bundle.draft.yaml`): name, version, repository URL and a
   concise description are required. Detected values must be confirmed
   (`confirm_values` on layer `bundle`) after you check them against the
   repository. Never invent licences, people or URLs.
3. **Inputs**: run `sync_identity` once the identity is ready. Give every
   parameter exactly one access policy with `set_parameter_access`:
   `user` (the person launching a job), `platform` (SPLICE sets it, such as
   `outdir`), `agent`, or nobody (empty list). Secret-like parameters must
   never be user-visible.
4. **Outputs**: follow the output-discovery skill. Accept each candidate
   with a complete reviewed output (key, title, description, free-text
   category, formats, scopes, entity types, anchored path patterns) or
   reject it with a reason. Set the analysis-output schema version with
   `set_output_contract_version` (for example `1.0.0`).
5. **Components**: `accept_unambiguous_components` accepts modules whose
   container evidence is unambiguous; review the rest with
   `accept_component` or `reject_component`; set the image policy with
   `set_image_policy`.
6. **Execution profiles**: review each profile candidate with
   `review_profile` (type, description, executor, container engine, adopted
   config source or a generated config) and choose one default with
   `set_default_profile`. Profile IDs come from `list_pending`.
7. **Provenance**: choose `provenance_strategy`: `include` an existing valid
   RO-Crate, `enriched` to repair one, or `generated` for a minimal one.
8. **Validate and build**: `preview_build` shows blockers; the engine runs
   the cross-layer check and `build_bundle`.

The CLI equivalents are `nf-splice configure <layer>`, `nf-splice draft
confirm`, `nf-splice plan` and `nf-splice build all`.

## Verification gates

After each change, `validate_layer` must report no errors before the layer
is complete. `preview_build` must report no blockers before building.
`validate_bundle` decides whether the built bundle is valid.

## Failure handling

- `conflict` errors mean the draft changed since you read it: read it again.
- `pending_candidate` issues mean a candidate still needs a decision.
- `unconfirmed_detected_value` issues need a deliberate confirmation.
- `identity_not_ready` on other layers means fix the identity first.

## Evidence reporting

State where each decision came from: a file and line, the route analysis,
an example output, or a person's statement. Mark anything a run would be
needed to confirm as unresolved.

## Safety boundaries

Change files only through the tools. Never edit the pipeline's own code,
publish contact details without a person's consent, or describe a layer as
ready before its validation passes.
