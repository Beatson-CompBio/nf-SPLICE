# Frozen nf-splice 0.1.0 legacy fixture

**Not for ingestion.** This directory freezes the exact bytes produced by the
unchanged nf-splice 0.1.0 code (commit `9ad15c1`) for a small realistic
pipeline, so that 0.3.0 compatibility adapters and migrations can be tested
against genuine historical artefacts.

- `repository/` — pipeline sources plus the complete 0.1.0 `splice/` bundle,
  including the monolithic `splice/nf-splice.yaml` (authoring schema `1.0`),
  `bundle.json` (bundle schema `1.0`), lock schema `1.0`, and an
  `outputs.schema.json` using the legacy `run` (workflow-wide), `sample` and
  `library` output scopes.
- `completed-job/` — one completed job's publish directory, the legacy
  `--run-metadata` input and the resulting legacy `analysis_output.json`
  (with the machine-specific `publish_directory` value removed).
- `SHA256SUMS` — byte checksums verified by `tests/test_legacy_fixtures.py`.
  Never regenerate these files; a changed checksum means a fixture was
  accidentally edited.
