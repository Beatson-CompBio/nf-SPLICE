# Provenance

The provenance layer publishes an RO-Crate: standard, machine-readable
metadata about the pipeline, its authors and how the bundle was made. It is
published as `ro-crate-metadata.json`.

- **Draft:** `.splice-local/drafts/provenance.draft.yaml`
- **Required:** a strategy

## 1. Analyse your RO-Crate

```bash
nf-splice configure provenance
```

nf-splice reads the `ro-crate-metadata.json` at the root of your repository,
if there is one. It checks the RO-Crate 1.1 structure and Workflow RO-Crate
conventions, and looks for placeholders, malformed identifiers and
differences from the reviewed identity.

## 2. Choose a strategy

```bash
nf-splice configure provenance --strategy enriched
```

| Strategy | What is published |
| --- | --- |
| `include` | Your root RO-Crate, unchanged. Allowed only when it has no blocking differences. |
| `enriched` | A reviewed copy of your RO-Crate with corrected identity and credited authors. |
| `generated` | A minimal RO-Crate built from the reviewed identity, for repositories without one. |

Your root `ro-crate-metadata.json` is never modified. Enriched and generated
crates record nf-splice as the creating software, with the review time, so
rebuilding produces identical bytes.

If your root RO-Crate changes later, the strategy must be reviewed again.

To create a root RO-Crate for an nf-core pipeline, you can use
`nf-core pipelines rocrate .`.

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
