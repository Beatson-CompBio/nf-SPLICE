# Platform integration: pipelines with several assay capabilities

**Status:** proposal for the SPLICE platform team, raised by nf-splice 0.3.0
on 16 October 2026. Nothing here changes the platform; it needs the platform
team's agreement.

## The gap

A SPLICE bundle now declares any number of assay capabilities for one
pipeline (`bundle.json` → `pipeline.assay_capabilities`). The platform's
`Pipelines` model, in the sprint snapshot nf-splice was built from, links a
pipeline to **one** registration through `modality_id: Optional[int]`. A
pipeline that processes both poly(A) and total RNA-seq cannot be represented
without losing one.

## What a bundle provides

For each capability:

- `kind`: `registered_assay` or `vocabulary_assay`;
- `registered_code`: the registration's `modality_name` (for example
  `polya_rnaseq`), present only for registered assays;
- `assay`: the vocabulary entity (`entity_id`, `entity_type`, `label`);
- `assay_types`, `modality_subtypes`, `modalities`: the entities above it;
- `paths`: every path from the assay to a modality (entity ids).

And once per bundle, `assay_vocabulary`: the vocabulary snapshot's name,
identifier and content digest.

The bundle never contains platform accession identifiers, `modality_id`
values or the `current` flag: those belong to a deployment.

## Proposed platform changes

1. **A many-to-many association** between `Pipelines` and `Modalities`, for
   example `PipelineAssayCapabilities(pipeline_id, modality_id, entity_id,
   kind, created_from_bundle_digest)`, with a uniqueness constraint on
   `(pipeline_id, modality_id)` and on `(pipeline_id, entity_id)` for
   vocabulary-only capabilities. Keep `Pipelines.modality_id` during a
   transition, then retire it.
2. **Ingestion rules:**
   - Resolve each `registered_code` to the deployment's `Modalities` row by
     `modality_name`, and check that its `entity_id` equals
     `assay.entity_id`. A mismatch is an error, not a guess.
   - A capability with no registration in the deployment, or a registration
     whose `current` is false, is stored and reported as *declared but not
     ingestible here*. It is never dropped silently.
   - Check `assay_vocabulary.digest` against the deployment's vocabulary;
     report a different snapshot rather than reinterpret ids.
3. **API contract** for tools such as nf-splice, building on the existing
   `GET /modality-entities`, `GET /modality-relationships` and
   `GET /modalities`:
   - a documented, versioned response shape and authentication;
   - each registration's verified `accession_id`;
   - a vocabulary version or digest, so clients can pin and compare;
   - a clear split between the full vocabulary and the deployment's ingestible
     registrations.

## What nf-splice does already

- Packages the vocabulary snapshot with its provenance and digest; works
  offline.
- Has an API-backed source (`nf-splice catalogue compare --api URL`) that
  checks every field, refuses conflicts with the pinned snapshot unless they
  are explicitly reconciled, and reports additions as a stale snapshot.
- Accepts accession identifiers only from such an API, never from authors.

## Questions for the platform team

- Is `modality_name` the stable registration key across deployments, or
  should bundles also carry another identifier once the API provides one?
- Should vocabulary-only capabilities be stored, or only registered ones?
- Who allocates and publishes accession identifiers for registrations, and
  how do tools obtain them?
