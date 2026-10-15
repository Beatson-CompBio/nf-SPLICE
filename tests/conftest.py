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
