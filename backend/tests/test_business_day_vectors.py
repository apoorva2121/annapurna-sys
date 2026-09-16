"""The business-day cases both implementations must agree on, from one file (backlog-issues B10).

`app/core/business_day.py` and `frontend/src/shared/businessDay.ts` implement one rule twice (ADR
0004). Their tests used the same instants, but transcribed into each file, so a case added to one
side never reached the other. `contracts/business-day-vectors.json` is read by both suites; the
hand-written tests stay, because they explain why each case matters.
"""

from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path
from typing import Any

import pytest

from app.core.business_day import business_date_of

_VECTORS = Path(__file__).resolve().parents[2] / "contracts" / "business-day-vectors.json"


def _cases() -> list[dict[str, Any]]:
    loaded: dict[str, Any] = json.loads(_VECTORS.read_text(encoding="utf-8"))
    cases: list[dict[str, Any]] = loaded["cases"]
    return cases


@pytest.mark.parametrize("case", _cases(), ids=lambda case: str(case["name"]))
def test_the_shared_vector_holds(case: dict[str, Any]) -> None:
    moment = datetime.fromisoformat(str(case["instant"]).replace("Z", "+00:00"))

    result = business_date_of(moment, case["timezone"], time.fromisoformat(case["day_starts_at"]))

    assert result == date.fromisoformat(case["business_date"])


def test_there_are_enough_vectors_to_mean_something() -> None:
    assert len(_cases()) >= 12
