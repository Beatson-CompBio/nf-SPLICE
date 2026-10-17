# Components and container images

The components layer lists the modules your pipeline runs and the container
images they need, so the platform can fetch images before a job starts. It is
published as `components.json`.

- **Draft:** `.splice-local/drafts/components.draft.yaml`
- **Required:** a resolved container for every component that has one, and
  whether images must be directly downloadable

## Image references and image files

nf-splice keeps two things apart:

- **Image references** name an image in a registry, such as
  `quay.io/biocontainers/fastqc:0.12.1--hdfd78af_0`. Docker, Singularity and
  Apptainer pull them. They are not files you can download with a URL.
  nf-core modules often give one reference per runtime; nf-splice records
  each.
- **Image files** are `.sif` or `.img` files at an HTTPS address. nf-splice
  marks an image as downloadable only after it has downloaded the file,
  checked it and recorded its SHA-256 itself.

## 1. The seeded inventory

`nf-splice init` lists every module from `modules.json` (nf-core's `repos`
layout or a flat `items` list, plus local modules; or the `modules/`
folder when there is no `modules.json`) with:

- its tool name and version, from the module's metadata, its conda pin and
  its image tag (software version, conda build, image tag and module
  revision are kept apart);
- one container per distinct image, with each runtime's own reference.
  nf-core's `containerEngine in ['apptainer','singularity'] &&
  !task.ext.singularity_pull_docker_container ? A : B` gives `A` to
  Singularity and Apptainer and `B` to Docker; a `withName` override in the
  configuration replaces a module's directive;
- container IDs kept from an earlier `splice/components.json`, and its
  verified image files when nf-splice can vouch for them (see below);
- every process defined inline in a workflow file (common in custom
  pipelines), as a component of `type: workflow_process` whose `path` is
  the `.nf` file and `process` the process name (`path: main.nf`,
  `process: TILE_SLIDE`), with the container references of its own body.
  Module directories are `type: workflow_module` and have no `process`.

What cannot be resolved statically, such as a container built from
parameters at run time or conflicting versions, is listed under the
component's draft-only `unresolved` key, verbatim with its location, and
blocks publication until you resolve it:

```yaml
components:
  - id: modules__local__tool
    name: tool
    path: modules/local/tool
    namespace: local
    tool: {name: tool}
    evidence: [modules.json, modules/local/tool/main.nf:6]
    unresolved:
      - "unresolved_expression reference at modules/local/tool/main.nf:6"
```

Edit the file to fix it (add the container, set `tool.version`, then delete
the `unresolved` entry). A component whose code declares a container but
which names none is an error, `container_not_mapped`: set its
`container_id`, or record what stops it under `unresolved`. A module added to the pipeline after `init` is
reported as `module_not_listed`; add it, or leave it out on purpose. The
wizard's *Add all unambiguous* and `nf-splice configure components
--accept-detected` add such modules for you; they are never required.

## Software the default profile can use

Readiness checks each component against the default profile's container
engine. A component with a container needs a source for that engine (an
OCI reference serves Docker, Podman, Singularity and Apptainer; a verified
image file serves Singularity and Apptainer). A component that declares
only Conda packages cannot get them from a container engine, so under one
it blocks deployment readiness. A component that declares no container and
no Conda environment, such as a Groovy `exec:` process, runs with what the
execution host provides; readiness notes it.

## 2. Decide whether images must be downloadable

```bash
nf-splice configure components --require-downloadable true
```

- `true`: every image needs a verified image file. Publication is blocked
  until each one is verified.
- `false`: registry references are enough. The platform pulls images itself.

## 3. Verify image files

For each image that needs a file, give its container identifier (from
`nf-splice draft inspect components`) and the HTTPS address:

```bash
nf-splice containers verify container-0123456789ab https://images.example.org/fastqc-0.12.1.img
```

nf-splice downloads the file, checks that it really is a Singularity or
Apptainer image, computes its SHA-256 and records it. Checksums typed by hand
are not accepted.

For safety, verification only uses HTTPS, refuses addresses with credentials
and private or local network addresses (on every redirect too), limits the
download size and never leaves a partial file behind.

When `init` seeds the inventory from an earlier `splice/components.json`,
a container's verified image file is reused without downloading it only
when everything agrees: the lock vouches for that published file; the
lock's record of the verification (`distributions`) names the same
checksum, address and size; the distribution is consistent (HTTPS, a `sif`
or `img` file, the Nextflow cache name of these sources); and the
container's sources are unchanged. That is a *historical* verification: it
shows nf-splice checked the file once, never that it is reachable now.
Validation says so (`adopted_distribution`), the lock records it as
`historical`, and readiness notes it.

To check availability now, download the files again:

```bash
nf-splice containers reverify --approve-network
nf-splice containers reverify container-0123456789ab --approve-network
```

A file that still matches is recorded as a `fresh` verification. A file
whose checksum or size changed, or that cannot be downloaded, is reported
and left as it is; the command exits with status 2 so you can decide.

## Useful tools

Classify a reference without any network access:

```bash
nf-splice containers classify quay.io/biocontainers/fastqc:0.12.1--hdfd78af_0
```

Print the file name Nextflow's Singularity or Apptainer cache uses for an
image. Storing an image file under this name lets the platform pre-populate
the cache:

```bash
nf-splice containers cache-name biocontainers/fastqc:0.12.1--hdfd78af_0 --registry quay.io
```

## Deliver images to an object store

For sites that need image files positioned in advance, nf-splice can fetch
or build each image and upload it to an S3-compatible store you control.
Each step needs your explicit approval; nothing happens during `init`,
validation, builds or AI sessions.

1. See what each container needs, offline:

   ```bash
   nf-splice containers plan
   ```

   For the default profile's runtime, each container shows the source that
   runtime selects and the file name Nextflow's cache uses for *that*
   source: the Galaxy depot image
   `https://depot.galaxyproject.org/singularity/fastqc:0.12.1--hdfd78af_0`
   is cached as `depot.galaxyproject.org-singularity-fastqc-0.12.1--hdfd78af_0.img`,
   the Quay reference `quay.io/biocontainers/fastqc:0.12.1--hdfd78af_0` as
   `quay.io-biocontainers-fastqc-0.12.1--hdfd78af_0.img`.

2. Configure the store once. No secret is stored: credentials come from your
   normal AWS credential chain, or the named profile:

   ```bash
   python -m pip install "nf-splice[s3] @ git+https://github.com/Beatson-CompBio/nf-SPLICE.git"
   nf-splice containers store --endpoint https://s3.example.ac.uk --bucket images \
     --prefix splice/ --profile images --public-base-url https://images.example.ac.uk
   ```

3. Deliver, approving network access and upload explicitly:

   ```bash
   nf-splice containers deliver --approve-network --approve-upload
   ```

   Native images are downloaded and checked; OCI images are converted with an
   installed Apptainer or Singularity (never `sudo` or Docker). Each file is
   uploaded under its cache name unless the same content is already there; a
   different object is never overwritten. The upload is read back and
   compared, then downloaded from its public HTTPS address and recorded as a
   verified distribution. Without a public address nothing is recorded as
   downloadable.

Without credentials, network or Apptainer, the plan is still shown and the
draft is unchanged.

Field reference: [`components.json`](../schemas/components/README.md).
