---
name: nf-splice-validation
description: Validate nf-splice drafts and SPLICE bundles deterministically; tell a safely saved draft from a publishable one, contract validity from scientific and operational readiness, and run optional external checks (nf-core lint, rocrate-validator, nextflow config) only when installed and permitted. Use before declaring any step done.
---

# nf-splice validation and recovery

## When to use

Use this skill before reporting any stage, build or integration as done,
when a person asks whether a bundle is valid or ready, and when recovering
from an interrupted or failed step.

## Prerequisites

Drafts exist (`nf-splice init`). Building needs every layer ready.

## Tools and commands

| Purpose | Tool | Command |
| --- | --- | --- |
| One draft | `validate_layer` | `nf-splice draft validate outputs` |
| Every draft | `workspace_status` | `nf-splice status` |
| Cross-layer plan and diff | `preview_build` | `nf-splice plan` |
| Build | `build_bundle` | `nf-splice build all` |
| Bundle and readiness dimensions | `validate_bundle` | `nf-splice validate` |
| Contract, observed outputs, coverage | `assess` | `nf-splice assess --example-output results/` |
| Optional external checks | `run_optional_checks` | `nf-splice assess --allow external_tools --allow network` |
| Effective profile configuration | - | `nf-splice draft check-config default --allow run_nextflow` |
| Archive with root RO-Crate | (export stage) | `nf-splice export --archive-scope pipeline` |

## Workflow

1. **Saved is not ready.** A draft written safely (restricted YAML, its
   marker kept, no conflicting edit) may still fail its contract. That is
   expected while authoring; validate, read the issues, revise.
2. Validate each draft you changed; errors block, warnings inform.
3. Run the cross-layer plan; publication is blocked while any layer errs.
4. Build. The build is transactional: interrupted builds are recovered with
   `nf-splice draft recover`; published files are never replaced silently,
   and configs nf-splice published earlier that nothing uses any more are
   removed in the same transaction.
5. Validate the published bundle. Every command and the workspace state one
   lifecycle: whether the drafts validate, whether the bundle is published
   and current, whether it is structurally valid and scientifically
   classified, and whether it is ready for SPLICE ingestion, with a
   headline such as `Published, but not ready for SPLICE ingestion` and the
   reason per dimension. A successful build is never ingestion readiness;
   a dimension that could not be assessed is not ready. The seven readiness
   dimensions are: contracts, scientific classification, runtime parameters
   (indispensable inputs someone can supply; a null default supplies
   nothing), deployment (images the default profile's engine can use;
   Conda-only components under a container engine block), provenance
   (RO-Crate 1.1 and identity agreement), output coverage (every
   established or conditional published route is described or excluded with
   a reason; `nf-splice draft routes` lists them) and publication
   consistency. Incomplete coverage never blocks publishing a valid,
   deliberately limited catalogue; it blocks ingestion readiness.
6. Assess: contract validity, observed-output compatibility and route
   coverage are three separate results.
7. Optional checks run only when installed, applicable and permitted;
   otherwise they are `not_run` or `not_applicable` with the reason.

## Verification gates

Only validator output counts. A model saying "valid" is not a validation.
Report `not_run` and `not_applicable` exactly, never as passed. A validated
draft has not therefore been reviewed scientifically.

## Failure handling

- Never relax a schema or skip a validator to make a result pass.
- A malformed draft is reported (`syntax`) and never rewritten: fix it in an
  editor.
- A hand-edited published file needs a person's explicit choice to replace
  it (`nf-splice build all --overwrite-edited splice/README.md`).
- After an interrupted session, the latest safely written drafts remain;
  validate them and continue in any mode.

## Evidence reporting

Quote the issue codes, files and JSON pointers. Keep "drafts valid",
"published", "contract valid", "classified", "outputs observed", "routes
covered" and "ready for ingestion" apart. For the RO-Crate, keep
nf-splice's structural checks apart from standards validation, and say
which ran.

## Safety boundaries

Validation is read-only, except building, which writes only `splice/`.
Optional checks never install software and never run the pipeline;
`nextflow config` evaluates configuration code only with `run_nextflow`.
