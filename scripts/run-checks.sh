#!/bin/sh
# Full local quality gate; all outputs stay inside /.nf-splice-local/.
set -eu
. scripts/dev-env.sh
python -m pip check
python -m pytest -q -p no:cacheprovider \
    --basetemp=.nf-splice-local/tests/tmp \
    --junitxml=.nf-splice-local/tests/junit.xml "$@"
ruff check src tests scripts
ruff format --check src tests scripts
mypy
nf-splice --version
python scripts/check_staged_paths.py
