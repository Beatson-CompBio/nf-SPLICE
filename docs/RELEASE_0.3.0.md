# nf-SPLICE 0.3.0 release record

**Status:** local work-in-progress branch `wip/nf-splice-v0.3.0`; not released.
Nothing has been pushed, merged, tagged or published.

| Item | Value |
| --- | --- |
| Branch | `wip/nf-splice-v0.3.0` (local only, no upstream) |
| Base commit | `9ad15c1` (`main` at branch creation) |
| Package version | 0.3.0 |
| Contract revision | 0.3.0 for all five workflow-bundle families |

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
| Task-based user guide, contributor guide and migration notes with verified commands | ADR-0023, ADR-0027, ADR-0037 | `README.md`, `CONTRIBUTING.md`, `docs/USAGE.md`, `docs/guide/`, `docs/CONTRACT_MIGRATION_0.3.0.md` | `tests/test_docs.py` | Current |
| Generated command reference | ADR-0023 | `scripts/generate_cli_docs.py`, `docs/reference/cli.md` | `tests/test_docs.py` | Current |
| Integrator overview, `analysis_output.json` and companion-file references | ADR-0024, ADR-0028 | `docs/CONTRACTS.md`, `docs/schemas/README.md`, `docs/schemas/analysis-output.md`, `docs/schemas/companion-files.md` | `tests/test_docs.py` | Current |
| Reference validated bundle and incomplete draft fixtures | ADR-0030, ADR-0036 | `tests/fixtures/example-0.3.0/`, `tests/fixtures/incomplete-drafts-0.3.0/` | `tests/test_reference_fixtures.py` | Current |
| CI matrix 3.10-3.14, packaging and hygiene gates | ADR-0040 | `.github/workflows/ci.yml`, `pyproject.toml` | `tests/test_packaging.py` | Current |

## Changelog

### Breaking

- New integrations no longer have an authoritative `nf-splice.yaml`. Each
  layer has one YAML draft under `splice/drafts/` (plus native `.config`
  drafts for generated execution profiles). The draft is the source of truth
  and you can edit it directly (ADR-0030).
- The public output contract is `outputs.schema.json` with `x-output-catalog`
  as the runtime's only catalogue. There is no `outputs.json` (ADR-0028).
- Output scopes are `job`, `sample` and `run`. Legacy `run` means `job`,
  legacy `sample` stays `sample`, and legacy `library` becomes `run` only after
  an explicit, versioned mapping (ADR-0027).
- `--run-metadata` is a deprecated alias of `--job-metadata`.
- The Textual dashboard is replaced by a guided wizard (ADR-0038).
- Lock format 2.0 records the contract URIs, per-file hashes and layer owners.

### Added

- Five independently versioned contract families with a packaged registry
  and the offline `nf-splice schema list|show|validate|check` commands
  (ADR-0024).
- Rich identity in `bundle.draft.yaml` (ADR-0031), an engine-neutral input
  contract with per-parameter access (ADR-0032), container sources, variants
  and verified distributions (ADR-0033), one reviewed default execution
  profile with adopted or generated configs (ADR-0034), and RO-Crate review,
  enrichment and generation (ADR-0035).
- Per-layer promotion and transactional bundle publication with journal,
  backup and `recover` (ADR-0036). Non-destructive 0.1.0 migration
  (ADR-0037).
- Public review events with actor labels, plus a private local audit store
  for contact details (ADR-0029).
- Optional, approval-gated agents: an offline scripted provider and a
  least-privilege Claude Agent SDK provider behind the `[claude]` extra
  (ADR-0039).
- CI matrix for Python 3.10-3.14, nf-core 4.0.2 coexistence, packaging
  checks and staged-path hygiene gates (ADR-0040).

### Fixed during this release

- `558a18d`: assignments inside a single-line Nextflow metadata block
  (`{ name = 'x'; version = 'y' }`) are now read, with correct evidence line
  numbers.

## Migration notes

See [CONTRACT_MIGRATION_0.3.0.md](CONTRACT_MIGRATION_0.3.0.md) for field
mappings and the ingestion/DEX roll-out order. Migration is preview first and
never deletes its source:

```bash
nf-splice migrate drafts
nf-splice migrate drafts --apply
```

`nf-splice migrate-state` (preview, then `--apply`) separately moves legacy
repository-root state files into `splice/`.

Ambiguous or unversioned scope conversions block instead of guessing.

## Functional acceptance checklist (specification section 17)

Each "Done" item is backed by the ledger tests above and by the scenario
tests listed in the next section. "Partial" items are complete offline and
are only waiting on an external dependency, named in the Notes column.

| Area | Requirement | State | Evidence / notes |
| --- | --- | --- | --- |
| Contract | Package reports 0.3.0 consistently | Done | `test_cli.py`, `nf-splice --version` on 3.10, 3.11 and 3.14 |
| Contract | Exactly five families, including `/workflow-bundle/bundle`, versioned, registered, documented key by key | Done | `test_contracts.py`, `test_scenarios.py::test_s10_*`, `docs/schemas/` |
| Contract | Compatibility checks, old fixtures, migration adapters | Done | `test_contracts.py`, `test_legacy_fixtures.py`, `test_migration.py` |
| Contract | Rich `bundle.json` identity | Done | `test_layer_bundle.py` |
| Contract | Consistent pipeline/generator/version provenance in every contract | Done | `test_lifecycle.py`, `test_scenarios.py::test_s10_*` |
| Contract | No `outputs.json`; `x-output-catalog` drives runtime | Done | `test_output_contracts.py`, `test_s10_*` |
| Contract | Free-text output categories and stages | Done | `test_output_discovery.py` |
| Contract | Engine-neutral 2020-12 input contract, lossless nf-schema import, no duplicated parameters | Done | `test_layer_inputs.py` |
| Contract | Service-level input permissions, presentation and engine mapping | Done | `test_layer_inputs.py` |
| Components | OCI source, Apptainer/Singularity source and downloadable image kept distinct | Done | `test_containers.py` |
| Components | HTTPS image validation, SHA-256, local conversion, cache naming, opt-in upload | Partial | Offline behaviour is tested. Live Nextflow cache naming and the real object store are not verified (decisions 3 and 4) |
| Components | IDs survive migration or have explicit mappings | Done | `test_migration.py` |
| Execution | At most one reviewed default; safe Slurm candidate | Done | `test_layer_execution.py` |
| Execution | Adopted and generated `.config` routes with required section headings | Done | `test_layer_execution.py` |
| Provenance | RO-Crate validation, reviewed enrichment/generation, root preserved | Done | `test_layer_provenance.py` |
| Provenance | Public contacts separated from private local identity | Done | `test_audit.py` |
| Workflow | One YAML draft per contract; only `outputs.draft.yaml` for outputs; no authoritative `nf-splice.yaml` | Done | `test_layer_outputs.py`, `test_reference_workflow.py` |
| Workflow | External edits detected, diffed, validated and promoted without import; no lost concurrent edits | Done | `test_drafts_infra.py`, `test_s03_*`, `test_s04_*` |
| Workflow | Final names, no draft markers, lock/ownership checks | Done | `test_lifecycle.py` |
| Workflow | Interrupted or failed builds never look complete | Done | `test_lifecycle.py`, `test_s09_*` |
| UI | Wizard covers every layer and the draft/final lifecycle | Done | `test_tui.py` |
| UI | Navigation, inline validation, progress, resume, CLI equivalence, keyboard review | Done | `test_tui.py` (CLI/TUI equivalence gate) |
| AI | No AI dependency for manual use; offline compilation and validation | Done | `test_s08_*` (SDK import blocked, sockets disabled) |
| AI | Claude SDK behind a provider-neutral, approval-gated, least-privilege interface | Done | `test_agents.py` |
| AI | Manual and AI suggestions interchangeable; only services apply changes | Done | `test_s03_*`, `test_agents.py` |
| AI | Provider code isolated for future adapters | Done | `src/nf_splice/agents/providers/` |
| Release | Existing regression tests pass | Done | 190 passed, 2 skipped |
| Release | Scenarios S01-S15 pass offline | Done | See the scenario table below |
| Release | Python 3.10-3.14, nf-core coexistence, pytest, ruff, mypy, packaging, installed CLI | Partial | 3.10, 3.11 and 3.14 run locally. 3.12 and 3.13 run only in the CI matrix, which has not been run (nothing pushed) |
| Release | Golden files and snapshots committed | Done | `tests/snapshots/tui/`, `docs/schemas/*/v0.3.0/` |
| Release | Bundle family URI exact; reserved word only in the upstream parser | Done | `test_vocabulary.py`, `test_s13_*`, `test_docs.py` |
| Release | Scopes exactly job/sample/run with mixed granularity and versioned migration | Done | `test_output_scopes.py` |
| Release | ADR register, statuses, supersession and ledger complete | Done | `test_adr_governance.py` |
| Release | Docs complete; every documented command exists | Done | `test_docs.py` |
| Release | No private data, credentials, local paths or drafts in published files | Done | `test_audit.py`, `test_lifecycle.py` |
| Hygiene | Single in-place clone; local-only branch; no external worktrees | Done | `git worktree list` shows only this clone |
| Hygiene | Anchored `/.nf-splice-local/` rule confirmed by `git check-ignore` | Done | `.gitignore:225:/.nf-splice-local/` |
| Hygiene | All temporary, cache, report and session files inside `.nf-splice-local/` | Done | `scripts/dev-env.sh`, `test_dev_workspace.py` |
| Hygiene | Staged-path guard rejects ignored paths, even forcibly staged | Done | `scripts/check_staged_paths.py`, `scripts/pre-commit`, CI `guard` job |
| Hygiene | No push, merge, tag or publication | Done | No upstream, no remote branch contains `HEAD`, no tags |

## Scenario coverage (specification section 15.2)

| Scenario | Test(s) |
| --- | --- |
| S01 manual CLI | `test_reference_workflow.py` |
| S02 Textual, identical to CLI | `test_tui.py::test_cli_and_tui_produce_identical_drafts_and_bundles` |
| S03 manual + AI + external edit | `test_scenarios.py::test_s03_manual_and_ai_work_are_interchangeable`, `test_agents.py` |
| S04 resume and external mutation | `test_scenarios.py::test_s04_*`, `test_tui.py`, `test_drafts_infra.py`, `test_lifecycle.py` (drift) |
| S05 legacy migration | `test_migration.py`, `test_legacy_fixtures.py` |
| S06 container hazard | `test_containers.py` (offline HTTPS fixture, SSRF and integrity guards) |
| S07 RO-Crate drift | `test_layer_provenance.py::test_stale_crate_blocks_inclusion_and_reviewed_enrichment_is_stable` |
| S08 no AI, no network | `test_scenarios.py::test_s08_full_workflow_without_ai_or_network` |
| S09 failure injection | `test_scenarios.py::test_s09_*`, `test_lifecycle.py::test_interrupted_publication_is_recovered_explicitly`, `test_drafts_infra.py` |
| S10 five-contract JSON consumer | `test_scenarios.py::test_s10_json_consumers_need_only_the_five_contracts` |
| S11 Python and packaging | `test_packaging.py`, local 3.10/3.11/3.14 wheel runs, CI matrix |
| S12 multi-job separation | `test_output_scopes.py::test_two_jobs_produce_separate_documents_without_static_mutation` |
| S13 terminology | `test_scenarios.py::test_s13_*`, `test_vocabulary.py`, `test_docs.py` |
| S14 scope migration | `test_output_scopes.py` (versioned legacy scopes, unmapped `library` blocks) |
| S15 ADR traceability | `test_adr_governance.py` |

S09 does not simulate a full disk. Instead it injects a write failure through
a read-only target, and `test_lifecycle.py` tests interrupted publication
through the `replace_file` hook. Both paths use the same staging and recovery
code.

## Tests and commands run

All commands ran inside the clone with `. scripts/dev-env.sh`, which sends
every cache, temporary file, report and session under `.nf-splice-local/`.

| Command | Result |
| --- | --- |
| `scripts/run-checks.sh` (uv pip check, pytest, ruff check, ruff format --check, mypy, `nf-splice --version`, staged-path guard) | exit 0: 190 passed, 2 skipped; ruff clean; 127 files formatted; mypy clean on 120 files; `nf-splice 0.3.0` |
| `python -m build --outdir .nf-splice-local/reports/dist` | sdist and wheel built |
| `python scripts/generate_schema_docs.py --check` | exit 0 |
| Wheel `[dev]` installed into new Python 3.11.16 and 3.14.7 venvs; suite run against the installed package | 190 passed, 2 skipped on each; `uv pip check` compatible |
| Wheel plus `nf-core==4.0.2` in a new Python 3.10.21 venv | `uv pip check` compatible; `nf-splice 0.3.0` and `nf-core 4.0.2` both run |

The two skipped tests are opt-in by design:

- The `nextflow` marker test needs a Nextflow install. None is installed on
  this machine.
- The `live_agent` marker test needs `NF_SPLICE_LIVE_AGENT=1` and approved
  Claude credentials.

## Known platform dependencies and blockers

- **Nextflow** is not installed here. The Singularity/Apptainer cache file
  name rule is implemented from the published Nextflow rule and covered by
  unit tests. The opt-in `nextflow` test that checks it against a real
  runtime has not run.
- **Docker, Apptainer and Singularity** are not installed here. Local image
  conversion is implemented and tested with fakes only.
- **SPLICE object store**: uploads use the operator's own authenticated
  backend. They were not tested against the real bucket, because that needs
  credentials and explicit authorisation.
- **Ingestion/DEX code** is not in this repository. The components shape and
  the migration order are published as schemas, examples and fixtures, and the
  downstream adapter work is listed in the migration guide.
- **CI** has never run, because nothing has been pushed. Python 3.12 and 3.13
  are covered only by the CI matrix.
- **Claude Agent SDK**: the provider is tested offline against a fake SDK.
  Live use needs an organisation-approved setup.

## Decisions to flag for review (specification section 18)

1. **Schema family histories.** All five families start at revision 0.3.0 for
   tool 0.3.0. Legacy `1.0`/`1.0.0` documents are recognised as unregistered
   legacy inputs, and the migration adapters handle them. The release
   registry maps each tool release to all five family revisions separately,
   so a future release must add a mapping row even when no family changes.
   The runtime `analysis_output.json` schema keeps its own semantics and is
   not a sixth bundle family.
2. **Components JSON shape.** `id`, `type` and `uri` are kept. Containers
   gain `source_images` per runtime, runtime variants and verified
   distributions (URL, SHA-256, cache file name). The ingestion code is not
   available here, so this needs an ingestion-side adapter, as described in
   the migration guide.
3. **Nextflow cache name rule.** Strip the URI scheme, map `:` and `/` to
   `-`, then append `.img` (or keep `.sif`). A configured registry prefix is
   applied first. This has not been verified against a live Nextflow.
4. **Object store.** Upload is opt-in and uses operator configuration, with
   no built-in URL, account or credential. It is untested against the real
   bucket.
5. **RO-Crate profile.** RO-Crate 1.1 with Workflow RO-Crate conventions. The
   strategy is `include`, `enriched` or `generated`. The root crate is never
   modified, and enriched or generated crates are byte-stable. A
   `CreateAction` and the `#nf-splice` `SoftwareApplication` are always
   added; identity corrections and author credit are reviewed choices.
6. **Private actor storage.** Published review events carry actor labels
   only. Contact details are kept only in an owner-only local audit store
   (`NF_SPLICE_AUDIT_DIR`) outside the repository, and nothing is public
   unless the user opts in.
7. **Slurm default.** `nf-splice configure execution-profiles --slurm-default`
   adds a generated, reviewable candidate. It has no site literals: queue,
   account and similar values are operator configuration. Nothing is the
   default until a reviewer chooses it.
8. **Claude Team vs SDK billing.** The docs state that a Team subscription
   does not automatically authorise or pay for Agent SDK usage. Live use is
   opt-in (`NF_SPLICE_LIVE_AGENT=1 pytest -m live_agent`) and has not been
   verified.

## Review points

- `services/__init__.py` exports lazily through `__getattr__` to break a
  services/layers import cycle. Review this if the package layout changes.
- Review sidecars are named `*.review.json`, so no review file looks like a
  public output contract.
- The legacy authoring document model is kept only so migration can read
  0.1.0 state.
- `.gitattributes` marks fixtures binary and lets `*.config` keep its
  intentional CRLF fixtures.

## Commits on this branch (base `9ad15c1`)

| Commit | Summary |
| --- | --- |
| `4abc414` | chore(gitignore): ignore in-repository local development workspace |
| `2cfea1f` | build(dev): add in-repository workspace setup and staged-path guard |
| `6464f0c` | style(outputs): document intentional character-wise suffix comparison |
| `46b6239` | test(fixtures): freeze nf-splice 0.1.0 legacy bundle and job output |
| `460e55a` | docs(adr): ADR-0023 incremental decisions with a checked release ledger |
| `73d2ad9` | feat(contracts): five workflow-bundle contract families and registry |
| `fe5fc40` | feat(vocabulary): reserve the upstream Nextflow metadata word and define bundle/job/sample/run terms (subject paraphrased; the reserved word is kept out of these docs) |
| `c7e2ae9` | feat(drafts): restricted YAML 1.2 drafts with three-way patches |
| `aece560` | feat(outputs): SPLICE job/sample/run scopes and catalogue-backed runtime |
| `4cb67e0` | feat(audit): public review events and private local audit store |
| `4907dd2` | feat(layers): file-first layer base and bundle.draft.yaml identity layer |
| `f3cbd68` | feat(layers): single authoritative outputs.draft.yaml |
| `5e64686` | feat(inputs): engine-neutral input contract with per-parameter access |
| `4746161` | feat(components): container sources, variants and verified distributions |
| `af06453` | feat(execution): reviewed default profile and generated config route |
| `cb6d510` | feat(provenance): reviewed RO-Crate analysis, enrichment and generation |
| `9c75ff0` | feat(lifecycle): per-layer promotion and transactional bundle publication |
| `2aaf1f7` | feat(migration): preview and apply 0.1.0 state migration into drafts |
| `2b7f18d` | feat(cli): switch the CLI to file-first drafts |
| `2ec880d` | feat(tui): guided Textual wizard replacing the dashboard |
| `9b6fd89` | refactor: retire monolithic nf-splice.yaml services and renderers |
| `3566e4e` | docs(adr): ADR-0030..0038 Current; supersede ADR-0021 and ADR-0022 |
| `21f4185` | feat(agents): optional provider-neutral, approval-gated agent tools |
| `14bb8d1` | docs: 0.3.0 user, contract, migration and component references |
| `cb61dfb` | ci: Python 3.10-3.14 matrix, packaging and hygiene gates |
| `558a18d` | fix(inspectors): read single-line Nextflow metadata blocks |
| `1122da7` | test: cross-cutting acceptance scenarios S03, S04, S08, S09, S10, S13 |
| `debc27a` | build(scripts): fall back to uv pip check in pip-less environments |
| `188aeaa` | docs(release): 0.3.0 handover, acceptance checklist and flagged decisions |
| `6bf17c4` | chore(gitignore): ignore personal Claude Code local settings |
| `035f7c1` | chore(gitignore): anchor build directories and ignore secrets and local files |
| `375b5d4` | test: use a reserved example domain for the fictional maintainer address |

The commit that updates this list follows these. Run `git log 9ad15c1..`
to see the full list.

### Commit identity rewrite

Before anything was pushed, every commit after `9ad15c1` was rewritten
locally with `git filter-branch`. The rewrite replaced an author and
committer email that Git had derived from the machine's hostname with the
maintainer's own identity, and removed AI co-author trailers. File content
(the final tree), commit order, subjects and dates did not change. The IDs
above are the rewritten ones. A repository-local `user.name` and
`user.email` are now set, so Git no longer derives an identity from the host.

## Clean staging evidence

Before every commit, `git diff --cached --name-only` was checked against the
intended paths and `python scripts/check_staged_paths.py` passed. After the
final commit:

- `git status --short` lists only the untracked host-application folder
  `.claude/`, which was deliberately never staged.
- `git diff --cached --name-only` is empty.
- `git check-ignore -v .nf-splice-local/x` matches `.gitignore:225:/.nf-splice-local/`.

## Release procedure (documentation only; not executed)

1. Push the branch and open a pull request against `main`. Let the CI
   `guard`, matrix, nf-core coexistence and package jobs pass.
2. Run the two opt-in tests where their dependencies exist: with Nextflow
   (`pytest -m nextflow`) and with approved Claude credentials
   (`NF_SPLICE_LIVE_AGENT=1 pytest -m live_agent`).
3. Confirm the section 18 decisions with ingestion/DEX and platform owners.
4. Merge, tag `v0.3.0`, then build and publish the sdist and wheel through
   the project's normal release process.
5. Publish the five schema families at their `schemas.splice-data.io`
   identifiers before ingestion switches to 0.3.0.
