---
name: nf-splice-components-images
description: Author the component inventory - every module, its tool and version, and the real container reference for each runtime (Docker/OCI versus Singularity/Apptainer) - resolve nf-core container ternaries and unresolved expressions from the source, and plan image delivery without inventing checksums or URLs. Use at the components stage.
---

# nf-splice components and container images

## When to use

Use this skill when authoring or reviewing
`.splice-local/drafts/components.draft.yaml`, investigating container
references, or planning downloadable images for an HPC deployment.

## Prerequisites

- `nf-splice init` seeded every module from `modules.json` (nf-core's
  `repos` layout or a flat `items` list, plus local modules) or from
  `modules/` on disk, with containers deduplicated and IDs kept from an
  earlier `splice/components.json`. A component's draft-only `unresolved`
  list says what still needs a decision.

## Workflow

1. `component_inventory`: each module's tool, versions, conda pins and every
   container reference with its runtime and source location.
2. nf-core's `containerEngine in ['apptainer','singularity'] &&
   !task.ext.singularity_pull_docker_container ? A : B` selects `A` for
   Singularity/Apptainer and `B` for Docker and other OCI engines. Keep
   each runtime's own reference. A `withName` override in configuration
   replaces the module's directive for that process.
3. For each `unresolved` item, read the module and the configs that touch it.
   Map a dynamic expression only when the code shows its values; otherwise
   leave it with a precise reason.
4. Versions: a tool's software version, its conda build, the image tag and
   digest and the module revision are different things. Resolve conflicts
   from evidence (the conda pin, the tag's version part) and write
   `tool.version`; remove the item from `unresolved`.
5. `require_downloadable_images` is a deployment decision: true when the
   site needs pre-positioned image files. Never set it false to hide a
   missing image.
6. Image delivery is a person's command, never an agent's:
   `nf-splice containers plan` (offline) shows, per container, the source
   the runtime selects and the file name Nextflow's cache uses for it;
   `nf-splice containers deliver --approve-network --approve-upload` fetches
   or converts, uploads to the configured S3-compatible store, reads it back
   and records the verified distribution.

## Verification gates

- `validate_layer` on `components` reports no errors: no unresolved item,
  no dangling `container_id`, every distribution verified by nf-splice.
- The deployment readiness dimension checks the default profile's engine
  against the containers' sources and required distributions.

## Failure handling

- `module_not_listed`: a module in the repository is not in the inventory;
  add it or remove it on purpose.
- `unverified_distribution`: a checksum or URL was entered by hand; only
  `nf-splice containers verify`/`deliver` records one.

## Evidence reporting

Cite each reference's location (module `main.nf:line` or the config
override) and say which runtime uses it.

## Safety boundaries

Never invent an image digest, checksum, S3 URL or "verified" status; a
registry reference is not a downloadable image file, and a `.sif` suffix is
not proof of one. Never fetch, convert or upload images yourself.
