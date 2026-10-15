# shellcheck shell=sh
# Source from the repository root: `. scripts/dev-env.sh`
#
# Routes every project-generated temporary file, cache, session and report
# into the ignored in-repository workspace /.nf-splice-local/.
if [ ! -f pyproject.toml ] || [ ! -d src/nf_splice ]; then
    echo "source scripts/dev-env.sh from the nf-SPLICE repository root" >&2
    return 1 2>/dev/null || exit 1
fi
mkdir -p .nf-splice-local/agent .nf-splice-local/tmp .nf-splice-local/tests \
    .nf-splice-local/logs .nf-splice-local/cache .nf-splice-local/sessions \
    .nf-splice-local/reports .nf-splice-local/fixtures
chmod 700 .nf-splice-local .nf-splice-local/agent .nf-splice-local/tmp
export NF_SPLICE_REPO_ROOT="$PWD"
export TMPDIR="$PWD/.nf-splice-local/tmp"
export TMP="$TMPDIR" TEMP="$TMPDIR"
export XDG_CACHE_HOME="$PWD/.nf-splice-local/cache"
export XDG_STATE_HOME="$PWD/.nf-splice-local/cache/state"
export XDG_CONFIG_HOME="$PWD/.nf-splice-local/cache/config"
export PIP_CACHE_DIR="$PWD/.nf-splice-local/cache/pip"
export UV_CACHE_DIR="$PWD/.nf-splice-local/cache/uv"
export RUFF_CACHE_DIR="$PWD/.nf-splice-local/cache/ruff"
export MYPY_CACHE_DIR="$PWD/.nf-splice-local/cache/mypy"
export COVERAGE_FILE="$PWD/.nf-splice-local/tests/.coverage"
export NF_SPLICE_SESSION_DIR="$PWD/.nf-splice-local/sessions"
export NF_SPLICE_AUDIT_DIR="$PWD/.nf-splice-local/cache/audit"
export PYTHONDONTWRITEBYTECODE=1
if [ -f .nf-splice-local/venv/bin/activate ]; then
    . .nf-splice-local/venv/bin/activate
fi
