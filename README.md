# nf-SPLICE

CLI and TUI toolkit for building, validating, and maintaining the SPLICE
platform integration layer for Nextflow pipelines.

## Compatibility

nf-splice supports Python 3.10 through 3.14.

The package does not depend on nf-core internals. The compatibility suite tests
coexistence with nf-core 4.0.2 on Python 3.10, the minimum Python version
supported by both packages.

## Installation

    python -m pip install .
    nf-splice --version

## Development

    python -m pip install -e '.[dev]'
    pytest
    ruff check .
    ruff format --check .
    mypy
    python -m build

Step 1 establishes only the package and compatibility baseline. Authoring,
inspection, TUI, and generation behaviour will be introduced in later,
separately reviewed steps.
