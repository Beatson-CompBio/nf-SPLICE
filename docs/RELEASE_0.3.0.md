# nf-SPLICE 0.3.0 release record

**Status:** local work-in-progress branch `wip/nf-splice-v0.3.0`; not released.

## Feature ledger

Each row maps one 0.3.0 feature to the ADR(s) that govern it, the main
implementation files and the tests that verify it. `tests/test_adr_governance.py`
checks that every ADR exists, every path exists and every test file exists.

| Feature | ADR(s) | Implementation | Tests | Status |
| --- | --- | --- | --- | --- |
| Incremental ADR discipline and ledger | ADR-0023 | `docs/ARCHITECTURE_DECISIONS.md`, `docs/RELEASE_0.3.0.md` | `tests/test_adr_governance.py` | Current |
| Local-only workspace and staged-path guard | ADR-0023 | `.gitignore`, `scripts/dev-env.sh`, `scripts/check_staged_paths.py` | `tests/test_dev_workspace.py` | Current |
| Frozen 0.1.0 legacy fixtures | ADR-0023 | `tests/fixtures/legacy-0.1.0/` | `tests/test_legacy_fixtures.py` | Current |
| Five workflow-bundle contract families and release registry | ADR-0024 | `src/nf_splice/contracts/registry.py`, `src/nf_splice/contracts/data/registry.json`, `docs/schemas/` | `tests/test_contracts.py` | Current |
| Offline schema list/show/validate/check commands | ADR-0024 | `src/nf_splice/contracts/validation.py`, `src/nf_splice/contracts/compatibility.py`, `src/nf_splice/cli.py` | `tests/test_contracts.py` | Current |
| Package version 0.3.0 | ADR-0024 | `src/nf_splice/_version.py` | `tests/test_cli.py`, `tests/test_contracts.py` | Current |
| Reserved `manifest` vocabulary audit and glossary | ADR-0025 | `src/nf_splice/vocabulary.py`, `src/nf_splice/inspectors/identity.py`, `docs/GLOSSARY.md` | `tests/test_vocabulary.py` | Current |
| Restricted YAML 1.2 drafts with comment-preserving three-way patches | ADR-0026 | `src/nf_splice/drafts/` | `tests/test_drafts_infra.py` | Current |
| Job/sample/run output scopes with version-gated legacy migration | ADR-0027 | `src/nf_splice/domain/outputs.py`, `src/nf_splice/inspectors/outputs.py`, `src/nf_splice/runtime/analysis_output.py` | `tests/test_output_scopes.py` | Current |
| Free-text output categories and stages | ADR-0027 | `src/nf_splice/domain/outputs.py`, `src/nf_splice/renderers/outputs.py` | `tests/test_authoring.py`, `tests/test_output_scopes.py` | Current |
| Job metadata and deprecated --run-metadata alias | ADR-0027 | `src/nf_splice/runtime/analysis_output.py`, `src/nf_splice/cli.py` | `tests/test_output_scopes.py`, `tests/test_runtime.py` | Current |
| outputs.schema.json x-output-catalog as sole runtime catalogue | ADR-0028 | `src/nf_splice/renderers/outputs.py`, `src/nf_splice/runtime/analysis_output.py` | `tests/test_output_scopes.py`, `tests/test_output_contracts.py` | Current |
| Actor attribution and private audit store | ADR-0029 | `src/nf_splice/domain/audit.py`, `src/nf_splice/services/audit.py` | `tests/test_audit.py` | Current |
