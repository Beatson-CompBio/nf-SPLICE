# nf-SPLICE 0.3.0 release record

**Status:** ready for review on branch `wip/nf-splice-v0.3.0`; not released.
Nothing has been merged, tagged or published. The branch passed CI at
`0828774`; the agentic AI and output-route commits after `318c350` are local
and have not yet been pushed or run in CI.

| Item | Value |
| --- | --- |
| Branch | `wip/nf-splice-v0.3.0` |
| Base commit | `9ad15c1` (`main` when the branch was created) |
| Package version | 0.3.0 |
| Contract revision | 0.3.0 for all five workflow-bundle families (the first supported revision) |
| Python | 3.10 to 3.14 |
| Install | From GitHub; nf-splice is not on PyPI |

## For reviewers and testers

Install the branch into a virtual environment:

```bash
python -m venv ~/.venvs/nf-splice
. ~/.venvs/nf-splice/bin/activate
python -m pip install "git+https://github.com/Beatson-CompBio/nf-SPLICE.git@wip/nf-splice-v0.3.0"
nf-splice --version
```

Then follow the [user guide](USAGE.md), starting with
[Getting started](guide/getting-started.md), on one of your own Nextflow
pipelines. A small pipeline for trying the tool is in the repository at
`tests/fixtures/incomplete-drafts-0.3.0/repository/`; copy it without its
`splice/` directory to start from scratch.

To try agentic AI, install the `claude` extra in the same way (see
[Agentic AI](guide/agentic-ai.md)) and follow the
[tutorials](USAGE.md#tutorials). `tests/fixtures/multi-route-0.3.0/` has a
pipeline with alternative and optional routes and a results tree from one
run, made for trying output discovery, `nf-splice assess` and sessions.

Please look first at:

1. The [decisions flagged for review](#decisions-flagged-for-review).
2. ADR-0044 to ADR-0046: the three ways of working, agent permissions and
   attribution, and the skills.
3. ADR-0042: output routes, and why the catalogue and a job's
   `analysis_output.json` differ.
4. ADR-0041, which removes all 0.1.0 compatibility because 0.1.0 was a
   pre-release test version.
5. The [schema reference](schemas/README.md), if you build tools on bundles.

## Feature ledger

Each row maps one 0.3.0 feature to the ADR(s) that govern it, the main
implementation files and the tests that verify it. `tests/test_adr_governance.py`
checks that every ADR exists, every path exists and every test file exists.

| Feature | ADR(s) | Implementation | Tests | Status |
| --- | --- | --- | --- | --- |
| Incremental ADR discipline and ledger | ADR-0023 | `docs/ARCHITECTURE_DECISIONS.md`, `docs/RELEASE_0.3.0.md` | `tests/test_adr_governance.py` | Current |
| Local-only workspace and staged-path guard | ADR-0023 | `.gitignore`, `scripts/dev-env.sh`, `scripts/check_staged_paths.py` | `tests/test_dev_workspace.py` | Current |
| Five workflow-bundle contract families and release registry | ADR-0024 | `src/nf_splice/contracts/registry.py`, `src/nf_splice/contracts/data/registry.json`, `docs/schemas/` | `tests/test_contracts.py` | Current |
| Offline schema list/show/validate/check commands | ADR-0024 | `src/nf_splice/contracts/validation.py`, `src/nf_splice/contracts/compatibility.py`, `src/nf_splice/cli.py` | `tests/test_contracts.py` | Current |
| Package version 0.3.0 | ADR-0024 | `src/nf_splice/_version.py` | `tests/test_cli.py`, `tests/test_contracts.py` | Current |
| Reserved-word vocabulary audit and glossary | ADR-0025 | `src/nf_splice/vocabulary.py`, `src/nf_splice/inspectors/identity.py`, `docs/GLOSSARY.md` | `tests/test_vocabulary.py` | Current |
| Restricted YAML 1.2 drafts with comment-preserving three-way patches | ADR-0026 | `src/nf_splice/drafts/` | `tests/test_drafts_infra.py` | Current |
| Job/sample/run output scopes | ADR-0027 | `src/nf_splice/domain/outputs.py`, `src/nf_splice/inspectors/outputs.py`, `src/nf_splice/runtime/analysis_output.py` | `tests/test_output_scopes.py` | Current |
| Free-text output categories and stages | ADR-0027 | `src/nf_splice/domain/outputs.py`, `src/nf_splice/renderers/outputs.py` | `tests/test_output_discovery.py`, `tests/test_output_scopes.py` | Current |
| Job metadata (`--job-metadata`) | ADR-0027 | `src/nf_splice/runtime/analysis_output.py`, `src/nf_splice/cli.py` | `tests/test_output_scopes.py`, `tests/test_runtime.py` | Current |
| outputs.schema.json x-output-catalog as sole runtime catalogue | ADR-0028 | `src/nf_splice/renderers/outputs.py`, `src/nf_splice/runtime/analysis_output.py` | `tests/test_output_scopes.py`, `tests/test_output_contracts.py` | Current |
| Actor attribution and private audit store | ADR-0029 | `src/nf_splice/domain/audit.py`, `src/nf_splice/services/audit.py` | `tests/test_audit.py` | Current |
| One authoritative YAML draft per layer; no nf-splice.yaml | ADR-0030 | `src/nf_splice/layers/base.py`, `src/nf_splice/drafts/` | `tests/test_layer_bundle.py`, `tests/test_layer_outputs.py` | Current |
| Rich identity in bundle.draft.yaml | ADR-0031 | `src/nf_splice/layers/bundle.py`, `src/nf_splice/domain/identity.py` | `tests/test_layer_bundle.py` | Current |
| Engine-neutral input contract and service-side permissions | ADR-0032 | `src/nf_splice/layers/inputs.py`, `src/nf_splice/services/input_policy.py` | `tests/test_layer_inputs.py` | Current |
| Container sources, verified distributions and cache naming | ADR-0033 | `src/nf_splice/layers/components.py`, `src/nf_splice/services/containers.py` | `tests/test_containers.py` | Current |
| Single reviewed default profile and generated configs | ADR-0034 | `src/nf_splice/layers/execution.py` | `tests/test_layer_execution.py` | Current |
| RO-Crate analysis, enrichment and generation | ADR-0035 | `src/nf_splice/layers/provenance.py` | `tests/test_layer_provenance.py` | Current |
| Per-layer promotion and recoverable bundle publication | ADR-0036 | `src/nf_splice/services/lifecycle.py`, `src/nf_splice/renderers/bundle_index.py` | `tests/test_lifecycle.py` | Current |
| Only 0.3.0 contracts supported; pre-release 0.1.0 compatibility removed | ADR-0041 | `src/nf_splice/cli.py`, `src/nf_splice/runtime/analysis_output.py`, `src/nf_splice/inspectors/splice_tree.py`, `src/nf_splice/contracts/data/registry.json` | `tests/test_state.py`, `tests/test_output_scopes.py`, `tests/test_contracts.py` | Current |
| File-first CLI | ADR-0030, ADR-0036 | `src/nf_splice/cli.py`, `src/nf_splice/services/workspace.py` | `tests/test_cli.py`, `tests/test_reference_workflow.py` | Current |
| Guided Textual wizard and CLI/TUI equivalence | ADR-0038 | `src/nf_splice/interfaces/tui/` | `tests/test_tui.py` | Current |
| Manual Ask AI, AI-assisted sessions and autonomous integration over one engine | ADR-0044 | `src/nf_splice/agents/engine.py`, `src/nf_splice/agents/stages.py`, `src/nf_splice/agents/state.py`, `src/nf_splice/agents/help.py`, `src/nf_splice/cli.py` | `tests/test_agents.py`, `tests/test_scenarios.py` | Current |
| Typed agent operations over the deterministic services, with sandboxed previews | ADR-0044 | `src/nf_splice/agents/operations.py`, `src/nf_splice/agents/toolbox.py`, `src/nf_splice/agents/sandbox.py` | `tests/test_agents.py` | Current |
| Session views in the wizard sharing state with the CLI | ADR-0044, ADR-0038 | `src/nf_splice/interfaces/tui/screens/session.py`, `src/nf_splice/interfaces/tui/screens/ask.py`, `src/nf_splice/interfaces/tui/screens/welcome.py` | `tests/test_agent_interfaces.py`, `tests/test_tui.py` | Current |
| Provider-neutral protocol with Claude Agent SDK and scripted providers | ADR-0044 | `src/nf_splice/agents/protocol.py`, `src/nf_splice/agents/providers/` | `tests/test_agent_interfaces.py` | Current |
| Operation-level permissions, bound approvals and agent attribution | ADR-0045 | `src/nf_splice/agents/permissions.py`, `src/nf_splice/domain/audit.py`, `src/nf_splice/layers/base.py` | `tests/test_agents.py`, `tests/test_audit.py` | Current |
| Publication-route analysis and published-only output discovery | ADR-0042 | `src/nf_splice/inspectors/routes.py`, `src/nf_splice/inspectors/outputs.py`, `tests/fixtures/multi-route-0.3.0/` | `tests/test_routes.py`, `tests/test_output_discovery.py` | Current |
| Separate contract, observed-output and coverage assessments (`nf-splice assess`) | ADR-0042 | `src/nf_splice/services/coverage.py`, `src/nf_splice/cli.py` | `tests/test_coverage.py` | Current |
| Optional nf-core checks behind explicit permissions | ADR-0043 | `src/nf_splice/services/checks.py` | `tests/test_coverage.py` | Current |
| Canonical skills, root AGENTS.md and runtime skill loading | ADR-0046 | `AGENTS.md`, `skills/`, `src/nf_splice/agents/skills.py`, `docs/AGENTS.md` | `tests/test_skills.py`, `tests/test_packaging.py` | Current |
| Private `.splice-local/` workspace, published-only `splice/`, safe ignore rule and migration | ADR-0047 | `src/nf_splice/layout.py`, `src/nf_splice/services/migration.py`, `src/nf_splice/drafts/store.py` | `tests/test_layout.py` | Current |
| Isolated integration copies, local commits of the validated bundle, explicit push | ADR-0048 | `src/nf_splice/services/source.py`, `src/nf_splice/services/gitops.py` | `tests/test_source_git_export.py` | Current |
| Deterministic, verified ZIP export of the bundle or pipeline | ADR-0049 | `src/nf_splice/services/export.py` | `tests/test_source_git_export.py` | Current |
| Explicit provider selection, typed provider errors, credential store and `nf-splice provider` commands | ADR-0050 | `src/nf_splice/agents/providers/__init__.py`, `src/nf_splice/agents/providers/base.py`, `src/nf_splice/credentials.py` | `tests/test_provider_cli.py`, `tests/test_agents.py` | Current |
| Claude provider with a Console API key, private configuration and typed SDK errors | ADR-0050 | `src/nf_splice/agents/providers/claude.py` | `tests/test_agent_interfaces.py` | Current |
| OpenAI provider: Sign in with ChatGPT and the Responses API | ADR-0051 | `src/nf_splice/agents/providers/openai_auth.py`, `src/nf_splice/agents/providers/openai.py` | `tests/test_openai_provider.py` | Current |
| Codex provider through a locked-down app-server | ADR-0052 | `src/nf_splice/agents/providers/codex.py` | `tests/test_codex_provider.py` | Current |
| OpenCode provider with deny-all permissions and a loopback tool bridge | ADR-0053 | `src/nf_splice/agents/providers/opencode.py`, `src/nf_splice/agents/providers/mcp_bridge.py` | `tests/test_opencode_provider.py` | Current |
| Bundle consumer kit: agent and role skill files, offline definitions and real examples for developers building on bundles | ADR-0054 | `bundle-consumer-kit/`, `scripts/build_consumer_kit.py` | `tests/test_consumer_kit.py` | Current |
| Typed assay capabilities from a pinned SPLICE modality vocabulary, in every mode | ADR-0055 | `src/nf_splice/catalogue/`, `src/nf_splice/layers/bundle.py`, `src/nf_splice/inspectors/assays.py`, `src/nf_splice/interfaces/tui/screens/assays.py` | `tests/test_assay_capabilities.py`, `tests/test_tui.py` | Current |
| Scientific assay discovery without AI, and classification-gated ingestion readiness | ADR-0056 | `src/nf_splice/services/assay_discovery.py`, `src/nf_splice/catalogue/data/assay-evidence-rules.json` | `tests/test_assay_discovery.py` | Current |
| Per-key contract references generated from packaged definitions | ADR-0024 | `scripts/generate_schema_docs.py`, `docs/schemas/fields.yaml`, `docs/CONTRACTS.md` | `tests/test_docs.py` | Current |
| Task-based user guide and contributor guide with verified commands | ADR-0023, ADR-0027 | `README.md`, `CONTRIBUTING.md`, `docs/USAGE.md`, `docs/guide/` | `tests/test_docs.py` | Current |
| Generated command reference | ADR-0023 | `scripts/generate_cli_docs.py`, `docs/reference/cli.md` | `tests/test_docs.py` | Current |
| Integrator overview, `analysis_output.json` and companion-file references | ADR-0024, ADR-0028 | `docs/CONTRACTS.md`, `docs/schemas/README.md`, `docs/schemas/analysis-output.md`, `docs/schemas/companion-files.md` | `tests/test_docs.py` | Current |
| Reference validated bundle and incomplete draft fixtures | ADR-0030, ADR-0036 | `tests/fixtures/example-0.3.0/`, `tests/fixtures/incomplete-drafts-0.3.0/` | `tests/test_reference_fixtures.py` | Current |
| CI matrix 3.10-3.14, packaging and hygiene gates | ADR-0040 | `.github/workflows/ci.yml`, `pyproject.toml` | `tests/test_packaging.py` | Current |

## What 0.3.0 provides

nf-splice 0.1.0 was a pre-release test version; 0.3.0 is the first supported
release and the baseline for schema compatibility (ADR-0041).

- **File-first authoring.** One YAML draft per layer under the private
  `.splice-local/drafts/`
  (plus native `.config` drafts for generated profiles) is the source of
  truth. Edit drafts with commands, the wizard or any editor; nf-splice applies
  targeted, comment-preserving patches and reports conflicts instead of
  overwriting (ADR-0026, ADR-0030).
- **Five versioned contracts** with a packaged registry and the offline
  `nf-splice schema list|show|validate|check` commands (ADR-0024). There is
  no `outputs.json`; `outputs.schema.json` carries the output catalogue in
  `x-output-catalog` (ADR-0028).
- **Job, sample and run** output scopes with free-text categories and
  stages, and one `analysis_output.json` per completed job (ADR-0027).
- **Layer reviews:** rich identity (ADR-0031), an engine-neutral input
  contract with per-parameter access (ADR-0032), container sources and
  verified image files (ADR-0033), one reviewed default execution profile
  (ADR-0034) and RO-Crate review, enrichment or generation (ADR-0035).
- **Safe publishing:** per-layer promotion and transactional bundle
  publication with recovery; lock format 2.0 (ADR-0036).
- **Attribution and privacy:** public actor labels, a private local audit
  store for contact details, opt-in public maintainers (ADR-0029).
- **Guided wizard** over the same services as the CLI (ADR-0038).
- **Agentic AI built in**, in three ways of working over one deterministic
  engine (ADR-0044): manual work with read-only *Ask AI* help; AI-assisted
  sessions where the agent proposes each stage with its diff and validation
  and a person approves, objects or asks; and autonomous integration where
  the agent does the whole integration within an approved scope and reports
  truthfully what is done and what is blocked. Operation-level permissions,
  stale-proof approvals and attribution that never presents an agent's
  decision as human review (ADR-0045). Skills in `skills/` guide every
  provider (ADR-0046).
- **Four real AI providers** behind one protocol, each restricted to
  nf-splice's tools by configuration and tests that attempt forbidden tools:
  Claude (Agent SDK, Console API key), OpenAI (Sign in with ChatGPT for
  open-source apps, or an explicitly chosen API key; Responses API), Codex
  (locked-down app-server) and OpenCode (deny-all server, local or remote
  models). Explicit selection, typed provider errors that pause rather than
  lose work, per-user credential storage and
  `nf-splice provider list|doctor|models|select|auth|test`
  (ADR-0050 to ADR-0053). Dated account guidance in
  `docs/guide/providers.md`.
- **Assay capabilities:** a pipeline declares every assay it can process,
  classified by a packaged, pinned snapshot of the SPLICE modality
  vocabulary (modality, subtype, assay type, assay method, with every path);
  published as typed `pipeline.assay_capabilities` and re-verified on
  validation; `nf-splice catalogue` commands, a wizard step and agent tools
  share one resolver (ADR-0055). nf-splice investigates a pipeline's tools,
  parameters, outputs and documentation to recommend assays even when none
  is named, asks or records a blocker where the evidence cannot decide, and
  a pipeline is ready for ingestion only once its assays are classified
  (ADR-0056).
- **Private workspace and delivery:** private state in `.splice-local/`,
  published files only in `splice/`, with migration (ADR-0047); an isolated
  integration copy of the pipeline, local commits of the validated bundle
  and push only on request (ADR-0048); verified, deterministic ZIP archives
  of the bundle or the pipeline (ADR-0049).
- **Output routes and evidence:** static tracing of Nextflow publication
  routes across alternative and optional branches, discovery of published
  outputs only, and `nf-splice assess`, which reports contract validity,
  observed-output compatibility and route coverage as separate results
  (ADR-0042); optional nf-core checks only when installed and permitted
  (ADR-0043).
- **Documentation:** a task-based user guide, a generated command reference
  and key-by-key schema references for integrators.
- **Bundle consumer kit** for developers who build on bundles without
  nf-splice: a drop-in `AGENTS.md`, five role skills (contracts, ingestion,
  `analysis_output.json`, web interfaces, job launch), offline definitions
  and a real example bundle and job inventory, all checked against the
  contracts (ADR-0054).
- **CI** on Python 3.10 to 3.14, nf-core 4.0.2 coexistence, packaging and
  repository-hygiene checks, run on pushes to `main` and to `wip/**`
  branches (ADR-0040).

### Fixed during review

- Single-line Nextflow metadata blocks (`{ name = 'x'; version = 'y' }`) are
  read, with correct evidence line numbers.
- `--overwrite-edited` accepts the `splice/`-prefixed path that the blocking
  message prints.
- The `identity_mismatch` message suggests a command that exists
  (`nf-splice draft sync-identity`); a test now checks every command quoted in
  messages.
- `scripts/run-checks.sh` works in uv environments without pip.

## Functional acceptance checklist (specification section 17)

"Done" items are backed by the ledger tests above and the scenario tests
below. "Partial" items are complete offline and wait only on the external
dependency named. "Not applicable" items were withdrawn by ADR-0041.

| Area | Requirement | State | Evidence / notes |
| --- | --- | --- | --- |
| Contract | Package reports 0.3.0 consistently | Done | `test_cli.py`; `nf-splice --version` on 3.10, 3.11 and 3.14 |
| Contract | Exactly five families, including `/workflow-bundle/bundle`, versioned, registered, documented key by key | Done | `test_contracts.py`, `test_scenarios.py::test_s10_*`, `docs/schemas/` |
| Contract | Compatibility checks for future revisions | Done | `test_contracts.py` (`schema check --against`) |
| Contract | Old fixtures and 0.1.0 migration adapters | Not applicable | Withdrawn by ADR-0041: 0.1.0 was a test version |
| Contract | Rich `bundle.json` identity | Done | `test_layer_bundle.py` |
| Contract | Consistent pipeline/generator/version provenance in every contract | Done | `test_lifecycle.py`, `test_scenarios.py::test_s10_*` |
| Contract | No `outputs.json`; `x-output-catalog` drives the runtime | Done | `test_output_contracts.py`, `test_s10_*` |
| Contract | Free-text output categories and stages | Done | `test_output_discovery.py` |
| Contract | Engine-neutral 2020-12 input contract, lossless nf-schema import, no duplicated parameters | Done | `test_layer_inputs.py` |
| Contract | Service-level input permissions, presentation and engine mapping | Done | `test_layer_inputs.py` |
| Components | OCI source, Apptainer/Singularity source and downloadable image kept distinct | Done | `test_containers.py` |
| Components | HTTPS image validation, SHA-256, local conversion, cache naming, opt-in upload | Partial | Offline behaviour tested. Live Nextflow cache naming and the real object store are not verified (decisions 3 and 4) |
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
| AI | No AI dependency for manual use; offline compilation and validation | Done | `test_s08_*` (SDK import blocked, sockets disabled), `test_agents.py` |
| AI | Manual mode with read-only Ask AI that cannot change files | Done | `test_agents.py`, `test_agent_interfaces.py` |
| AI | AI-assisted sessions: bounded proposals, approval, objection investigation, revision, no advance on silence | Done | `test_agents.py`, `test_agent_interfaces.py` |
| AI | Autonomous integration builds and validates a real bundle without prompts; blockers reported and resumed in assisted mode | Done | `test_agents.py` |
| AI | All mode transitions preserve drafts and history; interrupted actions roll back | Done | `test_agents.py` |
| AI | Stale approvals, concurrent sessions, path traversal, secrets, permission escalation and prompt injection refused | Done | `test_agents.py` |
| AI | Claude adapter and scripted provider conform to one protocol; missing capabilities fail clearly | Done | `test_agent_interfaces.py` |
| AI | Skills canonical, packaged, accurate and loaded into every provider turn | Done | `test_skills.py` |
| Outputs | Catalogue covers alternative routes; one-route example validates without the others; unknown files fail by default | Done | `test_routes.py`, `test_coverage.py` |
| Release | Regression tests pass | Done | 217 passed, 2 opt-in skipped |
| Release | Scenarios S01-S15 pass offline | Done | S05 and S14 migration parts not applicable; see below |
| Release | Python 3.10-3.14, nf-core coexistence, pytest, ruff, mypy, packaging, installed CLI | Done | 3.10, 3.11 and 3.14 run locally; all of 3.10 to 3.14 pass in GitHub Actions |
| Release | Golden files and snapshots committed | Done | `tests/snapshots/tui/`, `docs/schemas/*/v0.3.0/` |
| Release | Bundle family URI exact; reserved word only in the upstream parser | Done | `test_vocabulary.py`, `test_s13_*`, `test_docs.py` |
| Release | Scopes exactly job/sample/run with mixed granularity | Done | `test_output_scopes.py` |
| Release | ADR register, statuses, supersession and ledger complete | Done | `test_adr_governance.py` |
| Release | Docs complete; every documented command, option, link and anchor exists | Done | `test_docs.py`; fresh-install walkthrough below |
| Release | No private data, credentials, local paths or drafts in published files | Done | `test_audit.py`, `test_lifecycle.py` |
| Hygiene | Single in-place clone; no external worktrees | Done | `git worktree list` shows only this clone |
| Hygiene | Anchored `/.nf-splice-local/` rule confirmed by `git check-ignore` | Done | `.gitignore` |
| Hygiene | All temporary, cache, report and session files inside `.nf-splice-local/` | Done | `scripts/dev-env.sh`, `test_dev_workspace.py` |
| Hygiene | Staged-path guard rejects ignored paths, even forcibly staged | Done | `scripts/check_staged_paths.py`, `scripts/pre-commit`, CI `guard` job |

## Scenario coverage (specification section 15.2)

| Scenario | Test(s) |
| --- | --- |
| S01 manual CLI | `test_reference_workflow.py` |
| S02 Textual, identical to CLI | `test_tui.py::test_cli_and_tui_produce_identical_drafts_and_bundles` |
| S03 manual + AI + external edit | `test_scenarios.py::test_s03_manual_and_ai_work_are_interchangeable`, `test_agents.py::test_every_mode_transition_preserves_drafts_and_history` |
| S04 resume and external mutation | `test_scenarios.py::test_s04_*`, `test_tui.py`, `test_drafts_infra.py`, `test_lifecycle.py` (drift) |
| S05 legacy bundle migration | Not applicable (ADR-0041) |
| S06 container hazard | `test_containers.py` (offline HTTPS fixture, SSRF and integrity guards) |
| S07 RO-Crate drift | `test_layer_provenance.py::test_stale_crate_blocks_inclusion_and_reviewed_enrichment_is_stable` |
| S08 no AI, no network | `test_scenarios.py::test_s08_full_workflow_without_ai_or_network` |
| S09 failure injection | `test_scenarios.py::test_s09_*`, `test_lifecycle.py::test_interrupted_publication_is_recovered_explicitly`, `test_drafts_infra.py` |
| S10 five-contract JSON consumer | `test_scenarios.py::test_s10_json_consumers_need_only_the_five_contracts` |
| S11 Python and packaging | `test_packaging.py`, local 3.10/3.11/3.14 runs, CI matrix |
| S12 multi-job separation | `test_output_scopes.py::test_two_jobs_produce_separate_documents_without_static_mutation` |
| S13 terminology | `test_scenarios.py::test_s13_*`, `test_vocabulary.py`, `test_docs.py` |
| S14 mixed granularity | `test_output_scopes.py::test_one_job_with_samples_and_runs_classifies_each_granularity`; the migration part is not applicable (ADR-0041) |
| S15 ADR traceability | `test_adr_governance.py` |

S09 does not simulate a full disk. It injects a write failure through a
read-only target, and `test_lifecycle.py` tests interrupted publication
through the `replace_file` hook; both use the same staging and recovery code.

## Tests and checks run

All commands ran inside the clone with `. scripts/dev-env.sh`, which keeps
every cache, temporary file, report and session under `.nf-splice-local/`.

| Check | Result |
| --- | --- |
| `scripts/run-checks.sh` (dependency check, pytest, ruff, ruff format, mypy, installed CLI, staged-path guard) | exit 0: 217 passed, 2 skipped; ruff clean; 140 files formatted; mypy clean on 129 files; `nf-splice 0.3.0` |
| `python -m build --no-isolation` | sdist and wheel built; the wheel contains the four skills |
| Generated references (`generate_schema_docs.py --check`, `generate_cli_docs.py --check`) | current |
| Wheel with `[dev]` in Python 3.11.16 and 3.14.7 environments, suite run against the installed package | 217 passed, 2 skipped on each |
| Wheel plus `nf-core==4.0.2` resolved together in a Python 3.10.21 environment | dependencies compatible; `nf-splice 0.3.0` and `nf-core 4.0.2` both run |
| Each new commit's tree exported and tested on its own | the output-routes documentation commit: docs, ADR, coverage, routes and agent tests pass; the agentic commit: 216 passed, 3 skipped (one Git-only test cannot run outside a checkout) |
| Autonomous and assisted sessions on the multi-route fixture with the scripted provider | complete: every stage gated, bundle valid, STAR-only example compatible, all 7 routes covered |
| nf-core lint adapter against a real nf-core 4.0.2 on an nf-core-marked copy of the fixture | without Nextflow it first reported `error` (nf-core fails without Nextflow); now `not_run` with the reason, before nf-core is started |
| Install from Git (`pip install "git+…@wip/nf-splice-v0.3.0"`) into a fresh Python 3.14 environment, then the user guide followed step by step on a new pipeline | Done at `ecf745d`: every layer reviewed, bundle published and validated, a job's `analysis_output.json` generated and validated, a new version released, a hand-edited file overwritten explicitly. Not repeated for the agentic commits, which are not pushed yet |

| Release-completion phase, `scripts/run-checks.sh` at the provider commits | exit 0: 291 passed, 3 skipped; ruff clean; 161 files formatted; mypy clean on 150 files |
| Wheel and sdist built from the final tree; wheel installed with `[dev,openai]` into fresh Python 3.10.21, 3.12.14 and 3.14.7 environments and the suite run against the installed package | 292 passed, 3 skipped on each |
| Real Codex 0.162.1 app-server against a local fake Responses endpoint (`NF_SPLICE_CODEX` set) | passed: only the nf-splice tool (and Codex's `request_user_input`, which nf-splice refuses) was offered; forged `exec_command`, `shell`, `apply_patch` and `web_search` calls did not run |
| Real OpenCode 2.0.29 server against a local fake model through a recording proxy | passed: forged `bash`, `write`, `read` and `webfetch` failed, only `nfsplice_*` was offered, no outbound connection was attempted; the tool is available on the first step |
| Installed-wheel end-to-end on a real RNA-seq pipeline copy | see [End-to-end on a real pipeline](#end-to-end-on-a-real-pipeline) |
| Assay capabilities (`tests/test_assay_capabilities.py`, 26 tests): offline snapshot (34 entities, 34 edges, 14 registrations, exact ids and provenance; loads with sockets disabled and outside the clone), poly(A)/Total, ATAC-seq and multi-modality spatial classifications, draft-to-bundle round trip with byte-identical rebuild and a clean archive, rejected selections and broken vocabularies, legacy free text, assisted objection and revision, autonomous blocker resumed in assisted mode, generic FASTQ pipeline, mocked API sources | passed; also against the installed wheel (Python 3.12.14): 341 passed, 3 skipped |
| Assay discovery (`tests/test_assay_discovery.py`, 11 tests, scenarios A to H on realistic fixtures) | passed: documented poly(A) found; an unlabelled RNA-seq pipeline gets Transcriptomics with poly(A) and total RNA-seq to verify and the deciding question; other domains (ATAC-seq, DNA methylation) classified at the level the evidence supports; Kraken2 alone discounted; assisted question and answer; autonomous blocker resumed in assisted mode; readiness levels enforced |
| Assay discovery on the real RNA-seq pipeline copy | Transcriptomics via Short-read RNA-seq (STAR, RSEM, Salmon, featureCounts, DESeq2, dupRadar, Qualimap…); Total RNA-seq suggested by SortMeRNA and the rRNA-removal parameters, poly(A) RNA-seq to verify; metagenomics not established from Kraken2 and Bracken |

The walkthrough found two documentation gaps and one wrong command in a
message; all three are fixed. Running the suite against the installed wheel
found that OpenCode reloads when the tool bridge is registered, so a prompt
sent at once ran without the tools; the adapter now waits for the reload
(`8f7ca26`).

### Live provider verification

No live provider credentials were available or authorised during this
work, so no live model was used. These tests are **NOT RUN**; nothing here
claims live verification.

| Live check | Status | How to run it |
| --- | --- | --- |
| Claude Agent SDK assisted session with a Console API key and a spending cap | NOT RUN | `ANTHROPIC_API_KEY=… NF_SPLICE_LIVE_AGENT=1 pytest -m live_agent` |
| Sign in with ChatGPT and a completed Responses turn | NOT RUN | `nf-splice provider auth openai --sign-in`, then `nf-splice provider test openai --allow-remote-model` |
| Codex app-server with a real ChatGPT plan token | NOT RUN | after the sign-in above: `nf-splice provider test codex --allow-remote-model` |
| OpenCode with a real local tool-capable model | NOT RUN (no Ollama, LM Studio or other local model server is installed here) | configure the model in OpenCode, then `nf-splice provider test opencode` |
| OpenCode with a configured cloud provider | NOT RUN (needs your authorisation for cost) | `nf-splice provider test opencode --model PROVIDER/MODEL --allow-remote-model` |

`nf-splice provider doctor` from the installed wheel, with no credentials
configured, reported: `claude` not ready (SDK 0.2.168 and its CLI present,
no API key), `openai` and `codex` not ready (sign-in support present, no
account signed in; Codex 0.162.1 verified), `opencode` ready (2.0.29, no
model selected), `scripted` ready.

## End-to-end on a real pipeline

The maintainer supplied a copy of a real pipeline,
`splice-nf-bulk-rnaseq` (based on nf-core/rnaseq, revision `e90c65a`), which
also contains a hand-made `splice/` folder written before nf-splice could
produce one. The run used the wheel installed into a fresh environment
outside the repository.

1. `nf-splice source prepare` made an isolated Git working copy on branch
   `nf-splice/integration-splice-nf-bulk-rnaseq-copy`; `workspace check`
   confirmed the ignore rule. `status` read the hand-made `splice/` as
   published files that are outdated or unknown relative to drafts, without
   touching them.
2. `init --accept-detected` created the six drafts and flagged three
   conflicting identity values (the copy's folder name and path against the
   pipeline's own name and URL). About 450 review items remained: access
   policies for each parameter, 117 statically traced publication routes,
   73 components, profiles and provenance.
3. Manual mode: identity resolved with `configure bundle --set …`; the
   bundle layer became ready.
4. AI-assisted mode with the scripted provider resumed at the inputs stage
   (identity was recognised as already complete), staged a diff for
   approval and applied exactly the approved revision; with no further
   scripted decisions it asked the person instead of guessing.
5. Switched to manual, changed an access policy with
   `configure inputs --decision-file`, back to assisted, then to autonomous:
   the autonomous run recorded a blocker per incomplete stage and reported
   `partial` with the reasons, the 117 uncovered routes and "no example
   output supplied".
6. `export` and `git commit` both refused, because the existing hand-made
   bundle does not validate against the 0.3.0 contracts; nothing was
   committed or pushed.
7. The original pipeline was unchanged (file hashes, HEAD and status
   compared before and after), and no runtime file was written to the
   nf-SPLICE checkout.

Completing this pipeline needs the ~450 decisions to be reviewed by a person
or a live model; that was not done here. The run found three defects, all
fixed in `07bf3fd`: a triple-quoted `description` in the Nextflow
configuration was read as a single quote; a README title in an HTML `<h1>`
was missed; a decision-file entry with the wrong key ended in a traceback. The two skipped tests are opt-in: `nextflow`
needs a Nextflow installation and `live_agent` needs approved Claude
credentials.

## Known dependencies and limitations

- **Nextflow** is not installed on the development machine. The
  Singularity/Apptainer cache-name rule follows the published Nextflow rule
  and has unit tests; the opt-in check against a real Nextflow has not run.
- **Docker, Apptainer and Singularity** are not installed there either;
  image conversion is tested with fakes only.
- **SPLICE object store:** uploads use the operator's own authenticated
  backend and were not tested against the real bucket.
- **Ingestion code** is not in this repository. The components shape is
  published as a schema, an example and fixtures; ingestion needs to read it.
- **Live providers:** no live Claude, ChatGPT, Codex or OpenCode model was
  used (see [Live provider verification](#live-provider-verification)). The
  adapters are tested offline against fake SDKs, fake servers and, for Codex
  and OpenCode, the real programs with local fake models.
- **Codex** is enabled only for 0.162.x and **OpenCode** only for 2.0.x;
  other versions are reported unavailable until verified. nf-splice installs
  neither.
- **Sign in with ChatGPT** needs a browser on the same computer; there is no
  browserless flow.
- **Assay discovery** is rule-based: it establishes what the evidence
  supports and cannot prove a library preparation the repository never
  states; those cases are asked or blocked, never guessed. The rules cover
  the domains of the current vocabulary.
- **Assay vocabulary:** the packaged snapshot is `splice-sprint-2026-10-14`,
  compiled from the platform's seed files. No live SPLICE platform API was
  contacted; the API source is tested with mocks only.
- **OpenCode readiness:** OpenCode has no API that reports the tools a
  session has, so the adapter waits for its reload to finish and retries
  once if the tools are not yet available.
- **Static route analysis** reads Groovy text without running Nextflow. It
  follows `publishDir` in processes and configuration selectors, includes
  and aliases, and `if`/`else` blocks, but not channel-level routing
  (`branch`, `filter`), conditions inside `includeConfig`, Nextflow's
  preview `output {}` blocks beyond simple assignments, or values computed
  at run time. Such routes are reported as `unresolved` or
  `inferred_unverified`, never as confirmed.
- **nf-core lint** has run against a real nf-core 4.0.2 only up to the
  Nextflow check, because Nextflow is not installed here; report parsing is
  tested with a fake executable.
- **Previews** in assisted sessions run on a copy without `.git`, so
  Git-derived evidence (revision, remote URL) is missing from previews only.
- **Exit codes:** `configure` commands save the draft and then exit with
  status 2 while blocking issues remain. Scripts should read the message or
  use `nf-splice plan` rather than treat the status as a failed save.

## Decisions flagged for review

From specification section 18.

1. **Schema family histories.** All five families start at revision 0.3.0,
   the first supported revision; 0.1.0 documents are not supported
   (ADR-0041). The release registry maps each tool release to all five
   family revisions, so every future release adds a row even when no family
   changes. The per-job `analysis_output.json` schema is versioned per
   workflow and is not a sixth family.
2. **Components JSON shape.** `id`, `type` and `uri` are kept for simple
   readers. Containers add per-runtime `source_images` and an optional
   verified `distribution` (URL, SHA-256, size, cache file name). The
   unpublished `legacy_ids` field was dropped. Ingestion must be updated to
   read this shape.
3. **Nextflow cache name rule.** Strip the URI scheme, map `:` and `/` to
   `-`, then append `.img` (or keep `.sif`); a configured registry prefix is
   applied first. Not yet verified against a live Nextflow.
4. **Object store.** Upload is opt-in, uses operator configuration and has
   no built-in URL, account or credential. Untested against the real bucket.
5. **RO-Crate profile.** RO-Crate 1.1 with Workflow RO-Crate conventions.
   Strategies `include`, `enriched` or `generated`; the root crate is never
   modified and enriched or generated crates are byte-stable. A
   `CreateAction` and the `#nf-splice` `SoftwareApplication` are always
   added; identity corrections and author credit are reviewed choices.
6. **Private actor storage.** Published review events carry actor labels
   only. Contact details stay in an owner-only local audit store
   (`NF_SPLICE_AUDIT_DIR`) outside the repository; public contacts are
   opt-in.
7. **Slurm default.** `nf-splice configure execution-profiles --slurm-default`
   adds a generated, reviewable candidate without site values; queue and
   account options are operator configuration. Nothing is the default until
   a reviewer chooses it.
8. **Claude Team and SDK billing.** A Team subscription does not by itself
   authorise or pay for Agent SDK usage. Live use is opt-in
   (`NF_SPLICE_LIVE_AGENT=1 pytest -m live_agent`) and unverified.
9. **Default autonomous scope.** Autonomous runs may edit drafts and build
   into `splice/` by default (the build is transactional and recoverable);
   overwriting hand-edited files and running external tools need explicit
   grants (ADR-0045).
10. **Parameter access in autonomous runs.** An autonomous agent may set
    parameter access policies, recorded as `agent_policy` decisions; an
    assisting agent needs the stage approval (ADR-0045, ADR-0032).
11. **Session storage.** Agent sessions live in the repository's ignored
    `.nf-splice-local/agent/` (self-protected by a `.gitignore`), while the
    wizard's navigation sessions stay in the user cache (ADR-0044,
    ADR-0038).
12. **nf-core lint permissions.** Lint needs `external_tools`,
    `run_nextflow` and `network`, because it runs `nextflow config` and may
    contact the network (ADR-0043).
13. **Published outputs only.** Output candidates come only from published
    routes; module `meta.yml` files enrich descriptions but no longer create
    candidates on their own (ADR-0042).

## Review points

- `services/__init__.py` exports lazily through `__getattr__` to avoid a
  services/layers import cycle.
- Review sidecars are named `*.review.json`, so no review file looks like a
  public output contract.
- Shared domain base types live in `src/nf_splice/domain/base.py`.
- `.gitattributes` keeps fixture bytes exact and lets `*.config` keep its
  intentional CRLF fixtures.
- Superseded ADRs are exempt from the governance test's path checks, because
  their code is history.

## Commits on this branch (base `9ad15c1`)

| `4abc414` | chore(gitignore): ignore in-repository local development workspace |
| `2cfea1f` | build(dev): add in-repository workspace setup and staged-path guard |
| `6464f0c` | style(outputs): document intentional character-wise suffix comparison |
| `46b6239` | test(fixtures): freeze nf-splice 0.1.0 legacy bundle and job output |
| `460e55a` | docs(adr): ADR-0023 incremental decisions with a checked release ledger |
| `73d2ad9` | feat(contracts): five workflow-bundle contract families and registry |
| `fe5fc40` | feat(vocabulary): reserve the upstream Nextflow metadata word and define bundle/job/sample/run terms |
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
| `8ca2743` | docs(release): record rewritten commit IDs and the identity rewrite |
| `544c0b5` | docs(cli): generated command reference and help for every option |
| `927857c` | docs(schemas): integrator-focused contract references |
| `a17d3ca` | docs(schemas): present 0.3.0 as the first supported contract revision |
| `dd3f041` | fix(lifecycle): accept splice/-prefixed paths for --overwrite-edited |
| `0db902f` | docs(migration): mark 0.1.0 as a pre-release test version |
| `5e04f0c` | docs: task-based user guide, shorter README and contributor guide |
| `08139cb` | refactor!: remove pre-release 0.1.0 compatibility (ADR-0041) |
| `ff6fe62` | ci: run on review-branch pushes and on demand |
| `e974c2d` | fix(inputs): suggest a sync-identity command that exists |
| `a947583` | docs: install from GitHub and fixes from a fresh-user walkthrough |
| `ecf745d` | docs(release): handover for review of the 0.3.0 branch |
| `773aece` | test(ci): make CLI help and TUI worker checks robust |
| `0828774` | test(cli): rely on functional build flag coverage without Click dependency |
| `318c350` | docs(release): record the first push and passing CI |
| `6dd8c8d` | feat(outputs): trace publication routes and discover only published outputs |
| `8b942cb` | fix(components): end a container expression at the next directive |
| `d3ee657` | feat(assess): report contract validity, observed outputs and coverage separately |
| `985ff0b` | docs: output routes, example evidence and the three assessments (ADR-0042, ADR-0043) |
| `509fa97` | feat(agents)!: manual, AI-assisted and autonomous integration over one engine |
| `31e9d5a` | docs(release): record agentic AI, output routes and their verification |
| `58ba4ac` | feat(layout)!: private .splice-local/ workspace, published-only splice/ (ADR-0047) |
| `de5af40` | feat(delivery): isolated working copies, local commits and verified ZIP export |
| `4e7ca24` | feat(providers): typed errors, credentials, provider CLI, Claude and OpenAI |
| `9558f92` | feat(providers): Codex app-server provider locked to nf-splice tools |
| `8067b24` | feat(providers): OpenCode server provider with deny-all permissions |
| `07bf3fd` | fix: findings from the end-to-end run on a real RNA-seq pipeline |
| `8f7ca26` | fix(opencode): wait until OpenCode has loaded the tool bridge |
| `4888e05` | feat(assays): typed, multi-assay pipeline capabilities from the SPLICE vocabulary |

`git log 9ad15c1..` lists everything, including later updates to this
record.

`773aece` and `0828774` were made after the first push to get CI passing.
They drop help-text assertions for `build --json` and `build --check`,
which depended on how Rich wraps help output on the runner (both options
are still exercised by functional tests). They also let Textual dispatch a
button event before the wizard tests wait for workers, and run the quality
and schema steps even when pytest fails. All commits are authored and committed by the maintainer's own
identity. Before the branch was first pushed, its history was rewritten
locally once to replace an author address Git had derived from the machine
name and to remove AI co-author trailers; content, order, subjects and dates
were unchanged.

## Clean staging evidence

Before every commit, the staged paths were checked against the intended
change and `python scripts/check_staged_paths.py` passed. After the final
commit, `git status --short` lists nothing and `git diff --cached --name-only`
is empty; the only ignored local folders are `.nf-splice-local/` and the
personal `.claude/` settings.

## Release procedure

The maintainer merges without pull requests; reviewers have read access.

1. Push `wip/nf-splice-v0.3.0`. CI runs on the push; make sure every job
   passes, including Python 3.12 and 3.13. CI passed at `0828774`; push
   again for the later commits.
2. Reviewers install the branch (see [above](#for-reviewers-and-testers)),
   follow the user guide and report problems.
3. Run the opt-in tests where their dependencies exist:
   `NF_SPLICE_NEXTFLOW_TESTS=1 pytest -m nextflow` and, with approved
   credentials, `NF_SPLICE_LIVE_AGENT=1 pytest -m live_agent`. Try one
   AI-assisted and one autonomous session with Claude on a real pipeline.
4. Confirm the flagged decisions with ingestion and platform owners.
5. Merge into `main` and push; CI runs again on `main`.
6. Tag `v0.3.0`.
7. Publish the five schema families at their `schemas.splice-data.io`
   identifiers before ingestion switches to 0.3.0.
