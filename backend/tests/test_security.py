"""Password hashing and token handling — the primitives every later module trusts blindly.

These are the functions where "almost right" is a breach rather than a bug, so the tests assert
properties (a hash is salted, a token cannot be re-signed, an expired token is refused) rather than
checking that the happy path returns something truthy.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.security import (
    ExpiredTokenError,
    InvalidTokenError,
    decode_access_token,
    hash_password,
    hash_refresh_token,
    issue_access_token,
    new_refresh_token,
    verify_password,
)


class TestPasswordHashing:
    def test_a_correct_password_verifies(self) -> None:
        stored = hash_password("Staging#2026")
        assert verify_password("Staging#2026", stored) is True

    def test_a_wrong_password_does_not_verify(self) -> None:
        stored = hash_password("Staging#2026")
        assert verify_password("staging#2026", stored) is False

    def test_the_hash_is_argon2id(self) -> None:
        # Not argon2i and not argon2d: id is the hybrid OWASP recommends, and the M01 spec names.
        assert hash_password("Staging#2026").startswith("$argon2id$")

    def test_the_same_password_hashes_differently_every_time(self) -> None:
        """Proves the salt is per-hash. Without it, identical passwords produce identical hashes
        and a stolen dump tells an attacker which accounts share a password."""
        assert hash_password("Staging#2026") != hash_password("Staging#2026")

    def test_the_plaintext_never_appears_in_the_hash(self) -> None:
        assert "Staging#2026" not in hash_password("Staging#2026")

    def test_verifying_against_a_corrupt_hash_is_false_rather_than_an_exception(self) -> None:
        # A malformed row must deny the login, not return a 500 that someone retries.
        assert verify_password("Staging#2026", "not-a-hash") is False

    def test_verifying_against_no_hash_is_false(self) -> None:
        # An invited-but-not-activated account has password_hash NULL. It must not be loggable in.
        assert verify_password("Staging#2026", None) is False

    def test_a_long_password_is_accepted(self) -> None:
        # bcrypt silently truncates at 72 bytes; argon2 does not. Asserted so a future swap back
        # cannot reintroduce that.
        long_password = "a" * 200 + "Z9!"
        stored = hash_password(long_password)
        assert verify_password(long_password, stored) is True
        assert verify_password("a" * 200, stored) is False


class TestRefreshTokens:
    def test_a_new_token_is_not_stored_in_plaintext(self) -> None:
        raw, stored = new_refresh_token()
        assert raw != stored
        assert raw not in stored

    def test_the_same_token_always_hashes_to_the_same_value(self) -> None:
        # Unlike a password, this hash is looked up by value, so it must be deterministic.
        raw, stored = new_refresh_token()
        assert hash_refresh_token(raw) == stored

    def test_two_tokens_are_never_the_same(self) -> None:
        assert len({new_refresh_token()[0] for _ in range(500)}) == 500

    def test_the_token_has_at_least_256_bits_of_entropy(self) -> None:
        # A guessable refresh token is a permanent account takeover.
        raw, _ = new_refresh_token()
        assert len(raw) >= 43  # 32 bytes, url-safe base64


class TestAccessTokens:
    def _claims(self) -> dict[str, object]:
        return {
            "employee_id": str(uuid4()),
            "organization_id": str(uuid4()),
            "restaurant_id": str(uuid4()),
            "permissions": ["employee.view"],
        }

    def test_a_token_round_trips(self) -> None:
        claims = self._claims()
        decoded = decode_access_token(issue_access_token(**claims))  # type: ignore[arg-type]
        assert decoded.employee_id == claims["employee_id"]
        assert decoded.restaurant_id == claims["restaurant_id"]
        assert decoded.permissions == frozenset({"employee.view"})

    def test_an_expired_token_is_refused(self) -> None:
        claims = self._claims()
        token = issue_access_token(**claims, expires_in=timedelta(seconds=-1))  # type: ignore[arg-type]
        with pytest.raises(ExpiredTokenError):
            decode_access_token(token)

    def test_a_token_signed_with_another_key_is_refused(self) -> None:
        """The attack this prevents: an attacker who learns the claim shape mints their own token
        with their own key and grants themselves every permission."""
        forged = jwt.encode(
            {
                "sub": str(uuid4()),
                "org": str(uuid4()),
                "rst": str(uuid4()),
                "prm": ["employee.role.assign"],
                "typ": "access",
                "exp": datetime.now(UTC) + timedelta(minutes=15),
            },
            # Long enough to be a valid HS256 key: the point is that it is the *wrong* key, not
            # that it is a weak one.
            "an-attacker-chosen-key-that-is-long-enough-to-sign-with",
            algorithm="HS256",
        )
        with pytest.raises(InvalidTokenError):
            decode_access_token(forged)

    def test_an_unsigned_token_is_refused(self) -> None:
        """CVE-2015-9235, the alg=none attack. PyJWT defends against it, and this test is here so
        a future change to the decode call cannot quietly reopen it."""
        forged = jwt.encode({"sub": str(uuid4()), "typ": "access"}, key="", algorithm="none")
        with pytest.raises(InvalidTokenError):
            decode_access_token(forged)

    def test_a_refresh_token_cannot_be_used_as_an_access_token(self) -> None:
        # Token confusion: the refresh token lives longer, so accepting one as an access token
        # would extend every session far past its intended life.
        claims = self._claims()
        token = issue_access_token(**claims, token_type="refresh")  # type: ignore[arg-type]  # noqa: S106
        with pytest.raises(InvalidTokenError):
            decode_access_token(token)

    def test_a_garbage_string_is_refused(self) -> None:
        with pytest.raises(InvalidTokenError):
            decode_access_token("not.a.token")

    def test_the_token_carries_no_personal_data(self) -> None:
        """A JWT is base64, not encryption — anyone holding it can read every claim. Names, emails
        and phone numbers must therefore never go in one."""
        claims = self._claims()
        payload = jwt.decode(
            issue_access_token(**claims),  # type: ignore[arg-type]
            options={"verify_signature": False},
        )
        assert set(payload) <= {"sub", "org", "rst", "prm", "typ", "exp", "iat", "jti"}
