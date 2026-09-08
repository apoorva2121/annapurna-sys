"""Settings must fail the boot loudly. These two tests are the assertion behind that promise."""

from __future__ import annotations

import pathlib

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_VALID_URL = "postgresql+asyncpg://user:pw@localhost:5432/db"


def test_boot_fails_when_required_var_is_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_boot_fails_when_debug_is_true_outside_local() -> None:
    with pytest.raises(ValidationError, match="DEBUG=true is forbidden"):
        Settings(_env_file=None, env="staging", debug=True, database_url=_VALID_URL)


def test_boot_fails_on_a_synchronous_database_driver() -> None:
    with pytest.raises(ValidationError, match="asyncpg"):
        Settings(_env_file=None, env="local", database_url="postgresql://user:pw@localhost/db")


def test_debug_is_allowed_locally() -> None:
    settings = Settings(_env_file=None, env="local", debug=True, database_url=_VALID_URL)
    assert settings.debug is True


def test_cors_origins_parses_a_comma_separated_list() -> None:
    settings = Settings(
        _env_file=None,
        env="local",
        database_url=_VALID_URL,
        cors_origins="http://a.test, http://b.test ,",
    )
    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]


def test_unknown_setting_is_rejected() -> None:
    # extra="forbid" means a typo in .env fails the boot rather than silently doing nothing.
    with pytest.raises(ValidationError):
        # mypy is right that this argument does not exist; rejecting it at runtime is the test.
        Settings(_env_file=None, env="local", database_url=_VALID_URL, notasetting="x")  # type: ignore[call-arg]


def test_version_fields_read_the_env_vars_the_image_actually_sets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GIT_SHA", "abc1234")
    monkeypatch.setenv("BUILT_AT", "2026-09-09T04:00:00+00:00")
    settings = Settings(_env_file=None, env="local", database_url=_VALID_URL)
    assert settings.git_sha == "abc1234"
    assert settings.built_at == "2026-09-09T04:00:00+00:00"


def test_dockerfile_stamps_exactly_the_names_settings_reads() -> None:
    """Regression: the image stamped BUILD_TIME while Settings reads BUILT_AT, so /version
    reported "unknown" in every built image and no test noticed. Driving the assertion off
    model_fields means renaming the setting breaks this test rather than the deployed image."""
    dockerfile = (pathlib.Path(__file__).resolve().parents[1] / "Dockerfile").read_text(
        encoding="utf-8"
    )
    for field in ("git_sha", "built_at"):
        assert field in Settings.model_fields
        name = field.upper()
        assert f"{name}=${{{name}}}" in dockerfile, f"Dockerfile does not stamp {name}"
