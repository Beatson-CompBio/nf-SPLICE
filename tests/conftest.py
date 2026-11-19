"""Shared test isolation for repository fixtures."""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _isolate_git_discovery(
    tmp_path_factory: pytest.TempPathFactory,
) -> Iterator[None]:
    """Stop fixture repositories from discovering an enclosing Git checkout.

    Local development routes pytest's base temporary directory into the
    ignored ``.nf-splice-local/`` workspace inside the nf-SPLICE clone, so
    without a ceiling Git would report the clone's own remote and revision
    as fixture evidence.
    """
    previous = os.environ.get("GIT_CEILING_DIRECTORIES")
    os.environ["GIT_CEILING_DIRECTORIES"] = str(tmp_path_factory.getbasetemp())
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop("GIT_CEILING_DIRECTORIES", None)
        else:
            os.environ["GIT_CEILING_DIRECTORIES"] = previous


@pytest.fixture(autouse=True)
def _isolate_credentials(
    request: pytest.FixtureRequest,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Never read or write the person's real provider credentials in tests.

    Only an opted-in live provider test (marked ``live_agent``, with
    ``NF_SPLICE_LIVE_AGENT=1``) sees the real credentials; every other test
    stays isolated in the same run.
    """
    live = request.node.get_closest_marker("live_agent") is not None
    if live and os.environ.get("NF_SPLICE_LIVE_AGENT") == "1":
        return
    monkeypatch.setenv(
        "NF_SPLICE_CONFIG_DIR", str(tmp_path_factory.mktemp("nf-splice-config"))
    )
    for variable in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(variable, raising=False)
