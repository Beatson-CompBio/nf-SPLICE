"""The beginner-friendly path-pattern builder (pure functions).

A person types an example relative path and says, for each part, whether it
is fixed text or where it varies (any name, the sample, the run, any depth).
The builder writes the anchored pattern the output contract expects, using
the contract's own placeholders (``{sample}``, ``{run}``, ``{any}``,
``{anypath}``) and escaping literal text. Nothing is guessed: every part is
literal until the person marks it as varying. Arbitrary patterns stay
editable in the advanced field and are checked the same way.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from nf_splice.domain import expand_output_path_pattern

LITERAL = "literal"
ANY = "any"
SAMPLE = "sample"
RUN = "run"
ANY_WITH_SUFFIX = "any_suffix"
SAMPLE_WITH_SUFFIX = "sample_suffix"
ANYPATH = "anypath"

#: The choices offered for one path part, in order.
KINDS = (
    (LITERAL, "exactly this text"),
    (ANY, "any name"),
    (SAMPLE, "the sample name"),
    (RUN, "the run name"),
    (SAMPLE_WITH_SUFFIX, "the sample name, then the rest as shown"),
    (ANY_WITH_SUFFIX, "any name, then the rest as shown"),
    (ANYPATH, "any number of folders and files (last part only)"),
)

_SPECIAL = re.compile(r"([.^$*+?{}\[\]\\|()])")


def escape(text: str) -> str:
    """Escape only the characters that are special in a regular expression."""
    return _SPECIAL.sub(r"\\\1", text)


def split_example(example: str) -> list[str]:
    """The parts of a relative example path (leading ./ and slashes dropped)."""
    text = example.strip().removeprefix("./").strip("/")
    return [part for part in text.split("/") if part]


def suffix_of(part: str) -> str:
    """What follows the varying name: from the first '.', else ''."""
    position = part.find(".")
    return part[position:] if position > 0 else ""


@dataclass(frozen=True, slots=True)
class Part:
    text: str
    kind: str = LITERAL


def build_pattern(parts: Sequence[Part]) -> str:
    """The anchored pattern for the chosen parts."""
    rendered = []
    for index, part in enumerate(parts):
        if part.kind == LITERAL:
            rendered.append(escape(part.text))
        elif part.kind == ANY:
            rendered.append("{any}")
        elif part.kind == SAMPLE:
            rendered.append("{sample}")
        elif part.kind == RUN:
            rendered.append("{run}")
        elif part.kind == SAMPLE_WITH_SUFFIX:
            rendered.append("{sample}" + escape(suffix_of(part.text)))
        elif part.kind == ANY_WITH_SUFFIX:
            rendered.append("{any}" + escape(suffix_of(part.text)))
        elif part.kind == ANYPATH:
            if index != len(parts) - 1:
                raise ValueError("'any number of folders' may only be the last part")
            rendered.append("{anypath}")
        else:
            raise ValueError(f"unknown part kind {part.kind!r}")
    if not rendered:
        raise ValueError("type an example path first")
    return "^" + "/".join(rendered) + "$"


def check_pattern(pattern: str) -> str | None:
    """Why a pattern is not acceptable, or ``None``."""
    if not pattern:
        return "a published path pattern is required"
    if not pattern.startswith("^") or not pattern.endswith("$"):
        return "anchor the pattern: start it with ^ and end it with $"
    try:
        re.compile(expand_output_path_pattern(pattern))
    except (re.error, ValueError) as error:
        return f"not a valid pattern: {error}"
    return None


def matches(pattern: str, paths: Iterable[str]) -> list[str]:
    """The example paths a valid pattern matches."""
    if check_pattern(pattern) is not None:
        return []
    compiled = re.compile(expand_output_path_pattern(pattern))
    return [path for path in paths if compiled.match(path.strip().strip("/"))]


def captures(pattern: str) -> set[str]:
    """Named identifiers the pattern captures (sample_id, run_id, …)."""
    if check_pattern(pattern) is not None:
        return set()
    return set(re.compile(expand_output_path_pattern(pattern)).groupindex)


def scope_problem(scope: str, patterns: Sequence[str]) -> str | None:
    """Whether the patterns can tell which sample or run owns a file."""
    found = set().union(*(captures(item) for item in patterns)) if patterns else set()
    if scope == "sample" and "sample_id" not in found:
        return (
            "an output that applies to one sample needs the sample name in its "
            "path: mark the part that varies per sample as 'the sample name'"
        )
    if scope == "run" and "run_id" not in found:
        return (
            "an output that applies to one run needs the run name in its path: "
            "mark that part as 'the run name'"
        )
    return None


def key_from_title(title: str) -> str:
    """A stable snake_case key suggested from a title (editable)."""
    key = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
    if key and not key[0].isalpha():
        key = f"output_{key}"
    return key[:64]
