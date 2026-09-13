"""Validation errors a person can act on.

Found in the M03 manual pass on 2026-09-13 (backlog: "Validation errors say only 'The request was
not valid.' and never which field or why"): adding a menu section, a supplier and a station each
failed with that sentence and a code. The envelope did carry pydantic's own words, but for a
format rule those words are a regular expression, which is worse than nothing to a restaurant
manager.

Three promises, one class each:

- every field problem carries a stable code and a sentence a person can act on;
- every format rule in the API has a sentence written for it, so a new `pattern=` without one fails
  the build and a regex can never reach a screen again;
- a GSTIN typed in lower case is the same GSTIN (backlog: "The API does not uppercase a GSTIN").
"""

from __future__ import annotations

import importlib
import pkgutil
import re
from collections.abc import AsyncIterator, Callable, Iterator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import BaseModel, ConfigDict, Field

import app.schemas
from app.core.validation_messages import PATTERN_MESSAGES
from app.schemas.orders import RecipientRequest
from app.schemas.procurement import SupplierCreateRequest, SupplierUpdateRequest
from app.schemas.setup import RestaurantUpdateRequest

GSTIN = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"

# `^(veg|non_veg|egg)$` — a closed list, which can be explained mechanically ("Choose one of …").
CHOICE = re.compile(r"^\^\((?:[a-z0-9_]+\|)*[a-z0-9_]+\)\$$")


class _Probe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=5)
    gstin: str | None = Field(default=None, pattern=GSTIN)
    payment_terms_days: int | None = Field(default=None, ge=0, le=365)


@pytest.fixture
async def probe_client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    @app.post("/api/v1/_probe")
    async def _probe(body: _Probe) -> dict[str, str]:
        return {"name": body.name}

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client


def _by_field(body: dict[str, Any]) -> dict[str, dict[str, str]]:
    return {entry["field"]: entry for entry in body["details"]["fields"]}


class TestAFieldProblemSaysWhatToDo:
    async def test_a_bad_gstin_explains_the_format_without_showing_a_pattern(
        self, probe_client: AsyncClient
    ) -> None:
        response = await probe_client.post(
            "/api/v1/_probe", json={"name": "Ok", "gstin": "27AAPFU0939F"}
        )

        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "request.invalid"
        entry = _by_field(body)["gstin"]
        assert entry["code"] == "field.format"
        assert entry["message"] == PATTERN_MESSAGES[GSTIN]
        assert "^" not in response.text
        assert "[A-Z]" not in response.text

    async def test_length_range_required_number_and_unknown_each_have_their_own_code(
        self, probe_client: AsyncClient
    ) -> None:
        response = await probe_client.post(
            "/api/v1/_probe", json={"name": "toolong", "payment_terms_days": 400, "colour": "red"}
        )
        fields = _by_field(response.json())
        assert fields["name"] == {
            "field": "name",
            "code": "field.too_long",
            "message": "Use at most 5 characters.",
        }
        assert fields["payment_terms_days"] == {
            "field": "payment_terms_days",
            "code": "field.out_of_range",
            "message": "Must be 365 or less.",
        }
        assert fields["colour"]["code"] == "field.unknown"

        response = await probe_client.post("/api/v1/_probe", json={})
        assert _by_field(response.json())["name"] == {
            "field": "name",
            "code": "field.required",
            "message": "This is required.",
        }

        response = await probe_client.post(
            "/api/v1/_probe", json={"name": "", "payment_terms_days": "thirty"}
        )
        fields = _by_field(response.json())
        assert fields["name"]["code"] == "field.required"
        assert fields["payment_terms_days"] == {
            "field": "payment_terms_days",
            "code": "field.not_a_number",
            "message": "Enter a whole number.",
        }

    async def test_the_summary_counts_the_fields_to_fix(self, probe_client: AsyncClient) -> None:
        one = await probe_client.post("/api/v1/_probe", json={"name": "toolong"})
        two = await probe_client.post(
            "/api/v1/_probe", json={"name": "toolong", "payment_terms_days": -1}
        )

        assert one.json()["message"] == "Please fix the highlighted field."
        assert two.json()["message"] == "Please fix the 2 highlighted fields."
        assert _by_field(two.json())["payment_terms_days"]["message"] == "Must be 0 or more."


def _schema_models() -> Iterator[type[BaseModel]]:
    for module_info in pkgutil.iter_modules(app.schemas.__path__):
        module = importlib.import_module(f"app.schemas.{module_info.name}")
        for value in vars(module).values():
            if (
                isinstance(value, type)
                and issubclass(value, BaseModel)
                and value.__module__ == module.__name__
            ):
                yield value


def _patterns_in_the_api() -> set[str]:
    """Every `pattern=` a schema declares.

    Read from the fields themselves, not from `model_json_schema()`: the JSON schema also carries
    patterns pydantic generates for decimals sent as strings, which nobody ever sees as a format
    error — a bad decimal is reported as not a number.
    """
    return {
        pattern
        for model in _schema_models()
        for field in model.model_fields.values()
        for metadata in field.metadata
        if isinstance(pattern := getattr(metadata, "pattern", None), str)
    }


class TestEveryFormatRuleHasASentence:
    def test_every_pattern_in_the_api_is_explained_in_words(self) -> None:
        unexplained = sorted(
            pattern
            for pattern in _patterns_in_the_api()
            if pattern not in PATTERN_MESSAGES and not CHOICE.match(pattern)
        )
        assert unexplained == [], (
            "Write a plain-language sentence for each of these in "
            "app/core/validation_messages.py, or a person will see the pattern itself"
        )

    def test_the_sentences_are_for_people(self) -> None:
        for pattern, message in PATTERN_MESSAGES.items():
            assert message.endswith("."), pattern
            assert "^" not in message and "[" not in message, pattern

    def test_no_sentence_is_kept_for_a_rule_the_api_no_longer_has(self) -> None:
        assert set(PATTERN_MESSAGES) <= _patterns_in_the_api()


LOWER = " 27aapfu0939f1zv "
UPPER = "27AAPFU0939F1ZV"

# Returning `Any` so each built model's `gstin` can be read directly; the four models share no base
# that declares it.
BUILDERS: dict[str, Callable[[str], Any]] = {
    "supplier create": lambda gstin: SupplierCreateRequest(name="Sharma Traders", gstin=gstin),
    "supplier update": lambda gstin: SupplierUpdateRequest(gstin=gstin),
    "restaurant settings": lambda gstin: RestaurantUpdateRequest(gstin=gstin),
    "invoice recipient": lambda gstin: RecipientRequest(gstin=gstin),
}


class TestAGstinIsTheSameInLowerCase:
    @pytest.mark.parametrize("where", sorted(BUILDERS))
    def test_it_is_accepted_and_kept_in_capitals(self, where: str) -> None:
        assert BUILDERS[where](LOWER).gstin == UPPER
