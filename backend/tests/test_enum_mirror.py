"""The wire boundary's only defence against enum drift.

`app/core/enums.py` is the source of truth; `frontend/src/shared/enums.ts` mirrors it by hand
(ADR 0008). Hand-mirroring works right up until someone adds a value on one side only, and then it
fails as a runtime bug in a browser rather than as a red build. This test is the reason that cannot
happen.
"""

from __future__ import annotations

import inspect
import re
from enum import StrEnum
from pathlib import Path

import pytest

from app.core import enums

_ENUMS_TS = Path(__file__).resolve().parents[2] / "frontend" / "src" / "shared" / "enums.ts"

# export const RoleCode = { OWNER: 'owner', ... } as const
_BLOCK = re.compile(r"export const (?P<name>\w+)\s*=\s*\{(?P<body>.*?)\}\s*as const", re.DOTALL)
_MEMBER = re.compile(r"(?P<name>\w+)\s*:\s*'(?P<value>[^']*)'")


def _python_enums() -> dict[str, dict[str, str]]:
    found: dict[str, dict[str, str]] = {}
    for name, obj in inspect.getmembers(enums, inspect.isclass):
        # StrEnum itself is imported into the module's namespace; only subclasses are ours.
        if issubclass(obj, StrEnum) and obj is not StrEnum:
            found[name] = {member.name: member.value for member in obj}
    return found


def _typescript_enums() -> dict[str, dict[str, str]]:
    source = _ENUMS_TS.read_text(encoding="utf-8")
    return {
        match.group("name"): {
            member.group("name"): member.group("value")
            for member in _MEMBER.finditer(match.group("body"))
        }
        for match in _BLOCK.finditer(source)
    }


def test_the_two_files_declare_the_same_enums() -> None:
    assert set(_typescript_enums()) == set(_python_enums())


@pytest.mark.parametrize("enum_name", sorted(_python_enums()))
def test_each_enum_has_identical_members_on_both_sides(enum_name: str) -> None:
    # Names and values both: a matching value under a renamed key still breaks any consumer
    # that imports the key.
    assert _typescript_enums().get(enum_name) == _python_enums()[enum_name]


def test_the_parser_actually_finds_something() -> None:
    """Guard against the mirror test passing because the regex matched nothing on both sides."""
    assert _python_enums(), "no StrEnum found in app/core/enums.py — the parser is broken"
