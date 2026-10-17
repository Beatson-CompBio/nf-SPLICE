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
from collections.abc import Callable, Collection, Mapping, Sequence
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
    """Detect nf-core, Nextflow and the RO-Crate validator on ``PATH``."""
    found = []
    for name in ("nf-core", "nextflow", "rocrate-validator"):
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


#: The RO-Crate profile the complete-pipeline archive claims.
ROCRATE_PROFILE = "workflow-ro-crate-1.0"
ROCRATE_SUPPORTED = re.compile(r"^0\.(?:1[0-9]|[89])\.")


def _crate_root(
    root: Path, target: Path, crate: Mapping[str, Any] | None = None
) -> None:
    """Lay the pipeline out as its archive would be: crate at the root.

    ``crate`` replaces the published crate, to check a draft graph before it
    is built.
    """
    from nf_splice.services.export import _pipeline_members

    members, _excluded = _pipeline_members(root)
    for relative, path in members:
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
    if crate is not None:
        (target / "ro-crate-metadata.json").write_text(
            json.dumps(crate, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return
    canonical = root / "splice" / "ro-crate-metadata.json"
    shutil.copyfile(canonical, target / "ro-crate-metadata.json")


def rocrate_validation(
    root: Path,
    *,
    permitted: Collection[str],
    runner: Runner = subprocess.run,
    timeout: float = 600.0,
    executable_name: str = "rocrate-validator",
    crate: Mapping[str, Any] | None = None,
) -> CheckResult:
    """Validate the pipeline's Workflow RO-Crate with ``rocrate-validator``.

    Runs on a temporary copy laid out exactly as the complete-pipeline
    archive (the published crate at its root). The validator fetches
    profile contexts over the network unless its cache is warm; without the
    ``network`` permission it runs ``--offline`` and reports what it could
    not check.
    """
    name, tool = f"RO-Crate {ROCRATE_PROFILE}", "rocrate-validator"
    if crate is None and not (root / "splice" / "ro-crate-metadata.json").is_file():
        return CheckResult(
            name, CheckStatus.NOT_APPLICABLE, "no published RO-Crate yet", tool
        )
    executable = shutil.which(executable_name) or os.environ.get(
        "NF_SPLICE_ROCRATE_VALIDATOR"
    )
    if not executable:
        return CheckResult(
            name,
            CheckStatus.NOT_RUN,
            "rocrate-validator is not installed (pip install roc-validator; "
            "nf-splice never installs it)",
            tool,
        )
    if EXTERNAL_TOOLS not in permitted:
        return CheckResult(
            name,
            CheckStatus.NOT_RUN,
            f"not permitted: grant {EXTERNAL_TOOLS} to run the RO-Crate validator",
            tool,
        )
    probe = runner(
        [executable, "--version"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    found = re.search(
        r"rocrate-validator\s+(?:version\s+)?(\d+(?:\.\d+)+)",
        probe.stdout + probe.stderr,
    )
    version = found.group(1) if found else None
    if version is None or not ROCRATE_SUPPORTED.match(version):
        return CheckResult(
            name,
            CheckStatus.NOT_RUN,
            f"rocrate-validator {version or 'of unknown version'} is not a "
            "supported version (0.8 to 0.19)",
            tool,
            version=version,
        )
    with tempfile.TemporaryDirectory(prefix="nf-splice-rocrate-") as scratch:
        layout = Path(scratch) / "crate"
        report = Path(scratch) / "report.json"
        _crate_root(root, layout, crate)
        command: list[str] = [
            executable,
            "validate",
            "-p",
            ROCRATE_PROFILE,
            "-f",
            "json",
            "-o",
            str(report),
            "--no-paging",
        ]
        if NETWORK not in permitted:
            command.append("--offline")
        command.append(str(layout))
        try:
            completed = runner(
                command,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=scratch,
                check=False,
                env=dict(os.environ) | {"NO_COLOR": "1", "TERM": "dumb"},
            )
        except subprocess.TimeoutExpired:
            return CheckResult(
                name,
                CheckStatus.ERROR,
                f"the validator did not finish within {int(timeout)} s",
                tool,
                version=version,
                command=tuple(command),
            )
        output = _excerpt(completed.stdout + completed.stderr)
        if not report.is_file():
            return CheckResult(
                name,
                CheckStatus.ERROR,
                f"the validator exited with {completed.returncode} without a report"
                + ("" if NETWORK in permitted else " (offline: is its cache warm?)"),
                tool,
                version=version,
                command=tuple(command),
                output_excerpt=output,
            )
        document = json.loads(report.read_text(encoding="utf-8"))
    issues = [
        f"{(item.get('check') or {}).get('identifier', '?')}: "
        f"{' '.join(str(item.get('message', '')).split())[:300]}"
        if isinstance(item.get("check"), dict)
        else " ".join(str(item.get("message", "")).split())[:300]
        for item in document.get("issues") or []
        if isinstance(item, dict)
    ]
    passed = bool(document.get("passed"))
    return CheckResult(
        name,
        CheckStatus.PASSED if passed else CheckStatus.FAILED,
        f"the pipeline archive conforms to {ROCRATE_PROFILE} (required checks)"
        if passed
        else f"{len(issues)} requirement(s) not met",
        tool,
        version=version,
        command=tuple(command),
        failures=tuple(issues),
        output_excerpt=output,
    )


def nextflow_config_check(
    root: Path,
    *,
    permitted: Collection[str],
    profile_config: str | None = None,
    runner: Runner = subprocess.run,
    timeout: float = 300.0,
) -> CheckResult:
    """Ask Nextflow for the effective configuration with one profile config.

    ``nextflow config`` evaluates the pipeline's and the profile's Groovy
    configuration without running the pipeline or submitting jobs, but it
    does execute that configuration code, so it needs the ``run_nextflow``
    permission. The effective process settings are scanned for a memory
    request that would reach the scheduler.
    """
    name, tool = "nextflow config", "nextflow"
    executable = shutil.which("nextflow")
    if executable is None:
        return CheckResult(name, CheckStatus.NOT_RUN, "Nextflow is not installed", tool)
    if RUN_NEXTFLOW not in permitted:
        return CheckResult(
            name,
            CheckStatus.NOT_RUN,
            f"not permitted: `nextflow config` evaluates configuration code; grant "
            f"{RUN_NEXTFLOW}",
            tool,
        )
    if not (root / "nextflow.config").is_file():
        return CheckResult(name, CheckStatus.NOT_APPLICABLE, "no nextflow.config", tool)
    command = [executable, "config", "-flat", str(root)]
    if profile_config:
        command[2:2] = ["-c", str(root / profile_config)]
    try:
        completed = runner(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=root,
            check=False,
            env=dict(os.environ) | {"NXF_OFFLINE": "true", "NO_COLOR": "1"},
        )
    except subprocess.TimeoutExpired:
        return CheckResult(
            name,
            CheckStatus.ERROR,
            f"nextflow config did not finish within {int(timeout)} s",
            tool,
            command=tuple(command),
        )
    output = completed.stdout
    if "Java Runtime" in completed.stderr + output or "needs a Java" in (
        completed.stderr + output
    ):
        return CheckResult(
            name,
            CheckStatus.NOT_RUN,
            "Nextflow is installed but cannot start: no Java runtime was found",
            tool,
            command=tuple(command),
        )
    if completed.returncode != 0:
        return CheckResult(
            name,
            CheckStatus.FAILED,
            "Nextflow could not evaluate the configuration",
            tool,
            command=tuple(command),
            output_excerpt=_excerpt(completed.stdout + completed.stderr),
        )
    memory = sorted(
        {
            line.split("=", 1)[0].strip()
            for line in output.splitlines()
            if re.match(r"^\s*process\.(?:.*\.)?memory\s*=\s*(?!null\b)", line)
        }
    )
    warnings = tuple(f"effective memory request: {item}" for item in memory)
    return CheckResult(
        name,
        CheckStatus.PASSED_WITH_WARNINGS if warnings else CheckStatus.PASSED,
        "the configuration evaluates"
        + (f"; {len(warnings)} memory setting(s) remain" if warnings else ""),
        tool,
        command=tuple(command),
        warnings=warnings,
        output_excerpt=_excerpt(output),
    )


def run_optional_checks(
    repository_root: str | Path,
    *,
    permitted: Collection[str] = (),
    runner: Runner = subprocess.run,
) -> tuple[CheckResult, ...]:
    """Every registered optional check, run or explained."""
    root = Path(repository_root).resolve()
    return (
        nf_core_lint(root, permitted=permitted, runner=runner),
        rocrate_validation(root, permitted=permitted, runner=runner),
    )
