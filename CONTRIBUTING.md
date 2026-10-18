# Contributing to nf-SPLICE

## Set up

Clone the repository, then from its root:

```bash
. scripts/dev-env.sh
python -m venv .nf-splice-local/venv
. .nf-splice-local/venv/bin/activate
python -m pip install -e '.[dev]'
```

`scripts/dev-env.sh` sends every cache, temporary file, test output, report
and workspace state to the ignored `.nf-splice-local/` directory inside the
clone. Source it in each new shell.

Install the staged-file guard as a Git hook:

```bash
ln -s ../../scripts/pre-commit .git/hooks/pre-commit
```

It rejects commits that include development-only files.

## Check your changes

```bash
scripts/run-checks.sh
```

This runs the test suite, `ruff`, `mypy`, the dependency check and the
staged-file guard. Two kinds of test are opt-in and skipped by default:

| Marker | Needs | Enable with |
| --- | --- | --- |
| `nextflow` | A local Nextflow installation | `NF_SPLICE_NEXTFLOW_TESTS=1 pytest -m nextflow` |
| `live_agent` | Approved Claude credentials | `NF_SPLICE_LIVE_AGENT=1 pytest -m live_agent` |

## Generated documentation

Two references and the bundle consumer kit's definitions and examples are
generated and checked by the test suite. Regenerate them after changing
commands or contract definitions:

```bash
python scripts/generate_cli_docs.py
python scripts/generate_schema_docs.py
python scripts/build_consumer_kit.py
```

Field descriptions for the schema reference live in
`docs/schemas/fields.yaml`. The consumer kit's skills
(`bundle-consumer-kit/skills/`) are written by hand; `tests/test_consumer_kit.py`
fails when one names a key the contracts do not define.

## Workspace tests and screenshots

`tests/test_tui.py`, `tests/test_tui_agents.py`, `tests/test_tui_themes.py`
and `tests/test_tui_performance.py` drive the workspace headlessly through
its widgets over real services and files. To look at what they render, save
SVG screenshots and open them in a browser:

```bash
NF_SPLICE_SCREENSHOTS=.nf-splice-local/reports/screenshots pytest tests/test_tui.py
```

`NF_SPLICE_LATENCY_REPORT=.nf-splice-local/reports/latency.json` records the
measured latencies of `tests/test_tui_performance.py`.

## Design decisions

Substantive changes need an architecture decision record in
[`docs/ARCHITECTURE_DECISIONS.md`](docs/ARCHITECTURE_DECISIONS.md), written
with the change, and a row in the release ledger. Coding agents (and people)
should read [`AGENTS.md`](AGENTS.md); the run-time agent contract is in
[`docs/AGENTS.md`](docs/AGENTS.md).

## Agent skills

The canonical skills are in `skills/<name>/SKILL.md`. After changing one,
copy it into the package so the runtime and the wheel use the same text:

```bash
cp skills/nf-splice-authoring/SKILL.md src/nf_splice/agents/skills/nf-splice-authoring/SKILL.md
```

`tests/test_skills.py` fails when the two copies differ, a section is
missing, or a skill names a tool, value, command or path that does not
exist.

## Writing documentation

User documentation lives in `docs/guide/`, with `docs/USAGE.md` as its
index. Every `nf-splice` command shown in a `bash` block must exist, and
every relative link must resolve; `tests/test_docs.py` checks both.
