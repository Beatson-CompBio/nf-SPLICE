---
name: nf-splice-input-access
description: Author a pipeline's runtime input contract - keep every declared nf-schema parameter, start from least privilege (editable_by [] and hidden), and decide from the parameter's real use in code who may change it at run time (user, platform, agent), as one coherent policy. Use at the inputs stage.
---

# nf-splice input access policy

## When to use

Use this skill when authoring or reviewing
`.splice-local/drafts/inputs.draft.yaml`, deciding who may change a
parameter when a job is submitted, or checking whether a job can run.

## Prerequisites

- The identity layer is ready (`sync_identity` copies its envelope).
- `nf-splice init` imported `nextflow_schema.json` losslessly into JSON
  Schema 2020-12. Every parameter starts with `x-splice-access.editable_by:
  []` (nobody may change it at run time) and `x-splice-ui.visibility:
  hidden`. That is a valid policy, not a missing one.

## Workflow

1. `read_draft` and `parameter_usage`: where workflow code reads each
   parameter, which references are undeclared, which are values configs set
   for themselves (such as the `genomes` reference map) and which appear only
   in comments. Read the code for anything unclear.
2. Decide each parameter's principals from its scientific and operational
   meaning, not from its name:
   - sample sheets, job files and input data locations: `platform` (SPLICE
     resolves authorised data and generates the job's inputs);
   - output and work locations, resource limits, infrastructure paths:
     `platform`; never expose arbitrary storage paths or secrets;
   - reference choice: often `user` and `platform` with a controlled choice;
     physical reference file paths: `platform`;
   - analysis thresholds and tool choices: often `user`, optionally `agent`;
     check every route supports each choice;
   - skip and save switches: case by case (some disable required QC or
     change the outputs);
   - free-form `extra_*_args` and hooks: restricted, they can bypass
     validation;
   - help, version, logging and institutional plumbing: `platform` or `[]`.
3. Visibility (`standard`, `advanced`, `hidden`) is presentation only; it
   never authorises a change.
4. Apply the whole policy as one revision (`replace_draft` or batched
   `set_parameter_access`), with reasons for uncertain cases. In an
   assisted session the person approves it; in an autonomous run it is
   recorded as your decision under the approved policy, never as human
   review. Ask one
   grouped question where the intended exposure is a genuine choice.
5. Check that indispensable inputs (required values and the sample sheet
   with no default) can be supplied: by a principal, a default, or the
   default profile's config. `nf-splice validate` reports this as the
   runtime-parameters readiness dimension. Never widen a policy only to make
   a bundle ready: if nobody should supply a value, the default profile's
   config must set it, or it is a question for the person.

## Verification gates

- `validate_layer` on `inputs` reports no errors: the schema is valid, every
  reference resolves, every parameter has a policy.
- After the build, the runtime-parameters dimension is ready.

## Failure handling

- `undeclared_parameter` warnings: declare the parameter if a job may set
  it; otherwise it is a value the pipeline sets for itself.
- A re-import of a changed `nextflow_schema.json` (`nf-splice configure
  inputs --reimport`) is a three-way merge: new parameters arrive with `[]`
  and hidden; your policies are kept; overlaps are reported, never forced.

## Evidence reporting

For each non-default policy, cite the code that uses the parameter and why
that principal should control it.

## Safety boundaries

- Never drop a declared parameter because users should not see it.
- The runtime principal `agent` is a SPLICE platform role, not the assistant
  authoring this draft: never grant it because an AI wrote the policy.
- An assisting agent's access changes apply only through the person's
  approval of the stage.
