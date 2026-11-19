# Identity

The identity layer says what the pipeline is: its identifier, name, version,
description, authors and links. The platform uses it for listings, search and
citation. It is published as `bundle.json`.

- **Draft:** `.splice-local/drafts/bundle.draft.yaml`
- **Required:** `id`, `name`, `version`, `repository_url`
- **Recommended:** `description`, `authors`, `licence`

## Where values come from

`nf-splice init` imports only documented keys from structured sources: the
Nextflow metadata block in `nextflow.config`, `CITATION.cff`, the root
dataset of any `ro-crate-metadata.json`, the upstream remote recorded for an
integration copy, and an exact Git release tag (ADR-0069). It fills every
field the sources agree on. The README and other prose are never copied
into a field; a description longer than 600 characters is left for you to
summarise. ORCID iDs are checked and stored as `https://orcid.org/…`; one
with a wrong check digit is not imported. Every other authorable field is
in the draft too, as `null` or an empty list, so you can see and fill all of
them: `title`, `description`, `long_description`, `readme`, the URLs,
`authors`, `funders`, `citation`, `licence`, `licence_url`, the Nextflow
versions, `pipeline_type`, `keywords`, `released_at`, the assay
capabilities, and `maintainers`. Values the build owns (the file index,
`generated_by`, contract identifiers) are not in the draft.

Where sources disagree, for example a version in `nextflow.config` that
differs from `CITATION.cff`, the field stays empty and the conflict is
reported with every value and where it came from: write the right one.

## Edit the identity

Open `.splice-local/drafts/bundle.draft.yaml` and edit it; nested values
are ordinary YAML:

```yaml
pipeline:
  name: rnaquant
  version: 1.2.0
  licence: MIT
  authors:
    - name: Ada Lovelace
      orcid: https://orcid.org/0000-0002-1825-0097
    - name: Beatson Institute
      type: organization
  funders:
    - name: Cancer Research UK
      award_id: A12345
  citation:
    doi: 10.5281/zenodo.1234567
```

Or set fields from the command line (list and object values are JSON):

```bash
nf-splice configure identity --set licence=MIT --set released_at=2026-10-15T10:00:00Z
nf-splice configure identity \
  --set 'authors=[{"name": "Ada Lovelace", "orcid": "https://orcid.org/0000-0002-1825-0097"}]'
```

The [`bundle.json` reference](../schemas/bundle/README.md#pipeline) lists
every field; `nf-splice draft contract identity` prints the full structure.
A seeded value you leave as it is counts as yours: there is nothing to
confirm. `nf-splice draft confirm bundle /pipeline/version` remains
available if you want the review history to record that you checked one.

A licence and a release date (`released_at`) are also needed for a
standards-conformant RO-Crate; see [Provenance](provenance.md).

## With an assistant

In an AI-assisted session you can paste what you know in one go, for
example a paragraph from a grant or the README. The agent maps each fact to
its field, checks it against the repository, says which claims the
repository contradicts, and proposes all of it as one change for you to
approve. If you have nothing more to add, say so: optional fields stay
empty and the session moves on.

## Check the layer

```bash
nf-splice draft inspect bundle
```

```text
.splice-local/drafts/bundle.draft.yaml: not ready
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

## Copy the identity to the inputs draft

The inputs draft repeats the pipeline identity. Copy it once the identity
layer is ready, and again whenever you change the name, version or
repository URL:

```bash
nf-splice draft sync-identity
```

`nf-splice status` reports `identity_mismatch` when this is needed.
