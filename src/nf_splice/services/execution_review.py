"""Static analysis of a pipeline's resource configuration (read-only).

A navigation aid for authoring execution profiles, especially on clusters
whose scheduler rejects per-job memory requests (for example a Slurm site
where ``#SBATCH --mem`` must not be emitted and memory is allotted per CPU):

- the resources each ``withLabel`` / ``withName`` selector asks for;
- which modules use which labels;
- every use of ``task.memory`` in module scripts, and whether it is guarded
  against ``task.memory`` being ``null`` (an unguarded use fails at run time
  once a profile sets ``memory = null``; a guarded one may silently fall back
  to a small default);
- what one config sets: executor, ``memory = null`` coverage,
  ``NXF_EXECUTOR_MEM_GIGA_PER_CORE`` and memory flags in cluster options.

Groovy is never evaluated: values are read from the text, expressions that
are not simple numbers are kept verbatim, and nothing here proves what
Nextflow will do. Effective configuration needs Nextflow itself (an opt-in
check). People and agents read the original files to decide.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from nf_splice.layout import PUBLISHED_DIR

_IGNORED = {".git", ".splice-local", ".nf-splice-local", "work", ".nextflow"}
_SELECTOR = re.compile(r"\bwith(Label|Name)\s*:\s*(['\"]?)(?P<name>[^'\"{\n]+?)\2\s*\{")
_SETTING = re.compile(r"^\s*(cpus|memory|time)\s*=\s*(?P<value>.+?)\s*$", re.M)
_LABEL = re.compile(r"^\s*label\s+['\"]([^'\"]+)['\"]", re.M)
_PROCESS = re.compile(r"\bprocess\s+([A-Za-z0-9_]+)\s*\{")
_MEMORY_VALUE = re.compile(r"(\d+(?:\.\d+)?)\s*\.?\s*(TB|GB|MB|KB|G|M)\b", re.I)
_NUMBER = re.compile(r"\{\s*(\d+)\b|^\s*(\d+)\s*$|^(\d+)\b")
_TASK_MEMORY = re.compile(r"\btask\.memory\b")
_GUARD_INLINE = re.compile(
    r"task\.memory\s*\?(?!\.)|task\.memory\?\.|task\.memory\s*&&"
)
#: Null tests guard a use just as a bare ternary does: nf-core modules size
#: ``task.memory == null ? fallback : task.memory * n`` on one line, or split
#: the test, the ``?`` and the multiply across the lines of a check_max call.
_GUARD_NULLTEST = re.compile(
    r"task\.memory\s*(?:==|!=)\s*null\b|null\s*(?:==|!=)\s*task\.memory\b"
)
_GUARD_BLOCK = re.compile(r"if\s*\(\s*!?\s*task\.memory\s*\)")
_DEFINED = re.compile(r"\bdef\s+([A-Za-z_]\w*)\s*=.*task\.memory")


def _strip_comments(text: str) -> str:
    text = re.sub(
        r"/\*.*?\*/", lambda match: "\n" * match.group(0).count("\n"), text, flags=re.S
    )
    return re.sub(r"(?<!:)//.*", "", text)


def _block(text: str, opening: int) -> str:
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[opening + 1 : index]
    return text[opening + 1 :]


def memory_gb(expression: str) -> float | None:
    """GB in a simple memory expression (``{ 36.GB * task.attempt }``)."""
    match = _MEMORY_VALUE.search(expression)
    if match is None:
        return None
    value = float(match.group(1))
    unit = match.group(2).upper()
    return (
        value
        * {
            "TB": 1024,
            "GB": 1,
            "G": 1,
            "MB": 1 / 1024,
            "M": 1 / 1024,
            "KB": 1 / 1024**2,
        }[unit]
    )


def cpus_value(expression: str) -> int | None:
    """CPUs in a simple expression (``{ 6 * task.attempt }``, ``2``)."""
    match = _NUMBER.search(expression.strip())
    if match is None:
        return None
    return int(next(group for group in match.groups() if group))


@dataclass(slots=True)
class Selector:
    """Resources one process selector asks for (first attempt)."""

    kind: str
    name: str
    location: str
    cpus: str | None = None
    memory: str | None = None
    time: str | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "selector": f"with{self.kind}: {self.name}",
            "location": self.location,
            "cpus": self.cpus,
            "memory": self.memory,
            "time": self.time,
            "cpus_value": cpus_value(self.cpus) if self.cpus else None,
            "memory_gb": memory_gb(self.memory) if self.memory else None,
        }


@dataclass(slots=True)
class MemoryUse:
    """One ``task.memory`` use in a module script."""

    process: str | None
    location: str
    line: str
    guarded: bool
    derived: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "process": self.process,
            "location": self.location,
            "line": self.line,
            "guarded": self.guarded,
            "risk": (
                "a guard: with memory = null the module falls back to a derived "
                "default; check what that default does"
                if self.guarded
                else "unguarded: fails at run time when task.memory is null"
            ),
            "derived_uses": self.derived,
        }


def _files(root: Path, suffix: str) -> list[Path]:
    found = []
    for current, directories, names in os.walk(root, followlinks=False):
        directories[:] = sorted(
            name
            for name in directories
            if name not in _IGNORED
            and not (name == PUBLISHED_DIR and Path(current) == root)
        )
        for name in sorted(names):
            path = Path(current) / name
            if name.endswith(suffix) and not path.is_symlink():
                if "tests" in path.relative_to(root).parts[:-1]:
                    continue
                found.append(path)
    return found


def selectors(root: Path) -> list[Selector]:
    """Every ``withLabel``/``withName`` selector with resource settings."""
    found = []
    for path in _files(root, ".config"):
        relative = path.relative_to(root).as_posix()
        if relative.startswith(".splice-local/"):
            continue
        text = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        for match in _SELECTOR.finditer(text):
            body = _block(text, match.end() - 1)
            settings = {
                item.group(1): item.group("value") for item in _SETTING.finditer(body)
            }
            if not settings:
                continue
            found.append(
                Selector(
                    "Label" if match.group(1) == "Label" else "Name",
                    match.group("name").strip(),
                    f"{relative}:{text.count(chr(10), 0, match.start()) + 1}",
                    settings.get("cpus"),
                    settings.get("memory"),
                    settings.get("time"),
                )
            )
    return found


def process_labels(root: Path) -> dict[str, dict[str, Any]]:
    """Process name -> its labels and module file."""
    found: dict[str, dict[str, Any]] = {}
    for path in _files(root, ".nf"):
        relative = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in _PROCESS.finditer(text):
            body = _block(text, match.end() - 1)
            found[match.group(1)] = {
                "labels": _LABEL.findall(body),
                "location": f"{relative}:{text.count(chr(10), 0, match.start()) + 1}",
            }
    return found


def memory_uses(root: Path) -> list[MemoryUse]:
    """Every ``task.memory`` use in workflow code, with its guard status."""
    found = []
    for path in _files(root, ".nf"):
        relative = path.relative_to(root).as_posix()
        raw = path.read_text(encoding="utf-8", errors="replace")
        lines = raw.splitlines()
        process = None
        for number, line in enumerate(lines, start=1):
            started = _PROCESS.search(line)
            if started:
                process = started.group(1)
            code = re.sub(r"(?<!:)//.*", "", line)
            if not _TASK_MEMORY.search(code):
                continue
            if _GUARD_BLOCK.search(code) and not re.search(r"task\.memory\.", code):
                continue
            window = "\n".join(lines[max(0, number - 9) : number])
            guarded = bool(
                _GUARD_INLINE.search(code)
                or _GUARD_NULLTEST.search(code)
                or _GUARD_BLOCK.search(window)
                or _GUARD_NULLTEST.search(window)
            )
            derived = []
            defined = _DEFINED.search(code)
            if defined:
                name = defined.group(1)
                derived = [
                    f"{relative}:{later}: {lines[later - 1].strip()[:160]}"
                    for later in range(number + 1, min(len(lines), number + 40) + 1)
                    if re.search(rf"\b{name}\b", lines[later - 1])
                ][:5]
            found.append(
                MemoryUse(
                    process,
                    f"{relative}:{number}",
                    line.strip()[:200],
                    guarded,
                    derived,
                )
            )
    return found


def config_facts(text: str) -> dict[str, Any]:
    """What one Nextflow config sets that matters for resource requests."""
    code = _strip_comments(text)
    executor = re.findall(r"\bexecutor\s*=\s*['\"]([A-Za-z0-9_-]+)['\"]", code)
    nulls = []
    for match in _SELECTOR.finditer(code):
        body = _block(code, match.end() - 1)
        if re.search(r"^\s*memory\s*=\s*null\b", body, re.M):
            nulls.append(f"with{match.group(1)}: {match.group('name').strip()}")
    process_null = bool(
        re.search(r"process\s*\{[^{}]*?^\s*memory\s*=\s*null\b", code, re.M | re.S)
        or re.search(r"\bprocess\.memory\s*=\s*null\b", code)
    )
    per_core = re.search(
        r"NXF_EXECUTOR_MEM_GIGA_PER_CORE\s*=\s*['\"]?(\d+(?:\.\d+)?)", code
    )
    memory_flags = re.findall(r"--mem(?:-per-cpu)?\b[^'\"\s]*", code)
    return {
        "executor": executor[-1] if executor else None,
        "memory_null_selectors": nulls,
        "memory_null_for_every_process": process_null or "withName: .*" in nulls,
        "gigabytes_per_core": float(per_core.group(1)) if per_core else None,
        "memory_flags_in_cluster_options": memory_flags,
    }


def analyse_execution(
    repository_root: str | Path, config_text: str | None = None
) -> dict[str, Any]:
    """Resources, labels, memory uses and (optionally) one config's settings.

    With a config whose memory is null and a known memory per core, each
    selector also gets the CPUs that would give it its intended memory:
    ``ceil(memory_gb / gigabytes_per_core)``, never fewer than it asked for.
    """
    root = Path(repository_root).resolve()
    found = [item.to_json() for item in selectors(root)]
    labels = process_labels(root)
    uses = [item.to_json() for item in memory_uses(root)]
    report: dict[str, Any] = {
        "selectors": found,
        "processes_by_label": {
            label: sorted(
                name for name, item in labels.items() if label in item["labels"]
            )
            for label in sorted(
                {label for item in labels.values() for label in item["labels"]}
            )
        },
        "task_memory_uses": uses,
        "unguarded_task_memory": [item for item in uses if not item["guarded"]],
        "notes": [
            "Values are read from configuration text; expressions are not "
            "evaluated and later config files may override them. Check the "
            "effective configuration with Nextflow before relying on it."
        ],
    }
    if config_text is not None:
        facts = config_facts(config_text)
        report["config"] = facts
        per_core = facts["gigabytes_per_core"]
        if facts["memory_null_for_every_process"] and per_core:
            sizing = []
            for item in found:
                memory = item["memory_gb"]
                if memory is None:
                    continue
                needed = max(math.ceil(memory / per_core), item["cpus_value"] or 1)
                sizing.append(
                    {
                        "selector": item["selector"],
                        "intended_memory_gb": memory,
                        "declared_cpus": item["cpus_value"],
                        "cpus_for_intended_memory": needed,
                        "memory_at_those_cpus_gb": needed * per_core,
                    }
                )
            report["cpu_sizing"] = sizing
        if facts["memory_null_for_every_process"] and report["unguarded_task_memory"]:
            report["notes"].append(
                "memory = null applies to every process, and some modules use "
                "task.memory without a guard: those tasks fail at run time unless "
                "their memory is restored for them or the modules are adapted"
            )
    return report
