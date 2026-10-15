# Containers: sources versus downloadable images

nf-splice keeps three concepts apart (ADR-0033):

1. **Source images**: native references per runtime, e.g. a Docker/OCI
   registry reference `quay.io/biocontainers/fastqc:0.12.1--hdfd78af_0` or a
   Singularity reference. A registry reference is not a file that `curl` can
   download.
2. **Runtime variants**: nf-core modules choose a Singularity/Apptainer or a
   Docker reference with `workflow.containerEngine`; both are recorded.
3. **Distributions**: a static `.sif`/`.img` file at an HTTPS URL that
   nf-splice has downloaded, signature-checked and hashed (SHA-256).

```bash
nf-splice containers classify quay.io/biocontainers/fastqc:0.12.1--hdfd78af_0
nf-splice containers cache-name biocontainers/fastqc:0.12.1--hdfd78af_0 --registry quay.io
nf-splice configure components --accept-detected --require-downloadable true
nf-splice containers verify container-0123456789ab https://images.example.org/x.img
```

## Trust and safety

Verification is explicit and network-bound: HTTPS only, no credentials in
URLs, no private, loopback, link-local, multicast or reserved addresses
(re-checked on every redirect), bounded streaming with a size quota,
temporary files and atomic placement. A distribution is accepted only when
its recorded checksum matches nf-splice's own verification; hand-entered
checksums are rejected. When `require_downloadable_images` is true, a
container without a verified distribution blocks publication.

## Nextflow cache names

`cache_filename` follows Nextflow's `SingularityCache.simpleName` rule:
strip the URI scheme, replace `:` and `/` with `-`, append `.img` (or keep
`.sif`); a registry-less reference is first prefixed with the configured
`singularity.registry`/`apptainer.registry`. Publishing the image under that
name lets a pre-seeded cache be reused. This rule is tested offline; a live
check runs only with `NF_SPLICE_NEXTFLOW_TESTS=1` and a local Nextflow.

## Materialising and uploading (opt-in)

The services `materialise_image` (pull/convert with an installed Apptainer or
Singularity, never sudo or Docker) and `publish_image` (upload) require
explicit approval. The target is operator configuration:

```bash
export NF_SPLICE_IMAGE_STORE_URL=https://store.example.org/images
export NF_SPLICE_IMAGE_STORE_ALLOWED_HOSTS=store.example.org
```

Uploads use the operator's own authenticated backend, reuse an identical
object by digest and never overwrite an object with a different checksum. No
organisation URL, account or credential is built into nf-splice or written
into a bundle. Uploading to the real SPLICE object store has not been tested
from this repository (it needs credentials and authorisation).
