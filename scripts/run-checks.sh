#!/bin/sh
# Full local quality gate; all outputs stay inside /.nf-splice-local/.
set -eu
. scripts/dev-env.sh
# uv-created environments carry no pip; uv checks the same metadata.
if python -m pip --version >/dev/null 2>&1; then
    python -m pip check
else
    uv pip check --python "$(command -v python)"
fi
python -m pytest -q -p no:cacheprovider \
    --basetemp=.nf-splice-local/tests/tmp \
    --junitxml=.nf-splice-local/tests/junit.xml "$@"
ruff check src tests scripts
ruff format --check src tests scripts
mypy
nf-splice --version
python scripts/check_staged_paths.py
