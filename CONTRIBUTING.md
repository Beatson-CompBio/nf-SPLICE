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
and wizard session to the ignored `.nf-splice-local/` directory inside the
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

Two references are generated and checked by the test suite. Regenerate them
after changing commands or contract definitions:

```bash
python scripts/generate_cli_docs.py
python scripts/generate_schema_docs.py
```

Field descriptions for the schema reference live in
`docs/schemas/fields.yaml`.

## Wizard snapshots

`tests/test_tui.py` compares each wizard step with reviewed text snapshots
in `tests/snapshots/tui/`. After an intended change to the wizard, update
them and review the difference:

```bash
NF_SPLICE_UPDATE_SNAPSHOTS=1 pytest tests/test_tui.py
```

## Design decisions

Substantive changes need an architecture decision record in
[`docs/ARCHITECTURE_DECISIONS.md`](docs/ARCHITECTURE_DECISIONS.md), written
with the change, and a row in the release ledger. The developer contract for
assistant integrations is in [`docs/AGENTS.md`](docs/AGENTS.md).

## Writing documentation

User documentation lives in `docs/guide/`, with `docs/USAGE.md` as its
index. Every `nf-splice` command shown in a `bash` block must exist, and
every relative link must resolve; `tests/test_docs.py` checks both.
