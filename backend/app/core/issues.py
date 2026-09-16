"""The issue catalogue: every error a person can meet, with a number and plain words.

Backlog-issues B12 (owner decisions D11, D12). `code` stays the stable string the frontend switches
on and is never shown. A person reads the error's own sentence and "Issue 1042" — a number they can
read out on the phone, which support looks up here. `issues.json` is the source; migration 0029
copies it into the `issue` table, the way permissions.json reaches `permission`.

Numbers are permanent: a new issue takes the next free number, and a retired one is never reused.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

_CATALOGUE_PATH = Path(__file__).with_name("issues.json")

# Every status the transport synthesises (`http.404`, `http.502` …) shares one entry.
_HTTP = "http.status"


class IssueSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    number: int = Field(ge=1000, le=9999)
    code: str
    text: str = Field(min_length=10)


class IssueCatalogue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    issues: tuple[IssueSpec, ...]

    @model_validator(mode="after")
    def _numbers_and_codes_are_unique(self) -> IssueCatalogue:
        numbers = [issue.number for issue in self.issues]
        codes = [issue.code for issue in self.issues]
        repeated_numbers = sorted({n for n in numbers if numbers.count(n) > 1})
        repeated_codes = sorted({c for c in codes if codes.count(c) > 1})
        if repeated_numbers or repeated_codes:
            raise ValueError(f"repeated issue numbers {repeated_numbers} or codes {repeated_codes}")
        return self


@lru_cache
def load_issues() -> IssueCatalogue:
    raw = json.loads(_CATALOGUE_PATH.read_text(encoding="utf-8"))
    return IssueCatalogue.model_validate({k: v for k, v in raw.items() if not k.startswith("_")})


ISSUES = load_issues()
_BY_CODE = {issue.code: issue.number for issue in ISSUES.issues}


def issue_for(code: str) -> int | None:
    """The number a person quotes for this code, or None for a code nobody catalogued."""
    if code.startswith("http."):
        return _BY_CODE.get(_HTTP)
    return _BY_CODE.get(code)
