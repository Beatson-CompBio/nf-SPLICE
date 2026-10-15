---
name: nf-splice-validation
description: Validate nf-splice drafts and SPLICE bundles deterministically, interpret contract validity versus observed-output compatibility versus route coverage, and run optional nf-core checks only when available and permitted. Use before declaring any integration step done.
---

# nf-splice validation

## When to use

Use this skill before reporting any stage, build or integration as done, and
whenever a person asks whether a bundle is valid or complete.

## Prerequisites

Drafts exist (`nf-splice init`). Building needs every layer ready.

## Tools and commands

| Purpose | Tool | Command |
| --- | --- | --- |
| One draft | `validate_layer` | `nf-splice draft validate outputs` |
| Every draft | `workspace_status` | `nf-splice status` |
| Cross-layer readiness and diff | `preview_build` | `nf-splice plan` |
| Build | `build_bundle` | `nf-splice build all` |
| Published bundle | `validate_bundle` | `nf-splice validate` |
| Three separate results | `assess` | `nf-splice assess --example-output results/` |
| Optional external checks | `run_optional_checks` | `nf-splice assess --allow external_tools --allow run_nextflow --allow network` |
| Verified archive | (export stage) | `nf-splice export --archive-scope bundle` |
| Local commit of the bundle | `git_commit` | `nf-splice git commit` |

## Workflow

1. Validate each draft you changed. Fix every error; warnings are reported
   but do not block.
2. Run the cross-layer preview. Publication is blocked while any layer has
   errors.
3. Build. The build is transactional: an interrupted build is recovered with
   `nf-splice draft recover`, and existing published files are never
   replaced silently.
4. Validate the published bundle.
5. Assess. Report the three results separately:
   - **Contract validity**: the validators accept the bundle files and their
     cross-file relationships.
   - **Observed-output compatibility**: each example's paths are classified
     and a real `analysis_output.json` is generated and validated (with a
     placeholder job identity during assessment).
   - **Coverage assessment**: published routes covered by the catalogue,
     excluded by review, not covered or unresolved.
6. Optional checks: nf-core lint runs only for nf-core pipelines, with
   supported nf-core (3.x or 4.x) and Nextflow installed, and only with the
   `external_tools`, `run_nextflow` and `network` permissions, because it
   runs `nextflow config` and may contact the network. Otherwise it is
   reported as `not_applicable` or `not_run` with the reason.

## Verification gates

Only validator output counts. A model saying "valid" is not a validation.
Report `not_run` and `not_applicable` exactly; never as passed. Warnings
from nf-core are not errors, but report them.

## Failure handling

- Never relax a schema or skip a validator to make a result pass.
- If the build reports that a published file was edited by hand, the
  `overwrite` permission or a person's explicit choice is needed to replace
  it (`nf-splice build all --overwrite-edited splice/README.md`).

## Evidence reporting

Quote the validator's issue codes and JSON pointers. Distinguish
"contract valid" from "outputs observed" from "routes covered".

## Safety boundaries

Validation is read-only, except building, which writes only `splice/`.
Optional checks never install software and never run the pipeline.
