"""Machine checks for the ADR register and the 0.3.0 traceability ledger."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "docs" / "ARCHITECTURE_DECISIONS.md"
LEDGER = ROOT / "docs" / "RELEASE_0.3.0.md"
_FIRST_INCREMENTAL = 23
_STATUSES = {"Proposed", "Current", "Superseded", "Rejected"}
_REQUIRED_SECTIONS = ("Context", "Decision", "Alternatives rejected", "Consequences")


@dataclass(frozen=True)
class Record:
    identifier: str
    title: str
    metadata: dict[str, str]
    sections: tuple[str, ...]

    @property
    def number(self) -> int:
        return int(self.identifier.removeprefix("ADR-"))


def _ids(value: str) -> set[str]:
    return set(re.findall(r"ADR-\d{4}", value))


def _paths(value: str) -> list[str]:
    return re.findall(r"`([^`]+)`", value)


def _index() -> dict[str, tuple[str, str, str]]:
    text = REGISTER.read_text(encoding="utf-8")
    block = text.split("## Decision index", 1)[1].split("\n---\n", 1)[0]
    rows = {}
    for line in block.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 4 and cells[0].startswith("ADR-"):
            rows[cells[0]] = (cells[1], cells[2], cells[3])
    return rows


def _records() -> dict[str, Record]:
    text = REGISTER.read_text(encoding="utf-8")
    records = {}
    for chunk in re.split(r"\n(?=## ADR-\d{4}: )", text)[1:]:
        heading, _, body = chunk.partition("\n")
        match = re.match(r"## (ADR-\d{4}): (.+)", heading)
        assert match, heading
        metadata = {}
        for line in body.splitlines():
            cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
            if len(cells) == 2 and cells[0] not in {"Metadata", "---"}:
                metadata[cells[0]] = cells[1]
        sections = tuple(re.findall(r"^### (.+)$", body, flags=re.MULTILINE))
        records[match.group(1)] = Record(
            match.group(1), match.group(2).strip(), metadata, sections
        )
    return records


def test_index_matches_every_record_in_order() -> None:
    index = _index()
    records = _records()
    assert list(index) == list(records)
    numbers = [record.number for record in records.values()]
    assert numbers == list(range(1, len(numbers) + 1))
    for identifier, (title, status, superseded_by) in index.items():
        record = records[identifier]
        assert record.title == title, identifier
        assert record.metadata["Status"] == status, identifier
        assert status in _STATUSES, identifier
        assert record.metadata["Superseded by"] == superseded_by, identifier


def test_supersession_links_are_bidirectional() -> None:
    records = _records()
    for identifier, record in records.items():
        for older in _ids(record.metadata.get("Supersedes", "")):
            assert identifier in _ids(records[older].metadata["Superseded by"]), (
                identifier,
                older,
            )
            assert records[older].metadata["Status"] == "Superseded", older
        superseded_by = _ids(record.metadata.get("Superseded by", ""))
        if record.metadata["Status"] == "Superseded":
            assert superseded_by, identifier
        for newer in superseded_by:
            assert identifier in _ids(records[newer].metadata["Supersedes"]), (
                identifier,
                newer,
            )
        for related in _ids(record.metadata.get("Related", "")):
            assert related in records, (identifier, related)


def test_incremental_records_carry_traceability_metadata_and_sections() -> None:
    for identifier, record in _records().items():
        if record.number < _FIRST_INCREMENTAL:
            continue
        for key in ("Date", "Source", "Scope", "Implementation", "Tests"):
            assert record.metadata.get(key), (identifier, key)
        for section in _REQUIRED_SECTIONS:
            assert section in record.sections, (identifier, section)
        for path in _paths(record.metadata["Implementation"]):
            assert (ROOT / path).exists(), (identifier, path)
        tests = _paths(record.metadata["Tests"])
        assert tests, identifier
        for path in tests:
            assert (ROOT / path).is_file(), (identifier, path)


def test_release_ledger_traces_features_to_current_adrs_and_tests() -> None:
    records = _records()
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) == 5 and _ids(cells[1]):
            rows.append(cells)
    assert rows
    features = [row[0] for row in rows]
    assert len(features) == len(set(features))
    for feature, adrs, implementation, tests, status in rows:
        assert status == "Current", feature
        for identifier in _ids(adrs):
            assert records[identifier].metadata["Status"] == "Current", (
                feature,
                identifier,
            )
        for path in _paths(implementation):
            assert (ROOT / path).exists(), (feature, path)
        test_paths = _paths(tests)
        assert test_paths, feature
        for path in test_paths:
            assert (ROOT / path).is_file(), (feature, path)
