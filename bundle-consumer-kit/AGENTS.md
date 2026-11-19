# Working with SPLICE workflow bundles

This repository consumes SPLICE workflow bundles and job results. Read this
before writing code that parses, stores, displays or acts on them. The
detailed procedures are in the skills listed at the end; the formal
definitions are in `schemas/`; a complete real example is in `examples/`.

## What you are working with

- A **bundle** describes one released version of one workflow. It is a
  folder of JSON files, written by nf-splice and never edited by hand:
  `bundle.json` (entry point), `inputs.schema.json`, `outputs.schema.json`,
  `components.json`, `execution-profiles.json`, plus companion files
  (`configs/<profile>.config`, `ro-crate-metadata.json`, `outputs.yaml`,
  `nf-splice.lock.json`, `README.md`).
- An **`analysis_output.json`** is written once per completed **job** (one
  execution of a workflow version). It lists what that job published.
- Units: a **job** is a whole execution; a **sample** is a biological
  sample; a **run** is a platform file-level unit of one sample (for
  example one sequencing run) and always has a parent sample. A Nextflow
  execution is a job, never a run.

## Rules

1. **Read `bundle.json` first.** Follow its `schemas` and `files` maps to the
   other files; do not hard-code file names.
2. **Validate every file before using it**, against the definition for the
   exact contract revision it declares (`schema_id` and `schema_version`, or
   `x-splice-contract.id` and `.version` in the two JSON Schema documents).
   Reject revisions your code does not support; never "best-effort" parse
   an unknown revision.
3. **Use `pipeline.id` plus `pipeline.version` as the identity of a
   workflow version.** Check that every file repeats the same identity as
   `bundle.json`. A bundle can be rebuilt for the same workflow version
   (a newer nf-splice, a corrected review); detect that by comparing the
   lock's file hashes and handle it deliberately, never by silently
   overwriting what jobs already used.
4. **Keep the five version numbers apart:** contract revision
   (`schema_version`), workflow version (`pipeline.version`), output schema
   version (`x-output-catalog.analysis_output_schema_version`), generator
   version (`generated_by.version`) and lock format. They change for
   different reasons.
5. **Read output metadata only from `outputs.schema.json` →
   `x-output-catalog`.** `outputs.yaml` is a human-readable copy. There is no
   `outputs.json`.
6. **The output catalogue lists every output a workflow *may* publish**
   across its routes (alternative tools, optional steps). One job publishes
   a subset. An output type missing from a job is normal, not an error.
7. **Validate each `analysis_output.json` against the `outputs.schema.json`
   of the bundle for that job's workflow version** (JSON Schema draft-07),
   then link each record to its output type by `output_type` = `key`.
8. **Enforce `x-splice-access.editable_by` on the server.** It says who may
   set each input parameter (`user`, `platform`, `agent`; empty means
   fixed). `x-splice-ui` is presentation only and grants nothing.
9. **Treat `maintainers` as personal data**, published with consent. Apply
   your privacy rules to storing and showing it.
10. **Treat every string as untrusted text**: escape it when rendering, never
    execute it, and never build file paths from it without checking they stay
    inside the expected folder. Output `path` values are relative and never
    contain `..`; check anyway.
11. **An assay is not a modality.** `pipeline.assay_capabilities` lists the
    assays a workflow can process; group them by `modalities`, keep every
    path, and resolve `registered_code` against your deployment, reporting
    the ones it does not support. A bundle without assay capabilities is not
    ready for ingestion.
12. **Do not invent keys or values.** Every object in the contracts is
    closed (no other keys allowed) unless the schema says otherwise. If you
    need a field that is not there, it is not part of the contract; ask.

## Definitions and examples

| Need | Where |
| --- | --- |
| Formal definition of a family at a revision | `schemas/<family>/v<revision>/schema.json` |
| A minimal valid document of each family | `schemas/<family>/v<revision>/example.json` |
| A complete real bundle | `examples/bundle/` |
| A real job inventory for that bundle | `examples/analysis_output.json` |

Families: `bundle`, `inputs`, `outputs`, `components`,
`execution-profiles`. Family URIs are identifiers below
`https://schemas.splice-data.io/workflow-bundle/`, not web addresses;
validation is offline.

## Skills

| Skill | Use it for |
| --- | --- |
| `skills/splice-bundle-contracts/SKILL.md` | Structure, versions, identity and validation. Always. |
| `skills/splice-bundle-ingestion/SKILL.md` | Storing bundles and job results in a database. |
| `skills/splice-analysis-output/SKILL.md` | Reading and interpreting `analysis_output.json`. |
| `skills/splice-web-ui/SKILL.md` | Catalogue pages, launch forms and results views. |
| `skills/splice-job-launch/SKILL.md` | Turning a submission into a running job. |
