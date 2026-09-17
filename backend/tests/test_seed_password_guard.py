"""Who may seed the demo world, and with whose password (R7 step 2).

The danger is not the demo data, it is the logins. Every seeded account is `status=ACTIVE` and the
password in `seed/organization.yaml` is printed in that file's own header — so seeding with it
outside local hands an owner account to anyone who can read the repository. `is_demo` does not help:
it keeps these organizations out of reports and does nothing about signing in.

Staging still needs the world, because a deployment with an empty floor demonstrates nothing and
`docs/sdlc.md` puts the manual pass there. So staging is allowed on one condition, and production on
none at all. These tests are that rule, written down.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.errors import AppError
from app.seed.identity import _seed_password

_COMMITTED = "Staging#2026"
# Stand-ins for what an operator would put in SEED_PASSWORD. Named rather than inline so ruff's
# S106 does not flag every call site, and so the intent is legible: these are *not* the committed
# value, which is the whole subject of this file.
_SUPPLIED = "3AVbi-Lsr0cPMcd7"
_ANY_OTHER = "a-genuinely-different-password"
_VALID_DB = "postgresql+asyncpg://user:pw@localhost/db"


def _settings(monkeypatch: pytest.MonkeyPatch, **overrides: object) -> None:
    """Point `get_settings` at a Settings built for one environment."""
    from app.seed import identity

    built = Settings(
        _env_file=None,  # type: ignore[call-arg]
        database_url=_VALID_DB,
        jwt_secret="j" * 40,
        **overrides,  # type: ignore[arg-type]
    )
    monkeypatch.setattr(identity, "get_settings", lambda: built)


def test_local_seeds_with_the_committed_password(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing is exposed that the repository does not already publish."""
    _settings(monkeypatch, env="local")
    assert _seed_password(_COMMITTED) == _COMMITTED


def test_production_is_refused_however_it_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    """There is no argument for demo logins on a real restaurant's data, so there is no flag."""
    _settings(monkeypatch, env="production", seed_password=_ANY_OTHER)
    with pytest.raises(AppError) as raised:
        _seed_password(_COMMITTED)
    assert raised.value.code == "seed.not_local"


def test_staging_without_a_password_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """Otherwise every seeded login is the one printed in seed/organization.yaml's header."""
    _settings(monkeypatch, env="staging")
    with pytest.raises(AppError) as raised:
        _seed_password(_COMMITTED)
    assert raised.value.code == "seed.no_password"


def test_staging_with_the_committed_password_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """The half of the rule that is easy to omit.

    Requiring SEED_PASSWORD and then accepting the committed value is the original hole with a
    longer configuration path to it — and it is exactly what somebody does when the deploy fails
    and the committed password is the one they have to hand.
    """
    _settings(monkeypatch, env="staging", seed_password=_COMMITTED)
    with pytest.raises(AppError) as raised:
        _seed_password(_COMMITTED)
    assert raised.value.code == "seed.committed_password"


def test_staging_with_a_real_password_seeds_with_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """The allowed path: the supplied password is what every seeded login gets, not the committed
    one, so reading the repository tells an attacker nothing about staging."""
    _settings(monkeypatch, env="staging", seed_password=_SUPPLIED)
    assert _seed_password(_COMMITTED) == _SUPPLIED
