"""Optional external checkers (nf-core lint) behind explicit permissions.

nf-splice never requires nf-core or Nextflow. This registry detects whether a
supported checker is installed and applicable, and runs it only when every
permission it needs has been granted. A checker that is missing, not
applicable, not permitted or unsupported is reported with its reason; it is
never reported as passed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

#: Permissions an external checker may need. They mirror the agent
#: permission names so a session policy and the CLI share one vocabulary.
EXTERNAL_TOOLS = "external_tools"
RUN_NEXTFLOW = "run_nextflow"
NETWORK = "network"

Runner = Callable[..., subprocess.CompletedProcess[str]]


class CheckStatus(str, Enum):
    """Outcome of one optional check."""

    PASSED = "passed"
    PASSED_WITH_WARNINGS = "passed_with_warnings"
    FAILED = "failed"
    ERROR = "error"
    NOT_APPLICABLE = "not_applicable"
    NOT_RUN = "not_run"


@dataclass(frozen=True, slots=True)
class CheckResult:
    """What happened when an optional check was considered."""

    name: str
    status: CheckStatus
    reason: str
    tool: str
    version: str | None = None
    command: tuple[str, ...] = ()
    counts: dict[str, int] = field(default_factory=dict)
    failures: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    output_excerpt: str = ""

    def to_json(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "reason": self.reason,
            "tool": self.tool,
            "version": self.version,
            "command": list(self.command),
            "counts": dict(self.counts),
            "failures": list(self.failures),
            "warnings": list(self.warnings),
            "output_excerpt": self.output_excerpt,
        }


@dataclass(frozen=True, slots=True)
class ToolAvailability:
    """Whether an external tool is on ``PATH`` (detected, never executed)."""

    name: str
    installed: bool
    path: str | None

    def to_json(self) -> dict[str, Any]:
        return {"name": self.name, "installed": self.installed, "path": self.path}


def detect_tools() -> tuple[ToolAvailability, ...]:
    """Detect nf-core and Nextflow by ``PATH`` lookup only."""
    found = []
    for name in ("nf-core", "nextflow"):
        location = shutil.which(name)
        found.append(ToolAvailability(name, location is not None, location))
    return tuple(found)


def is_nf_core_pipeline(root: Path) -> tuple[bool, str]:
    """An nf-core pipeline has ``.nf-core.yml`` or an ``nf-core/`` name."""
    if (root / ".nf-core.yml").is_file() or (root / ".nf-core.yaml").is_file():
        return True, ".nf-core.yml is present"
    config = root / "nextflow.config"
    if config.is_file():
        text = config.read_text(encoding="utf-8", errors="replace")
        if re.search(r"\bname\s*=\s*['\"]nf-core/", text):
            return True, "the pipeline name in nextflow.config starts with nf-core/"
    return False, "not an nf-core pipeline (no .nf-core.yml or nf-core/ name)"


_SUPPORTED_NF_CORE = ((3, 0), (5, 0))
_NF_CORE_PERMISSIONS = (EXTERNAL_TOOLS, RUN_NEXTFLOW, NETWORK)


def _version(text: str) -> str | None:
    match = re.search(r"version\s+(\d+(?:\.\d+)+)", text)
    return match.group(1) if match else None


def _supported(version: str) -> bool:
    parts = tuple(int(item) for item in version.split(".")[:2])
    low, high = _SUPPORTED_NF_CORE
    return low <= parts < high


def _excerpt(text: str, limit: int = 2000) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[-limit:]


def _lint_entries(document: dict[str, Any], key: str) -> tuple[str, ...]:
    items = document.get(key, [])
    entries = []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, list | tuple) and item:
                entries.append(": ".join(str(part) for part in item[:2]))
            else:
                entries.append(str(item))
    return tuple(entries[:50])


def nf_core_lint(
    root: Path,
    *,
    permitted: Collection[str],
    runner: Runner = subprocess.run,
    timeout: float = 900.0,
) -> CheckResult:
    """Run ``nf-core pipelines lint`` when applicable, installed and allowed."""
    name, tool = "nf-core pipelines lint", "nf-core"
    applies, why = is_nf_core_pipeline(root)
    if not applies:
        return CheckResult(name, CheckStatus.NOT_APPLICABLE, why, tool)
    executable = shutil.which("nf-core")
    if executable is None:
        return CheckResult(
            name, CheckStatus.NOT_RUN, "nf-core is not installed on PATH", tool
        )
    missing = [item for item in _NF_CORE_PERMISSIONS if item not in permitted]
    if missing:
        return CheckResult(
            name,
            CheckStatus.NOT_RUN,
            "not permitted: nf-core lint runs an external tool that calls "
            "`nextflow config` and may contact the network; grant "
            + ", ".join(missing),
            tool,
        )
    if shutil.which("nextflow") is None:
        return CheckResult(
            name,
            CheckStatus.NOT_RUN,
            "nf-core lint needs Nextflow on PATH (it runs `nextflow config`), "
            "and Nextflow is not installed",
            tool,
        )
    environment = dict(os.environ) | {
        "NFCORE_NO_VERSION_CHECK": "1",
        "NO_COLOR": "1",
        "TERM": "dumb",
    }
    probe = runner(
        [executable, "--version"],
        capture_output=True,
        text=True,
        timeout=60,
        env=environment,
        check=False,
    )
    version = _version(probe.stdout + probe.stderr)
    if version is None:
        return CheckResult(
            name,
            CheckStatus.ERROR,
            "could not read the nf-core version",
            tool,
            output_excerpt=_excerpt(probe.stdout + probe.stderr),
        )
    if not _supported(version):
        return CheckResult(
            name,
            CheckStatus.NOT_RUN,
            f"nf-core {version} is not a supported version (3.x or 4.x)",
            tool,
            version=version,
        )
    with tempfile.TemporaryDirectory(prefix="nf-splice-lint-") as scratch:
        report = Path(scratch) / "lint.json"
        command: Sequence[str] = (
            executable,
            "pipelines",
            "lint",
            "--dir",
            str(root),
            "--json",
            str(report),
        )
        try:
            completed = runner(
                list(command),
                capture_output=True,
                text=True,
                timeout=timeout,
                env=environment,
                cwd=scratch,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return CheckResult(
                name,
                CheckStatus.ERROR,
                f"nf-core lint did not finish within {int(timeout)} s",
                tool,
                version=version,
                command=tuple(command),
            )
        output = _excerpt(completed.stdout + completed.stderr)
        if not report.is_file():
            return CheckResult(
                name,
                CheckStatus.ERROR,
                f"nf-core lint exited with {completed.returncode} without a report",
                tool,
                version=version,
                command=tuple(command),
                output_excerpt=output,
            )
        document = json.loads(report.read_text(encoding="utf-8"))
    counts = {
        key: int(document.get(f"num_tests_{key}", 0) or 0)
        for key in ("pass", "warned", "failed", "ignored")
    }
    failures = _lint_entries(document, "tests_failed")
    warnings = _lint_entries(document, "tests_warned")
    if counts["failed"] or completed.returncode != 0:
        status = CheckStatus.FAILED
        reason = f"{counts['failed']} failed, {counts['warned']} warned"
    elif counts["warned"]:
        status = CheckStatus.PASSED_WITH_WARNINGS
        reason = f"{counts['pass']} passed, {counts['warned']} warned"
    else:
        status = CheckStatus.PASSED
        reason = f"{counts['pass']} passed"
    return CheckResult(
        name,
        status,
        reason,
        tool,
        version=version,
        command=tuple(command),
        counts=counts,
        failures=failures,
        warnings=warnings,
        output_excerpt=output,
    )


def run_optional_checks(
    repository_root: str | Path,
    *,
    permitted: Collection[str] = (),
    runner: Runner = subprocess.run,
) -> tuple[CheckResult, ...]:
    """Every registered optional check, run or explained."""
    root = Path(repository_root).resolve()
    return (nf_core_lint(root, permitted=permitted, runner=runner),)
