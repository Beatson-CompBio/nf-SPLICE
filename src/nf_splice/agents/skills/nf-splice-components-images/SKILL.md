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

1. `component_inventory`: a summary first (count, how many need a decision,
   every module name), then full rows a page at a time - each module's tool,
   versions, conda pins and every container reference with its runtime and
   source location. Page with `offset`/`limit` and filter with `name`; read a
   single module's whole detail with `name` set to it.
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
  no dangling `container_id`, no module that declares a container without
  one (`container_not_mapped`), every distribution verified by nf-splice.
- The deployment readiness dimension checks the default profile's engine
  against the containers' sources and required distributions. Singularity
  and Apptainer use their own sources, a verified image file or an OCI
  reference; Docker and Podman need an OCI reference. A component with
  only Conda packages blocks deployment under a container engine; one with
  no container and no Conda environment uses the execution host's software
  and is noted.

## Failure handling

- `module_not_listed`: a module in the repository is not in the inventory;
  add it or remove it on purpose.
- `unverified_distribution`: a checksum or URL was entered by hand; only
  `nf-splice containers verify`/`deliver` records one.
- `adopted_distribution` (warning): a verified image file was reused from
  the earlier bundle because the lock, its verification record, the
  distribution and the sources all agree. It is a historical verification:
  never say the image is available now. A person checks that with
  `nf-splice containers reverify --approve-network`.
- Processes defined inline in a workflow file are components too, with
  `type: workflow_process`, `path` the `.nf` file and `process` the process
  name (for example `path: main.nf`, `process: TILE_SLIDE`). Never put the
  process name into `path`.

## Evidence reporting

Cite each reference's location (module `main.nf:line` or the config
override) and say which runtime uses it.

## Safety boundaries

Never invent an image digest, checksum, S3 URL or "verified" status; a
registry reference is not a downloadable image file, and a `.sif` suffix is
not proof of one. Never fetch, convert or upload images yourself.
