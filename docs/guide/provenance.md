# Provenance

The provenance layer publishes an RO-Crate: standard, machine-readable
metadata about the pipeline, its authors, its files and the SPLICE bundle.
It is published as `splice/ro-crate-metadata.json`, which the ingestion
service can store and offer for download with the pipeline version.

- **Draft:** `.splice-local/drafts/provenance.draft.yaml`, holding the
  RO-Crate graph

## The seeded graph

`nf-splice init` writes the graph for you:

- if your repository has a parseable root `ro-crate-metadata.json`, a copy of
  it (`origin: adopted`, with its hash under `source`). The original is never
  modified;
- otherwise a Workflow RO-Crate built from the identity draft (`origin:
  generated`): the root dataset, the main workflow file, Nextflow as its
  language and the credited authors.

The graph's IDs are relative to the pipeline directory (`main.nf`,
`nextflow.config`). Edit it like any other draft:

```yaml
origin: authored
source: null
crate:
  '@context': https://w3id.org/ro/crate/1.1/context
  '@graph':
    - '@id': ro-crate-metadata.json
      '@type': CreativeWork
      about: {'@id': ./}
      conformsTo:
        - {'@id': https://w3id.org/ro/crate/1.1}
        - {'@id': https://w3id.org/workflowhub/workflow-ro-crate/1.0}
    - '@id': ./
      '@type': Dataset
      name: rnaquant
      description: Quantifies RNA-seq reads.
      license: MIT
      datePublished: 2026-10-15
      mainEntity: {'@id': main.nf}
      creator: [{'@id': https://orcid.org/0000-0002-1825-0097}]
```

RO-Crate 1.1 requires the root dataset to have a name, description, licence
and `datePublished`. When the identity has a `licence` and `released_at`
they are used; otherwise validation warns, and the bundle is not ready for
ingestion until you supply them. They are never guessed.

## Checks

```bash
nf-splice configure provenance
nf-splice draft validate provenance
```

nf-splice checks the RO-Crate structure and Workflow RO-Crate conventions,
placeholders and malformed identifiers, differences from the reviewed
identity (a stale version is an error), and whether your root crate changed
since the graph was based on it.

```bash
nf-splice draft check-crate
nf-splice draft check-crate --allow external_tools --allow network
```

`draft check-crate` says whether to keep the graph, adopt your root crate,
correct a copy of it or regenerate one, and checks the draft graph as it
would be published. It reports two results separately:

| Result | What ran | Statuses |
| --- | --- | --- |
| Structural checks | nf-splice's own RO-Crate structure and identity checks, always, offline | `passed`, `failed` |
| Standards | the Workflow RO-Crate 1.0 profile with [rocrate-validator](https://github.com/crs4/rocrate-validator), installed by you, only with `--allow external_tools` (offline without `--allow network`) | `passed`, `failed`, `not_run`, `not_applicable` |

When the standards check did not run, the output says that only the
structural checks are established; a structural pass is never a standards
pass. `nf-splice assess --allow external_tools --allow network` runs the
same validator on the published archive layout.

## Shortcuts

| Command | What it does to the draft |
| --- | --- |
| `nf-splice configure provenance --strategy adopt` | Copy the current root crate in |
| `nf-splice configure provenance --strategy correct` | Copy it in, corrected from the reviewed identity |
| `nf-splice configure provenance --strategy regenerate` | Rebuild the graph from the reviewed identity |
| `nf-splice configure provenance --with-nf-core` | Use `nf-core pipelines rocrate` (installed by you) |

The nf-core generator runs on an isolated copy below `.splice-local/tmp/`,
with no terminal input and its update check disabled, so it cannot change
your pipeline or wait for a prompt. Its output is a candidate: the reviewed
identity is applied, and for a pipeline that is not an nf-core pipeline any
nf-co.re hosting claim is removed. It is a generator, not a validator.

The earlier names `include`, `enriched` and `generated` are still read.

In AI sessions the agent does the same through its tools:
`analyse_ro_crate` (the assessment and recommendation), `provenance_strategy`
(adopt, correct or regenerate), `generate_ro_crate` (nf-core's generator on
an isolated copy; needs `--allow external_tools --allow network`, and
nf-splice never installs nf-core) and `validate_ro_crate` (the two checks
above). Without the tools or permissions, the agent reports what it could
not run instead of claiming it.

Shortcuts that record a review add nf-splice and the reviewer to the graph
as a `CreateAction` with the time you ran them, so rebuilding produces
identical bytes.

## What is published

Building adds the `splice/` bundle to the graph: a Dataset `splice/` that is
about the main workflow and has a File entry for each published artefact
(`bundle.json`, the input and output schemas, components, profiles and their
configs). No checksums are added, so the crate and `bundle.json` (which
records the crate's hash) never depend on each other.

The complete-pipeline archive (`nf-splice export --archive-scope pipeline`)
places the same crate at the archive's root, where RO-Crate tools look for
it, so the archive is a standard Workflow RO-Crate. A root crate of your own
is replaced in the archive by the reviewed one; your file is untouched. The
bundle-only archive holds `splice/` and describes a pipeline it does not
contain. Neither archive contains its own checksum or an invented download
address: the ingestion service records where it stores them.

## Attribution and privacy

Every review decision is recorded with:

- an **actor label**, from `--actor`, `NF_SPLICE_ACTOR` or the CI identity,
  otherwise `unattributed`;
- the layer, action, fields, origin (command line, wizard, assistant) and time.

These records are stored in `.splice-local/reviews/` and contain no contact
details. Your Git name and e-mail address are offered only as a suggestion
and are never published. Contact details, if you choose to record them, go
to a private audit store outside the repository (`NF_SPLICE_AUDIT_DIR`,
readable only by you):

```bash
nf-splice audit identity
nf-splice audit show
```

Public maintainer contacts are opt-in. See
[Identity](identity.md#authors-and-maintainers).
