"""Compile the SPLICE modality vocabulary into nf-splice's packaged catalogue.

python scripts/build_assay_catalogue.py --source DIR --snapshot ID --origin TEXT

DIR holds the three seed files of the SPLICE platform (``splice-lib``
``repositories/seed_data``): ``modality_entities.csv``,
``modality_relationships.csv`` and ``Modalities.csv``. The raw files are never
committed; this script writes a normalised projection with every value the
catalogue needs, exactly as the source states it, plus the SHA-256 of each
source file so the snapshot can be traced and rebuilt.

Only these registration columns are kept: ``modality_id``,
``modality_name``, ``entity_id``, ``current``, ``schema_version_splice`` and
``schema_version_ext``. Per-assay metadata schemas, QC DAGs and LLM context
files are deployment data and are left out. No accession identifiers exist in
the seed data and none are derived.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "src" / "nf_splice" / "catalogue" / "data" / "assay-vocabulary.json"
FILES = ("modality_entities.csv", "modality_relationships.csv", "Modalities.csv")
ENTITY_TYPES = {"root", "MODALITY", "MODALITY_SUBTYPE", "ASSAY_TYPE", "ASSAY_METHOD"}


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _boolean(value: str, where: str) -> bool:
    lowered = value.strip().lower()
    if lowered not in {"true", "false"}:
        raise SystemExit(f"{where}: expected true or false, found {value!r}")
    return lowered == "true"


def _text(value: str | None) -> str | None:
    stripped = (value or "").strip()
    return stripped or None


def compile_snapshot(source: Path, snapshot: str, origin: str) -> dict[str, object]:
    missing = [name for name in FILES if not (source / name).is_file()]
    if missing:
        raise SystemExit(f"missing source files in {source}: {', '.join(missing)}")
    entities = []
    for row in _rows(source / "modality_entities.csv"):
        kind = row["entity_type"].strip()
        if kind not in ENTITY_TYPES:
            raise SystemExit(f"entity {row['entity_id']}: unknown type {kind!r}")
        aliases = [item.strip() for item in (row.get("aliases") or "").split("|")]
        entities.append(
            {
                "entity_id": int(row["entity_id"]),
                "label": row["label"].strip(),
                "entity_type": kind,
                "description": _text(row.get("description")),
                "aliases": [item for item in aliases if item],
                "concept_status": row["concept_status"].strip(),
                "implementation_status": row["implementation_status"].strip(),
            }
        )
    relationships = [
        {
            "id": int(row["id"]),
            "child_entity_id": int(row["child_entity_id"]),
            "ancestor_entity_id": int(row["ancestor_entity_id"]),
            "navigation": row["navigation"].strip(),
        }
        for row in _rows(source / "modality_relationships.csv")
    ]
    registrations = []
    for row in _rows(source / "Modalities.csv"):
        entity = _text(row.get("entity_id"))
        registrations.append(
            {
                "modality_id": int(row["modality_id"]),
                "modality_name": row["modality_name"].strip(),
                "entity_id": int(entity) if entity else None,
                "current": _boolean(row["current"], f"modality {row['modality_id']}"),
                "schema_version_splice": _text(row.get("schema_version_splice")),
                "schema_version_ext": _text(row.get("schema_version_ext")),
            }
        )
    content = {
        "entities": sorted(entities, key=lambda item: item["entity_id"]),
        "relationships": sorted(relationships, key=lambda item: item["id"]),
        "registrations": sorted(registrations, key=lambda item: item["modality_id"]),
    }
    digest = hashlib.sha256(
        json.dumps(content, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return {
        "format": "nf-splice-assay-vocabulary/1",
        "snapshot": {
            "id": snapshot,
            "name": "SPLICE modality vocabulary",
            "origin": origin,
            "digest": f"sha256:{digest}",
            "source_files": {
                name: hashlib.sha256((source / name).read_bytes()).hexdigest()
                for name in FILES
            },
            "counts": {key: len(value) for key, value in content.items()},
        },
        **content,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--snapshot", required=True, help="Snapshot identifier.")
    parser.add_argument("--origin", required=True, help="Where the files came from.")
    parser.add_argument("--output", type=Path, default=TARGET)
    arguments = parser.parse_args(argv)
    document = compile_snapshot(arguments.source, arguments.snapshot, arguments.origin)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    counts = document["snapshot"]["counts"]  # type: ignore[index]
    print(f"wrote {arguments.output} ({counts})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
