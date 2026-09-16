"""Every error a person can meet has an issue number and plain words (backlog-issues B12, D11, D12).

The owner's rule: a code such as `cash.payout_exceeds_till` never appears on screen. A person reads
the error's own sentence and "Issue 1042", a number they can read out on the phone.
`app/core/issues.json` holds number, code and text; migration 0029 copies it into the `issue`
table.
The scan below reads the syntax tree of `app/`, so a new `raise ConflictError("x.y", ...)` without a
catalogue entry fails the build here rather than showing a person nothing to quote.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import build_envelope
from app.core.issues import ISSUES, issue_for

_BACKEND = Path(__file__).resolve().parents[1]
_APP = _BACKEND / "app"
_CATALOGUE = _APP / "core" / "issues.json"
_VERSIONS = _BACKEND / "alembic" / "versions"
_ERROR_CLASSES = {"AppError", "NotFoundError", "ConflictError", "PermissionDeniedError"}
_CODE = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z0-9_]+)*$")
# Raised by the envelope itself rather than by an AppError call.
_CORE = {
    "request.invalid",
    "request.rejected",
    "conflict.duplicate",
    "conflict.missing",
    "internal.error",
    "http.status",
}
# Made in the browser: frontend/src/shared/api.ts.
_FRONTEND = {"network.unreachable", "idempotency.key_missing"}


def _code_in(node: ast.expr) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str) and _CODE.match(node.value):
        return node.value
    return None


def _raised_codes() -> set[str]:
    """The first argument (or `code=`) of every call to an AppError class, a subclass's
    `super().__init__`, `require_whole_order`, and a module constant spread into a raise."""
    codes: set[str] = set()
    for path in _APP.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        classes = set(_ERROR_CLASSES)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and any(
                isinstance(base, ast.Name) and base.id in classes for base in node.bases
            ):
                classes.add(node.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Tuple):
                elements = node.value.elts
                if (
                    len(elements) == 2
                    and isinstance(elements[1], ast.Constant)
                    and " " in str(elements[1].value)
                ):
                    found = _code_in(elements[0])
                    if found is not None:
                        codes.add(found)
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr
                if isinstance(func, ast.Attribute)
                else ""
            )
            if name not in classes and name not in {"__init__", "require_whole_order"}:
                continue
            candidates: list[ast.expr] = [kw.value for kw in node.keywords if kw.arg == "code"]
            if node.args and name != "require_whole_order":
                candidates.append(node.args[0])
            for candidate in candidates:
                found = _code_in(candidate)
                if (found is not None and "." in found) or (found is not None and "_" in found):
                    codes.add(found)
    return codes


def _catalogued() -> dict[str, int]:
    return {issue.code: issue.number for issue in ISSUES.issues}


def test_the_scan_finds_the_codes_it_must() -> None:
    codes = _raised_codes()

    assert len(codes) >= 150
    for expected in (
        "cash.payout_exceeds_till",
        "recipe.cycle",
        "idempotency.in_progress",
        "menu_category.reorder_incomplete",
        "auth.required",
    ):
        assert expected in codes


def test_every_raised_code_has_an_issue() -> None:
    missing = sorted(_raised_codes() - set(_catalogued()))

    assert missing == []


def test_every_core_and_browser_code_has_an_issue() -> None:
    assert sorted((_CORE | _FRONTEND) - set(_catalogued())) == []


def test_the_catalogue_names_no_code_nothing_raises() -> None:
    dead = sorted(set(_catalogued()) - _raised_codes() - _CORE - _FRONTEND)

    assert dead == []


def test_every_issue_is_a_sentence_a_person_can_read() -> None:
    for issue in ISSUES.issues:
        assert 1000 <= issue.number <= 9999
        assert issue.text.endswith((".", "?")), issue.code
        assert not re.search(r"\b[a-z]+_[a-z_]+\b|\b[a-z]+\.[a-z_]+\b", issue.text), issue.code


def test_the_envelope_carries_the_issue_number() -> None:
    body = build_envelope("cash.payout_exceeds_till", "Not enough cash in the till.")

    assert body["issue"] == issue_for("cash.payout_exceeds_till")
    assert isinstance(body["issue"], int)


def test_every_http_status_shares_one_issue() -> None:
    assert issue_for("http.404") == issue_for("http.502") == issue_for("http.status")


def test_a_code_with_no_issue_carries_none_rather_than_a_wrong_one() -> None:
    assert "issue" not in build_envelope("never.catalogued", "message")


def test_the_current_catalogue_has_a_migration_that_seeds_it() -> None:
    raw: dict[str, Any] = json.loads(_CATALOGUE.read_text(encoding="utf-8"))
    catalogue = {key: value for key, value in raw.items() if not key.startswith("_")}
    canonical = json.dumps(catalogue, sort_keys=True, separators=(",", ":"))
    current = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    declared = {
        match.group(1)
        for path in _VERSIONS.glob("*.py")
        if (
            match := re.search(
                r'^ISSUES_FINGERPRINT = "([^"]+)"', path.read_text(encoding="utf-8"), re.MULTILINE
            )
        )
    }

    assert current in declared, "issues.json changed and no migration copies this version of it"


async def test_the_issue_table_holds_the_catalogue(db_session: AsyncSession) -> None:
    rows = (await db_session.execute(text("SELECT number, code, text FROM issue"))).tuples().all()

    assert {(int(n), str(c), str(t)) for n, c, t in rows} == {
        (issue.number, issue.code, issue.text) for issue in ISSUES.issues
    }
