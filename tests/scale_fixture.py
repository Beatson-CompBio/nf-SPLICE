"""A synthetic pathological pipeline for performance tests (fixture D).

It is generated, not checked in: more than a thousand parameters, modules
and catalogued outputs, and well over a megabyte of prose that nf-SPLICE
must never read into a field. No real or private data is involved.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PARAMETERS = 1200
GROUPS = 12
MODULES = 1100
OUTPUTS = 1000
PROSE_BYTES = 1_500_000


def write_scale_pipeline(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "nextflow.config").write_text(
        "manifest {\n    name = 'org/scale'\n    version = '2.0.0'\n"
        "    homePage = 'https://github.com/org/scale'\n"
        "    description = 'A synthetic pipeline with very many parts.'\n}\n"
        "params {\n    outdir = 'results'\n}\n",
        encoding="utf-8",
    )
    per_group = PARAMETERS // GROUPS
    definitions: dict[str, Any] = {}
    for group in range(GROUPS):
        definitions[f"group_{group:02d}"] = {
            "title": f"Group {group}",
            "type": "object",
            "properties": {
                f"option_{group:02d}_{index:04d}": {
                    "type": "string" if index % 3 else "integer",
                    "default": "value" if index % 3 else index,
                    "description": "An option. " + "Long text. " * 20,
                }
                for index in range(per_group)
            },
        }
    (root / "nextflow_schema.json").write_text(
        json.dumps(
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "title": "org/scale parameters",
                "type": "object",
                "$defs": definitions,
                "allOf": [{"$ref": f"#/$defs/{name}"} for name in definitions],
            }
        ),
        encoding="utf-8",
    )
    includes = []
    installed = {}
    for index in range(MODULES):
        name = f"tool{index:04d}"
        module = root / "modules" / "nf-core" / name
        module.mkdir(parents=True)
        (module / "meta.yml").write_text(f"name: {name}\n", encoding="utf-8")
        (module / "main.nf").write_text(
            f"process TOOL{index:04d} {{\n"
            f"    container 'quay.io/biocontainers/{name}:1.0--0'\n"
            f'    publishDir "${{params.outdir}}/{name}"\n'
            f"    output:\n    path '*.txt', emit: out\n"
            "    script:\n    'touch out.txt'\n}\n",
            encoding="utf-8",
        )
        installed[name] = {"branch": "master", "git_sha": "0" * 40}
        if index < 50:
            includes.append(
                f"include {{ TOOL{index:04d} }} from './modules/nf-core/{name}/main'"
            )
    (root / "modules.json").write_text(
        json.dumps(
            {
                "name": "org/scale",
                "repos": {
                    "https://github.com/nf-core/modules.git": {
                        "modules": {"nf-core": installed}
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    calls = "\n".join(f"    TOOL{index:04d}()" for index in range(50))
    (root / "main.nf").write_text(
        "\n".join(includes) + f"\n\nworkflow {{\n{calls}\n}}\n", encoding="utf-8"
    )
    sentence = "This pipeline processes poly(A) RNA-seq and many other things. "
    (root / "README.md").write_text(
        "# Scale\n\n" + sentence * (PROSE_BYTES // len(sentence) + 1),
        encoding="utf-8",
    )


def scale_outputs() -> list[dict[str, Any]]:
    return [
        {
            "key": f"result_{index:04d}",
            "title": f"Result {index}",
            "description": "A synthetic result. " * 5,
            "category": f"category_{index % 20}",
            "formats": ["txt"],
            "scopes": ["sample"],
            "entity_types": ["file"],
            "path_patterns": [f"^tool{index:04d}/{{sample}}\\.txt$"],
        }
        for index in range(OUTPUTS)
    ]
