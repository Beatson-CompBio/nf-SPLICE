# Export a ZIP archive

When the bundle validates, nf-splice can package it as a ZIP file and prove
the archive is intact.

```bash
nf-splice export --archive-scope bundle
nf-splice export --archive-scope pipeline --archive-output ~/Desktop/my-pipeline-splice.zip
```

| Scope | Contains |
| --- | --- |
| `bundle` | The `splice/` folder only |
| `pipeline` | The pipeline files plus `splice/`, at the archive root, with the reviewed RO-Crate as the root `ro-crate-metadata.json`: a standard Workflow RO-Crate. In a Git copy these are the files Git tracks. |

Neither scope ever contains `.splice-local/`, `.git/`, `work/`,
`results/`, caches, `.env` or other secrets files. A file that looks like it
contains a credential stops the export.

Without `--archive-output`, the archive is written to
`.splice-local/exports/<name>-<version>-splice-<scope>.zip`, where it cannot
end up inside itself. An existing archive is never replaced unless you add
`--overwrite`.

## How it is checked

```text
Wrote .splice-local/exports/rnaquant-1.2.0-splice-bundle.zip (9412 bytes)
SHA-256: 4c0f...
verified: 11 member(s) match their SHA-256 hashes
verified: the extracted bundle validates
verified: no .splice-local/ or .git/ content
```

nf-splice builds the archive only from a valid, up-to-date bundle, with
files in a fixed order and fixed timestamps, so the same bundle always gives
the same archive. It then reopens the archive, compares every file and its
hash with the files that were meant to be included, extracts it into a
temporary folder and validates the extracted bundle. For the pipeline
archive it also checks that the root `ro-crate-metadata.json` is the
published crate and that every local file it names is in the archive.

The archive's own SHA-256 is printed and returned, never written into the
archive: record it with the archive (the ingestion service does).

An archive is not a commit: committing (see [Working copy and Git](working-copy.md))
is a separate step.
