# Identity

The identity layer says what the pipeline is: its identifier, name, version,
description, authors and links. The platform uses it for listings, search and
citation. It is published as `bundle.json`.

- **Draft:** `splice/drafts/bundle.draft.yaml`
- **Required:** `id`, `name`, `version`, `repository_url`
- **Recommended:** `description`, `authors`, `licence`

## Where values come from

`nf-splice init` reads the Nextflow metadata in `nextflow.config`, the Git
remote, `CITATION.cff`, `README.md` and any root `ro-crate-metadata.json`.
Values all sources agree on are filled in. Conflicting values are left empty
for you to choose.

## Set values

```bash
nf-splice configure identity \
  --set id=rnaquant \
  --set description="Quantifies RNA-seq reads." \
  --set licence=MIT
```

List and object values are JSON:

```bash
nf-splice configure identity \
  --set 'authors=[{"name": "Ada Lovelace", "orcid": "https://orcid.org/0000-0002-1825-0097"}]'
```

Any field of the `pipeline` section can be set this way. The
[`bundle.json` reference](../schemas/bundle/README.md#pipeline) lists them
all. You can also edit `bundle.draft.yaml` directly.

## Confirm detected values

A detected value counts only after you confirm it. Confirm everything the
sources agree on:

```bash
nf-splice configure identity --accept-detected
```

Or confirm individual fields by their path in the draft:

```bash
nf-splice draft confirm bundle /pipeline/licence /pipeline/version
```

## Check the layer

```bash
nf-splice draft inspect bundle
```

```text
splice/drafts/bundle.draft.yaml: not ready
  error: /pipeline/id [missing_required] pipeline.id is required for an ingestion-ready bundle
  warning: /pipeline/description [recommended] a concise description is recommended for platform display
```

Errors block publication; warnings do not. nf-splice also checks for
placeholder text, invalid URLs and ORCID iDs, a release URL that does not
match the version, and a minimum Nextflow version that contradicts the
pipeline's own declaration.

## Authors and maintainers

- **Authors** are the people and organisations credited for the pipeline.
  People who only reviewed the SPLICE integration are not authors.
- **Maintainers** are public contacts. They are published only after you
  approve it, because they are personal data:

```bash
nf-splice configure identity --approve-maintainer-publication
```

Your Git name and e-mail address are never used for either.

## After changing identity

The other layers repeat the pipeline identity. When you change the name,
version or repository URL, update the inputs draft to match:

```bash
nf-splice draft sync-identity
```

`nf-splice status` reports `identity_mismatch` when this is needed.
