"""Read the export-control catalogue: one manifest plus one file per category.

public/data/export_controls/manifest.json lists the category modules
(agri.json, energy.json, minerals.json). Each module holds only its own rows,
so a new group such as precious metals is a new file and a manifest line, not
another block in one shared document.

load() returns the shape the validator and survey have always read -- the
manifest's fields plus a flat `controls` list -- and adds `module_of`
(row id -> the category of the file it sits in) so a row filed under the
wrong module is caught.
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
# HERE is .../New for anti/scripts/export_controls
# parents[1] is the inner "New for anti" directory, where public/data lives.
DIRECTORY = HERE.parents[1] / "public" / "data" / "export_controls"
MANIFEST = DIRECTORY / "manifest.json"


def load(directory=DIRECTORY):
    directory = Path(directory)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    doc = {k: v for k, v in manifest.items() if k != "modules"}
    doc["modules"] = manifest.get("modules") or []
    doc["categories"] = {m["category"]: m.get("label_ko", m["category"]) for m in doc["modules"]}
    controls, module_of = [], {}
    for module in doc["modules"]:
        body = json.loads((directory / module["file"]).read_text(encoding="utf-8"))
        if body.get("category") != module["category"]:
            raise ValueError(f"{module['file']}: category {body.get('category')!r} != manifest {module['category']!r}")
        for row in body.get("controls") or []:
            controls.append(row)
            module_of.setdefault(row.get("id") or "?", module["category"])
    doc["controls"] = controls
    doc["module_of"] = module_of
    return doc
