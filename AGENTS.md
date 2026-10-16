# Working on nf-splice

Instructions for anyone, human or coding agent, who changes this repository.
For how nf-splice's own agents work at run time, see
[`docs/AGENTS.md`](docs/AGENTS.md).

## What nf-splice is

nf-splice prepares a Nextflow pipeline for the SPLICE platform. It reads the
pipeline repository, helps a person review what it finds, and publishes a
validated SPLICE workflow bundle in `splice/`. People can do the work
themselves (manual), with an agent that proposes and waits for approval
(AI-assisted), or let an agent do it within an approved scope (autonomous).

## Architecture and sources of truth

| Concern | Where | Rule |
| --- | --- | --- |
| Decisions | `docs/ARCHITECTURE_DECISIONS.md` | Current ADRs govern the code. A changed decision needs a new ADR. |
| Contracts | `src/nf_splice/contracts/` | Five versioned JSON Schema families; `docs/schemas/` is generated from them. |
| Authoring state | `.splice-local/drafts/*.draft.yaml` and `.review.json` sidecars | The only editable source. Published files are built from it. |
| Deterministic services | `src/nf_splice/layers/`, `src/nf_splice/services/`, `src/nf_splice/inspectors/`, `src/nf_splice/runtime/` | The only writers and validators of SPLICE files, in every mode. |
| Interfaces | `src/nf_splice/cli.py`, `src/nf_splice/interfaces/tui/` | Call the services; hold no business logic of their own. |
| Agents | `src/nf_splice/agents/` | Provider-neutral engine, permissions, typed operations, state and adapters. |
| Skills | `skills/<name>/SKILL.md` | Canonical procedures for agents; packaged copies live in `src/nf_splice/agents/skills/`. |

### The three modes share one engine

- Manual mode is the CLI and the wizard. *Ask AI* (`nf-splice ask`, Ctrl+A in
  the wizard) answers questions with read-only tools and never changes files.
- AI-assisted and autonomous sessions run in
  `src/nf_splice/agents/engine.py`, a typed stage machine. Every agent action
  goes through `src/nf_splice/agents/operations.py`, the typed operation
  registry over the same services the CLI uses, mediated by
  `src/nf_splice/agents/toolbox.py` (permissions, budgets, staging, logging).
- A stage is complete only when its deterministic gate in
  `src/nf_splice/agents/stages.py` passes. Never treat model output as
  validation.
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
check and the staged-path guard. Opt-in tests: `nextflow` (needs Nextflow)
and `live_agent` (needs approved Claude credentials). The Codex and OpenCode
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
| [`skills/nf-splice-authoring/SKILL.md`](skills/nf-splice-authoring/SKILL.md) | Integrating a pipeline layer by layer |
| [`skills/nf-splice-output-discovery/SKILL.md`](skills/nf-splice-output-discovery/SKILL.md) | Output catalogues across routes, examples, `analysis_output.json` |
| [`skills/nf-splice-validation/SKILL.md`](skills/nf-splice-validation/SKILL.md) | Validation, assessment and optional nf-core checks |
| [`skills/nf-splice-agent-operations/SKILL.md`](skills/nf-splice-agent-operations/SKILL.md) | Manual help, assisted sessions and autonomous runs |

nf-splice's embedded agents receive the relevant skills in every turn.
External coding agents can load them from `skills/`, or after
`nf-splice skills export --dest <directory>` from wherever their tool
discovers skills.

## Definition of done

A change is done when its tests exercise real services and files, the checks
pass, the generated references are current, the ADR and ledger are updated,
and the documentation describes only what is implemented.
