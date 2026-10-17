---
name: nf-splice-provenance
description: Author the pipeline's RO-Crate graph in provenance.draft.yaml - adopt or correct the repository-root crate or build one from the identity, keep attribution honest, and understand the canonical splice/ro-crate-metadata.json, the archive-root descriptor and standards validation. Use at the provenance stage.
---

# nf-splice provenance (RO-Crate)

## When to use

Use this skill when authoring or reviewing
`.splice-local/drafts/provenance.draft.yaml`, comparing it with the
repository-root crate, or explaining what the archives contain.

## Prerequisites

- The identity layer is ready.
- `nf-splice init` seeded the graph: a copy of a parseable root
  `ro-crate-metadata.json` (`origin: adopted`, the original never changed)
  or a Workflow RO-Crate built from the identity (`origin: generated`).

## Workflow

1. `read_draft` and `analyse_ro_crate`: structure, the root dataset's
   RO-Crate 1.1 properties (name, description, licence, `datePublished`),
   the main workflow, and differences from the reviewed identity.
2. Correct and extend the graph as one revision (`replace_draft` of
   `/crate`). Data-entity IDs are relative to the pipeline directory.
   Distinguish the workflow's authors, the integration reviewer and
   nf-splice as software; reuse the reviewed identity rather than asking
   again.
3. nf-core's generator (`nf-core pipelines rocrate`) is a person's opt-in
   command (`nf-splice configure provenance --with-nf-core`), run on an
   isolated copy; its output is a candidate, and nf-co.re hosting claims are
   removed for pipelines that are not nf-core's. It is not a validator.
4. nf-splice adds the `splice/` bundle Dataset and its files when it builds;
   do not author them. No checksum of the bundle or the archive is put in
   the crate.
5. Archives: the complete-pipeline ZIP has the pipeline at its root and the
   published crate as its root `ro-crate-metadata.json` (a developer's own
   root crate is replaced in the archive only). The bundle-only ZIP holds
   `splice/` and is not a self-contained Workflow RO-Crate.

## Verification gates

- `validate_layer` on `provenance` reports no errors; warnings name missing
  RO-Crate 1.1 root properties.
- The provenance readiness dimension blocks while those properties are
  missing or the crate disagrees with the bundle's identity.
- Standards validation: `nf-splice assess --allow external_tools --allow
  network` runs `rocrate-validator` on the archive layout when installed.

## Failure handling

- `stale_value`: the graph disagrees with the reviewed identity; correct it.
- `source_changed`: the root crate changed since the graph was based on it;
  compare them.
- `root_property`: set the missing licence or publication date from evidence,
  or ask; never guess.

## Evidence reporting

Cite the root crate, the identity fields and the files each entity names.

## Safety boundaries

Never edit the repository-root crate, never invent ORCIDs, licences, DOIs or
download URLs, and never claim a private S3 location is publicly
downloadable: the ingestion service records the eventual location.
