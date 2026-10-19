# Working on nf-splice

Instructions for anyone, human or coding agent, who changes this repository.
For how nf-splice's own agents work at run time, see
[`docs/AGENTS.md`](docs/AGENTS.md).

## What nf-splice is

nf-splice prepares a Nextflow pipeline for the SPLICE platform. It reads the
pipeline repository, seeds six editable YAML drafts (and native Nextflow
configs for the execution profiles) with what the evidence supports, and
publishes a validated SPLICE workflow bundle in `splice/` from those files.
People edit the drafts themselves (manual), with an agent that investigates
and proposes one coherent revision per stage for approval (AI-assisted), or
let an agent investigate and author within an approved scope (autonomous).
The drafts on disk are always the source of truth (ADR-0057).

## Architecture and sources of truth

| Concern | Where | Rule |
| --- | --- | --- |
| Decisions | `docs/ARCHITECTURE_DECISIONS.md` | Current ADRs govern the code. A changed decision needs a new ADR. |
| Contracts | `src/nf_splice/contracts/` | Five versioned JSON Schema families; `docs/schemas/` is generated from them. |
| Authoring state | `.splice-local/drafts/*.draft.yaml` and `.splice-local/drafts/configs/*.draft.config` | The only editable source; published files are built from it. `.review.json` sidecars are provenance and advisory candidates, never a gate. |
| Deterministic services | `src/nf_splice/layers/`, `src/nf_splice/services/`, `src/nf_splice/inspectors/`, `src/nf_splice/runtime/` | The only writers and validators of SPLICE files, in every mode. |
| Interfaces | `src/nf_splice/cli.py`, `src/nf_splice/interfaces/tui/` | Call the services; hold no business logic of their own. |
| Agents | `src/nf_splice/agents/` | Provider-neutral engine, permissions, typed operations, state and adapters. |
| Skills | `skills/<name>/SKILL.md` | Canonical procedures for agents; packaged copies live in `src/nf_splice/agents/skills/`. |

### The three modes share one engine

- Manual mode is the CLI and the workspace (`nf-splice tui`, ADR-0067). *Ask
  AI* (`nf-splice ask`, or the workspace's AI dock) answers questions with
  read-only tools and never changes files. The workspace's
  `AgentCoordinator` owns agent work; closing the dock never stops it.
- AI-assisted and autonomous sessions run in
  `src/nf_splice/agents/engine.py`, a typed stage machine. Every agent action
  goes through `src/nf_splice/agents/operations.py`, the typed operation
  registry over the same services the CLI uses, mediated by
  `src/nf_splice/agents/toolbox.py` (permissions, budgets, staging, logging).
- A stage is complete only when its deterministic gate in
  `src/nf_splice/agents/stages.py` passes, and a layer stage also needs the
  agent's recorded review (`complete_review`, or an approved proposal). A
  review needs the stage's required evidence from
  `src/nf_splice/agents/review_scope.py`, inspected as nf-splice logged it,
  an assessment of the draft and cited support (ADR-0063). A passing gate
  never skips the review; model output is never validation.
- Where an integration stands is stated once, by
  `src/nf_splice/services/readiness.py` `lifecycle()` (ADR-0062): drafts
  valid, published, classified and ingestion ready are separate facts, and
  every interface reports them the same way. A build is never ingestion
  readiness.
- Agents author through `replace_draft` (whole draft or section, with the
  expected sha256) and `write_config`; a safe write is kept even when the
  content does not validate yet. Reasoning effort is provider-neutral
  (`ReasoningEffort` in `src/nf_splice/agents/protocol.py`); every adapter
  maps it to its real control or emits a notice.
- Orchestration, permissions, persistence and validation must not depend on a
  provider SDK. Provider code stays in `src/nf_splice/agents/providers/`
  (claude, openai, codex, opencode, scripted); each restricts the model to
  nf-splice's tools by configuration, proven by tests that attempt forbidden
  tools.
- Provider credentials live only in the user's configuration folder
  (`src/nf_splice/credentials.py`); never write them to a repository, a log,
  a test fixture or an archive.

### Permissions

Operations declare one permission each (`src/nf_splice/agents/permissions.py`):
`read`, `draft_edit`, `build`, `overwrite`, `external_tools`, `run_nextflow`,
`network`. `install`, `publish_external`, `credentials` and `human_consent`
can never be granted to an agent, and no operation exists for them. Do not add
operations that run Nextflow pipelines, install software, upload data or read
secrets. Autonomous decisions are recorded with origin `agent_autonomous` and
approval `agent_policy`, never as human review.

## Rules for changes

- Never make a discovery candidate's review status a validation error, and
  never seed a discoverable list empty to force a review queue. Validate
  the draft's content; report substantive gaps (unlisted modules,
  unresolved containers, unbound required inputs). The output catalogue is
  authored, not discovered: it starts empty, and route coverage is the
  `output_coverage` readiness dimension, not a draft error (ADR-0068).
- Infer no science deterministically: identity comes from documented keys
  only and people declare assays (ADR-0069).
- Re-running discovery never changes an existing draft or config.
- Change contract files only through the services; never hand-write
  `outputs.schema.json`, `outputs.yaml`, `bundle.json` or `analysis_output.json`.
- The output catalogue is the union of outputs a pipeline may publish across
  its routes. `analysis_output.json` lists only what one job published.
- Keep deterministic behaviour deterministic: no timestamps or randomness in
  rendered files.
- The word for Nextflow's own pipeline-metadata configuration block is
  reserved: use it only in the Nextflow parser and the glossary or ADRs.
- Use British English in code comments, messages and documentation.
- Write the ADR with the change (`docs/ARCHITECTURE_DECISIONS.md`) and add a
  row to the ledger in `docs/RELEASE_0.3.0.md`.

## Set up and check

```bash
. scripts/dev-env.sh
python -m venv .nf-splice-local/venv
. .nf-splice-local/venv/bin/activate
python -m pip install -e '.[dev]'
scripts/run-checks.sh
```

`scripts/run-checks.sh` runs pytest, ruff, ruff format, mypy, the dependency
check and the staged-path guard. Opt-in tests: `nextflow` (needs Nextflow
and Java), `live_agent` (needs approved Claude credentials),
`reference_pipeline` (`NF_SPLICE_BULK_RNASEQ` names a real pipeline
checkout), `rocrate_validator` (`NF_SPLICE_ROCRATE_VALIDATOR`) and `s3`
(`NF_SPLICE_S3_TEST=1` with a test bucket). Scripted providers test
orchestration only, never model reasoning. The Codex and OpenCode
lockdown tests run against local fake models when those programs are
installed (`NF_SPLICE_CODEX`, `NF_SPLICE_OPENCODE`).

After changing commands or contracts, regenerate the references:

```bash
python scripts/generate_cli_docs.py
python scripts/generate_schema_docs.py
python scripts/build_consumer_kit.py
```

`bundle-consumer-kit/` is for developers who build on bundles without
nf-splice (ingestion, web interfaces, data explorers, job launchers). When a
contract changes, regenerate it and update any of its skills whose keys
changed; `tests/test_consumer_kit.py` checks both.

After changing a skill in `skills/`, copy it to
`src/nf_splice/agents/skills/`; `tests/test_skills.py` fails on drift.

## Files and Git hygiene

- Temporary files, caches, sessions and reports go in the ignored
  `.nf-splice-local/` workspace (`. scripts/dev-env.sh` arranges this).
  Agent sessions in user repositories also live there, protected by their own
  `.gitignore`.
- Never commit private transcripts, credentials, example results or
  `.claude/` settings. `scripts/check_staged_paths.py` rejects
  development-only paths; run `git status` before committing.
- Fixtures under `tests/fixtures/` are byte-exact; do not reformat them.

## Skills

| Skill | Use it for |
| --- | --- |
| [`skills/nf-splice-integration/SKILL.md`](skills/nf-splice-integration/SKILL.md) | External coding agents (Codex, Claude Code, OpenCode): the whole integration through the CLI and direct draft edits |
| [`skills/nf-splice-authoring/SKILL.md`](skills/nf-splice-authoring/SKILL.md) | File-first authoring of every layer, in every mode |
| [`skills/nf-splice-agent-operations/SKILL.md`](skills/nf-splice-agent-operations/SKILL.md) | Investigation, revisions, approvals, reviews, blockers, reasoning effort |
| [`skills/nf-splice-assay-capabilities/SKILL.md`](skills/nf-splice-assay-capabilities/SKILL.md) | Identity evidence, free-text intake and assay capabilities |
| [`skills/nf-splice-input-access/SKILL.md`](skills/nf-splice-input-access/SKILL.md) | Lossless inputs and least-privilege access policies |
| [`skills/nf-splice-output-discovery/SKILL.md`](skills/nf-splice-output-discovery/SKILL.md) | Output catalogues across routes, examples, `analysis_output.json` |
| [`skills/nf-splice-components-images/SKILL.md`](skills/nf-splice-components-images/SKILL.md) | Module inventory, runtime-specific containers, image delivery |
| [`skills/nf-splice-execution-config/SKILL.md`](skills/nf-splice-execution-config/SKILL.md) | Profile metadata, native configs, site profiles without memory requests |
| [`skills/nf-splice-provenance/SKILL.md`](skills/nf-splice-provenance/SKILL.md) | The RO-Crate graph, archives and standards validation |
| [`skills/nf-splice-validation/SKILL.md`](skills/nf-splice-validation/SKILL.md) | Validation, readiness dimensions, recovery and optional checks |

nf-splice's embedded agents receive the relevant skills in every turn.
External coding agents use `nf-splice-integration`, installed in an
integration copy with `nf-splice skills install --agent codex|claude|opencode|all`
(`src/nf_splice/services/agent_skills.py`, ADR-0072); it drives the CLI and
edits drafts directly, never the session engine. The other skills can be
loaded from `skills/`, or after `nf-splice skills export --dest <directory>`.

## Definition of done

A change is done when its tests exercise real services and files, the checks
pass, the generated references are current, the ADR and ledger are updated,
and the documentation describes only what is implemented.
