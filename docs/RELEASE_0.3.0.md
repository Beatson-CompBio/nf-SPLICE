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
