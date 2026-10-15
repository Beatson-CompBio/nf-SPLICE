# Provenance and attribution

## RO-Crate

The repository-root `ro-crate-metadata.json` belongs to the pipeline
developer and is **never modified** by nf-splice (ADR-0035). nf-splice analyses
it for RO-Crate 1.1 structure, Workflow RO-Crate conventions, placeholders,
malformed identifiers and differences from the reviewed identity, then
records one reviewed strategy in `splice/drafts/ro-crate-metadata.draft.yaml`:

| Strategy | Published `splice/ro-crate-metadata.json` |
| --- | --- |
| `include` | Root bytes unchanged; allowed only without blocking differences. |
| `enriched` | Reviewed copy with corrected identity fields and credited authors. |
| `generated` | Minimal RO-Crate 1.1 + Workflow RO-Crate graph from reviewed identity. |

```bash
nf-splice configure provenance
nf-splice configure provenance --strategy enriched
```

`nf-core pipelines rocrate .` can generate a root file through an opt-in
adapter when none exists. The reviewed root hash is recorded; if the root file
changes later, the strategy must be reviewed again. Enriched and generated
crates contain a namespaced `#nf-splice` `SoftwareApplication` and a
`CreateAction` whose `endTime` is the approval time stored in the draft, so
rebuilding never changes bytes. Pipeline authors and integration reviewers are
different roles.

## Review attribution and privacy

Every review is a public-safe event (layer, action, pointers, origin, approval
status, actor and approver *labels*, tool version, content hashes, UTC time)
stored in `splice/drafts/.reviews/<layer>.review.json` (ADR-0029). Actor labels
come from `--actor`/`NF_SPLICE_ACTOR`, a CI identity or `unattributed`; Git
`user.name`/`user.email` are only an unconfirmed suggestion
(`nf-splice audit identity`). Contact details go only to the private local
audit store (`NF_SPLICE_AUDIT_DIR`, owner-only, outside the repository):

```bash
nf-splice audit identity
nf-splice audit show
```

Public maintainer contacts are opt-in (`maintainers` in `bundle.draft.yaml`)
and require `maintainers_publication_approved: true`. Git e-mail never enters a
published artefact.
