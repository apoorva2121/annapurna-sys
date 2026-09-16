"""A person as the API names them: never an id alone (backlog-issues B12, D13)."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class PersonResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    full_name: str
    employee_code: str
    roles: list[str]

    @classmethod
    def of(cls, person: Any) -> PersonResponse | None:
        if person is None:
            return None
        return cls(
            full_name=person.full_name, employee_code=person.employee_code, roles=list(person.roles)
        )


class AdjusterResponse(PersonResponse):
    """Who adjusted a till, and whether they were also the person who closed it (D16)."""

    by_closer: bool
