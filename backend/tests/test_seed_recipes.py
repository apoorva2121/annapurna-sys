"""A seed dish contains what its name says (backlog-issues B9).

Palak Paneer was paneer, cream, onion and spices with no palak, because `seed/ingredients.yaml` had
no spinach. Read from the YAML, through preparations, the way the cost engine reads it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_SEED = Path(__file__).resolve().parents[2] / "seed"


def _load(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = yaml.safe_load((_SEED / name).read_text(encoding="utf-8"))
    return loaded


def _everything_in(refs: list[str], preparations: dict[str, Any]) -> set[str]:
    found: set[str] = set()
    pending = list(refs)
    while pending:
        ref = pending.pop()
        if ref in found:
            continue
        found.add(ref)
        if ref in preparations:
            pending.extend(line["ref"] for line in preparations[ref]["lines"])
    return found


def test_palak_paneer_contains_spinach() -> None:
    menu = _load("menu.yaml")
    preparations = {row["code"]: row for row in _load("preparations.yaml")["preparations"]}
    dish = next(item for item in menu["items"] if item["code"] == "PALAK_PANEER")

    for variant in dish["variants"]:
        contents = _everything_in([line["ref"] for line in variant["recipe"]], preparations)
        assert "SPINACH" in contents, f"PALAK_PANEER/{variant['code']} has no spinach"
