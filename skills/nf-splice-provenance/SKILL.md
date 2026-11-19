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

1. `read_draft`, `read_draft` of the identity (`bundle`) and
   `analyse_ro_crate`: the repository's crate and the authored graph, their
   findings (structure, the root dataset's RO-Crate 1.1 properties: name,
   description, licence, `datePublished`; the main workflow; differences
   from the reviewed identity), a recommendation to `keep`, `adopt`,
   `correct` or `regenerate` with its reasons, and whether nf-core's
   generator and `rocrate-validator` are installed and applicable.
   Decide yourself; the recommendation is a starting point.
2. Correct and extend the graph as one revision (`replace_draft` of
   `/crate`). Data-entity IDs are relative to the pipeline directory.
   Distinguish the workflow's authors, the integration reviewer and
   nf-splice as software; reuse the reviewed identity rather than asking
   again.
3. To start afresh: `provenance_strategy` with `adopt` (copy the root
   crate), `correct` (a copy corrected from the identity) or `regenerate`
   (from the identity). `generate_ro_crate` runs nf-core's generator
   (`nf-core pipelines rocrate`) on an isolated copy of the pipeline, when
   nf-core is installed and the session grants `external_tools` and
   `network`; nf-splice never installs it. Its output replaces the draft's
   crate after identity values are applied and nf-co.re hosting claims are
   removed for pipelines that are not nf-core's. It is a generator, not a
   validator: inspect and correct its graph. People run the same with
   `nf-splice configure provenance --strategy ...` or `--with-nf-core`.
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
- `validate_ro_crate` (or `nf-splice draft check-crate`) checks the draft
  graph as it would be published and reports two results apart:
  nf-splice's structural checks (`passed`/`failed`) and the Workflow
  RO-Crate 1.0 standards profile with `rocrate-validator` (`passed`,
  `failed`, `not_run`, `not_applicable`; it runs only when installed and
  `external_tools` is granted, offline without `network`). Report exactly
  which ran: a structural pass is never a standards pass. When a tool or a
  permission is missing, say so in your review's uncertainties, or record a
  blocker if the decision depends on it.

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
