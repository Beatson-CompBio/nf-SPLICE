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
| Reserved-word vocabulary audit and glossary | ADR-0025 | `src/nf_splice/vocabulary.py`, `src/nf_splice/inspectors/identity.py`, `docs/GLOSSARY.md` | `tests/test_vocabulary.py` | Current |
| Restricted YAML 1.2 drafts with comment-preserving three-way patches | ADR-0026 | `src/nf_splice/drafts/` | `tests/test_drafts_infra.py` | Current |
| Job/sample/run output scopes with version-gated legacy migration | ADR-0027 | `src/nf_splice/domain/outputs.py`, `src/nf_splice/inspectors/outputs.py`, `src/nf_splice/runtime/analysis_output.py` | `tests/test_output_scopes.py` | Current |
| Free-text output categories and stages | ADR-0027 | `src/nf_splice/domain/outputs.py`, `src/nf_splice/renderers/outputs.py` | `tests/test_output_discovery.py`, `tests/test_output_scopes.py` | Current |
| Job metadata and deprecated --run-metadata alias | ADR-0027 | `src/nf_splice/runtime/analysis_output.py`, `src/nf_splice/cli.py` | `tests/test_output_scopes.py`, `tests/test_runtime.py` | Current |
| outputs.schema.json x-output-catalog as sole runtime catalogue | ADR-0028 | `src/nf_splice/renderers/outputs.py`, `src/nf_splice/runtime/analysis_output.py` | `tests/test_output_scopes.py`, `tests/test_output_contracts.py` | Current |
| Actor attribution and private audit store | ADR-0029 | `src/nf_splice/domain/audit.py`, `src/nf_splice/services/audit.py` | `tests/test_audit.py` | Current |
| One authoritative YAML draft per layer; no nf-splice.yaml | ADR-0030 | `src/nf_splice/layers/base.py`, `src/nf_splice/drafts/` | `tests/test_layer_bundle.py`, `tests/test_layer_outputs.py` | Current |
| Rich identity in bundle.draft.yaml | ADR-0031 | `src/nf_splice/layers/bundle.py`, `src/nf_splice/domain/identity.py` | `tests/test_layer_bundle.py` | Current |
| Engine-neutral input contract and service-side permissions | ADR-0032 | `src/nf_splice/layers/inputs.py`, `src/nf_splice/services/input_policy.py` | `tests/test_layer_inputs.py` | Current |
| Container sources, verified distributions and cache naming | ADR-0033 | `src/nf_splice/layers/components.py`, `src/nf_splice/services/containers.py` | `tests/test_containers.py` | Current |
| Single reviewed default profile and generated configs | ADR-0034 | `src/nf_splice/layers/execution.py` | `tests/test_layer_execution.py` | Current |
| RO-Crate analysis, enrichment and generation | ADR-0035 | `src/nf_splice/layers/provenance.py` | `tests/test_layer_provenance.py` | Current |
| Per-layer promotion and recoverable bundle publication | ADR-0036 | `src/nf_splice/services/lifecycle.py`, `src/nf_splice/renderers/bundle_index.py` | `tests/test_lifecycle.py` | Current |
| Non-destructive 0.1.0 migration | ADR-0037 | `src/nf_splice/services/migration.py` | `tests/test_migration.py` | Current |
| File-first CLI | ADR-0030, ADR-0036 | `src/nf_splice/cli.py`, `src/nf_splice/services/workspace.py` | `tests/test_cli.py`, `tests/test_reference_workflow.py` | Current |
| Guided Textual wizard and CLI/TUI equivalence | ADR-0038 | `src/nf_splice/interfaces/tui/` | `tests/test_tui.py` | Current |
| Optional approval-gated agents (scripted + Claude providers) | ADR-0039 | `src/nf_splice/agents/`, `docs/AGENTS.md` | `tests/test_agents.py` | Current |
| Per-key contract references generated from packaged definitions | ADR-0024 | `scripts/generate_schema_docs.py`, `docs/schemas/fields.yaml`, `docs/CONTRACTS.md` | `tests/test_docs.py` | Current |
| User, platform and migration documentation with verified commands | ADR-0023, ADR-0027, ADR-0037 | `README.md`, `docs/USAGE.md`, `docs/CONTRACT_MIGRATION_0.3.0.md`, `docs/TUI.md`, `docs/CONTAINERS.md`, `docs/PROVENANCE.md` | `tests/test_docs.py` | Current |
| Reference validated bundle and incomplete draft fixtures | ADR-0030, ADR-0036 | `tests/fixtures/example-0.3.0/`, `tests/fixtures/incomplete-drafts-0.3.0/` | `tests/test_reference_fixtures.py` | Current |
| CI matrix 3.10-3.14, packaging and hygiene gates | ADR-0040 | `.github/workflows/ci.yml`, `pyproject.toml` | `tests/test_packaging.py` | Current |
