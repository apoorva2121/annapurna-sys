"""One person types one login many ways (backlog-issues B4, guardrail G-18).

`98765 43210`, `+91 98765 43210` and `09876543210` are one phone number, and `Ravi@Gmail.com` is
`ravi@gmail.com`. Stored as typed they were different logins (P1-7): a manager could create the same
person twice, and a waiter typing the number the other way was refused. Every login is normalised
at the boundary — lowercase email, E.164 phone with India's `+91` when no country code is given —
and the database's per-organization uniqueness then holds for the person, not for the spelling.
"""

from __future__ import annotations

import pytest

from app.core.identifiers import is_email, is_phone, normalise_identifier


@pytest.mark.parametrize(
    ("typed", "stored"),
    [
        ("9876543210", "+919876543210"),
        ("98765 43210", "+919876543210"),
        ("+91 98765 43210", "+919876543210"),
        ("+91-98765-43210", "+919876543210"),
        ("(+91) 98765 43210", "+919876543210"),
        ("09876543210", "+919876543210"),
        ("919876543210", "+919876543210"),
        ("0091 98765 43210", "+919876543210"),
        ("+44 20 7946 0958", "+442079460958"),
        ("  Ravi@Gmail.COM ", "ravi@gmail.com"),
    ],
)
def test_one_login_typed_many_ways_is_stored_one_way(typed: str, stored: str) -> None:
    assert normalise_identifier(typed) == stored


@pytest.mark.parametrize("typed", ["ravi", "12345", "+12", "98765 4321x", ""])
def test_what_is_neither_a_phone_nor_an_email_is_left_as_typed(typed: str) -> None:
    """Left alone rather than guessed at: at sign-in it matches nobody, and creating a login with
    it is refused in words."""
    assert normalise_identifier(typed) == typed.strip()


def test_the_kind_of_login_is_read_from_its_normal_form() -> None:
    assert is_email("ravi@gmail.com")
    assert not is_email("+919876543210")
    assert is_phone("+919876543210")
    assert not is_phone("ravi")
    assert not is_phone("12345")
