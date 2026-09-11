"""Reads `seed/organization.yaml` — the authoritative P1 dataset — into typed records.

The YAML is the single source of truth and is validated independently by `seed/validate.py`, which
`make check` runs. This module is the typed view the application seeds from, so a field renamed in
the YAML fails here rather than producing a half-populated demo nobody notices until the manual
pass.

Finding the file is the awkward part. The directory lives at the repository root (P1 fixed that,
and `docs/seed-data.md` names the path), while the backend runs from `/app` inside a container that
bind-mounts only `backend/`. Hence a search rather than a constant — and `SEED_DIR` as the explicit
override for anyone who puts it somewhere else.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

_FILENAME = "organization.yaml"


class SeedDataNotFoundError(RuntimeError):
    """Raised with the places we looked. "File not found" without them is a scavenger hunt."""


class SeedFormatError(RuntimeError):
    """The YAML parsed but does not have the shape the seeder expects."""


@dataclass(frozen=True, slots=True)
class OrganizationRecord:
    code: str
    name: str
    slug: str
    plan: str
    billing_email: str | None


@dataclass(frozen=True, slots=True)
class RestaurantRecord:
    code: str
    organization: str
    name: str
    timezone: str
    currency: str
    business_day_start: str
    gstin: str | None
    address: dict[str, Any] | None
    fssai_licence: str | None


def _posting(raw: object) -> Posting | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise SeedFormatError(f"also_at must be a mapping, got {type(raw).__name__}")
    return Posting(restaurant=str(raw["restaurant"]), role=str(raw["role"]))


@dataclass(frozen=True, slots=True)
class Posting:
    """A role held at one restaurant."""

    restaurant: str
    role: str


@dataclass(frozen=True, slots=True)
class EmployeeRecord:
    code: str
    name: str
    role: str
    restaurant: str
    # A second posting, at another branch of the same organization. Rare in reality and rare here —
    # exactly one seeded person has one — but without it `POST /auth/switch` cannot be exercised by
    # hand, because the switcher renders nothing for someone who works at one place.
    also_at: Posting | None
    phone: str | None
    joined: date
    employment_type: str
    # None is not a degenerate case: cleaners and part-time kitchen staff routinely have no login,
    # and ADR 0007 requires that to be a normal shape rather than a workaround.
    login: str | None


@dataclass(frozen=True, slots=True)
class SeedData:
    password: str
    is_demo: bool
    organizations: tuple[OrganizationRecord, ...]
    restaurants: tuple[RestaurantRecord, ...]
    employees: tuple[EmployeeRecord, ...]


def _candidate_directories() -> list[Path]:
    override = os.environ.get("SEED_DIR")
    if override:
        return [Path(override)]

    here = Path(__file__).resolve()
    return [
        # The container: docker-compose bind-mounts the repository's seed/ read-only.
        Path("/app/seed"),
        # A working copy: backend/app/seed/loader.py -> repo root -> seed/
        *(parent / "seed" for parent in here.parents),
    ]


def find_seed_directory() -> Path:
    looked: list[Path] = []
    for directory in _candidate_directories():
        looked.append(directory)
        if (directory / _FILENAME).is_file():
            return directory
    raise SeedDataNotFoundError(
        f"Could not find {_FILENAME}. Looked in: "
        + ", ".join(str(path) for path in looked)
        + ". Set SEED_DIR to the directory holding it."
    )


def load_seed_data(directory: Path | None = None) -> SeedData:
    source = (directory or find_seed_directory()) / _FILENAME
    raw: dict[str, Any] = yaml.safe_load(source.read_text(encoding="utf-8"))

    meta = raw["meta"]
    return SeedData(
        password=str(meta["seed_password"]),
        is_demo=bool(meta["is_demo"]),
        organizations=tuple(
            OrganizationRecord(
                code=str(item["code"]),
                name=str(item["name"]),
                slug=str(item["slug"]),
                plan=str(item["plan"]),
                billing_email=_optional(item.get("billing_email")),
            )
            for item in raw["organizations"]
        ),
        restaurants=tuple(
            RestaurantRecord(
                code=str(item["code"]),
                organization=str(item["organization"]),
                name=str(item["name"]),
                timezone=str(item["timezone"]),
                currency=str(item["currency"]),
                business_day_start=str(item["business_day_start"]),
                gstin=_optional(item.get("gstin")),
                address=item.get("address"),
                fssai_licence=_optional(item.get("fssai_licence")),
            )
            for item in raw["restaurants"]
        ),
        employees=tuple(
            EmployeeRecord(
                code=str(item["code"]),
                name=str(item["name"]),
                role=str(item["role"]),
                restaurant=str(item["restaurant"]),
                phone=_optional(item.get("phone")),
                joined=item["joined"],
                employment_type=str(item["type"]),
                login=_optional(item.get("login")),
                also_at=_posting(item.get("also_at")),
            )
            for item in raw["employees"]
        ),
    )


def _optional(value: Any) -> str | None:
    """YAML `null` and an empty string both mean absent here."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None
