# Components and container images

The components layer lists the modules your pipeline runs and the container
images they need, so the platform can fetch images before a job starts. It is
published as `components.json`.

- **Draft:** `splice/drafts/components.draft.yaml`
- **Required:** a decision on every discovered module, and whether images
  must be directly downloadable

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

## 1. Review the discovered modules

Accept what was found in your modules:

```bash
nf-splice configure components --accept-detected
```

Or review one module, correcting its image or tool version:

```bash
nf-splice configure components \
  --set 'component:modules__local__multi.docker=quay.io/org/tool:1.0' \
  --set 'component:modules__local__multi.version=1.0'
```

You can set `docker`, `singularity`, `apptainer` and `version`, or reject a
module with `.action=reject` and `.reason=...`.

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

## Building and uploading images

Converting images and uploading them to object storage are available to
platform integrations through the Python API, and are not part of the
command-line workflow. Both need explicit approval, use an installed
Apptainer or Singularity (never `sudo` or Docker), and upload only to a
store the operator configures:

```bash
export NF_SPLICE_IMAGE_STORE_URL=https://store.example.org/images
export NF_SPLICE_IMAGE_STORE_ALLOWED_HOSTS=store.example.org
```

No storage address, account or credential is built into nf-splice or written
into a bundle.

Field reference: [`components.json`](../schemas/components/README.md).
