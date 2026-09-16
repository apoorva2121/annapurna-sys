"""The toolchain is pinned, and the places that pin it agree.

Finding M9, guardrail G-10. This project has already been bitten once by an unpinned dependency:
FastAPI 0.141 stopped flattening included routers into `app.routes`, which made all four generic
suites iterate an empty list and pass while testing nothing — recorded as defect 9 in
`docs/plan/m01-build-log.md`. A resolver that picks a different version on a different day is a
test suite that means something different on a different day.

Two pins have to agree in particular: `ruff` in `pyproject.toml` and the `rev` of the ruff
pre-commit hook. When they drift, the hook on a developer's machine and the `make lint` that gates
CI disagree about whether the same file is clean — and nobody notices until a commit that passed
locally fails in CI for a rule that did not exist yesterday.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent


def _pyproject_ruff_pin() -> str:
    data = tomllib.loads((_BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    dev: list[str] = data["project"]["optional-dependencies"]["dev"]
    pins = [entry for entry in dev if entry.replace(" ", "").startswith("ruff==")]
    assert len(pins) == 1, f"expected exactly one exact ruff pin in dev extras, found {pins}"
    return pins[0].split("==", 1)[1].strip()


def _pre_commit_ruff_rev() -> str:
    config = (_ROOT / ".pre-commit-config.yaml").read_text(encoding="utf-8")
    match = re.search(
        r"repo:\s*https://github\.com/astral-sh/ruff-pre-commit\s*\n\s*rev:\s*v?([0-9][^\s]*)",
        config,
    )
    assert match is not None, "could not find the ruff pre-commit hook's rev"
    return match.group(1)


def test_ruff_is_pinned_exactly_rather_than_floored() -> None:
    """A floor lets two machines run two different linters against one rule set."""
    assert _pyproject_ruff_pin()


def test_the_ruff_pin_and_the_pre_commit_hook_agree() -> None:
    assert _pyproject_ruff_pin() == _pre_commit_ruff_rev(), (
        "pyproject.toml and .pre-commit-config.yaml pin different ruff versions, so the hook and "
        "the CI gate can disagree about whether a file is clean"
    )


def _uv_executable() -> Path | None:
    """uv, wherever it is. `shutil.which` alone misses it: on Windows the venv's Scripts directory
    is on PATH only for a shell that activated it, and pytest is often started by its full path."""
    found = shutil.which("uv")
    if found:
        return Path(found)
    for directory in ("Scripts", "bin"):
        for name in ("uv.exe", "uv"):
            candidate = Path(sys.prefix) / directory / name
            if candidate.is_file():
                return candidate
    return None


def test_a_lockfile_exists() -> None:
    assert (_BACKEND / "uv.lock").is_file(), (
        "backend/uv.lock is missing — run `uv lock` in backend/"
    )


def test_the_lockfile_resolves_the_current_dependency_list() -> None:
    """`uv.lock` is what makes a build reproducible; a stale one is worse than none, because it
    claims a reproducibility the resolver is quietly ignoring.

    This asks uv whether the lock still satisfies `pyproject.toml`, rather than comparing the two
    files' modification times. mtime was wrong in both directions: it failed on an edit to a comment
    in `pyproject.toml`, where the only remedy is to `touch` a file — which teaches people that this
    gate is noise to be worked around — and it passed on a genuinely stale lock that anything had
    since rewritten for an unrelated reason. A gate whose green means "the timestamps are in a
    pleasing order" is not a gate.

    `uv lock --check` is what the Dockerfile's `uv sync --frozen` will enforce at build time, so
    this fails here rather than at a deploy.
    """
    uv = _uv_executable()
    assert uv is not None, (
        "uv was not found on PATH or in this virtualenv, so lockfile freshness cannot be checked. "
        "uv is required to build this project — see backend/Dockerfile and the Makefile."
    )
    result = subprocess.run(  # noqa: S603 - our own executable, no shell, no user input
        [str(uv), "lock", "--check"],
        cwd=_BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        "backend/uv.lock no longer resolves backend/pyproject.toml — a dependency changed without "
        f"re-locking. Run `uv lock` in backend/.\n{result.stdout}{result.stderr}"
    )


def test_the_frontend_is_locked_too() -> None:
    assert (_ROOT / "frontend" / "package-lock.json").is_file()


def test_the_coverage_floor_can_actually_fail_the_build() -> None:
    """The gate's blind spot, closed and kept closed.

    `--cov-fail-under=95` looks like it fails at 94.83%. It does not, by default: pytest-cov prints
    the verdict from `total < fail_under` and sets the exit status from
    `coverage.results.should_fail_under(total, fail_under, precision)`, which **rounds to
    `precision` first**. At the default precision of 0, `round(94.83, 0)` is 95, so the run prints
    `FAIL Required test coverage of 95% not reached` in red and exits 0.

    That is not hypothetical: `make check` reported `make check: clean` on exactly that output on
    2026-09-13, and the two obvious explanations — pytest not failing, make not propagating — had
    both already been ruled out by direct measurement. The gap is roughly half a percentage point
    wide, which is comfortably enough room for a module to land in.

    `[tool.coverage.report] precision = 2` closes it. This test is what stops the line being
    removed as cosmetic by somebody who reads it as "how many decimals to print".
    """
    from coverage.results import should_fail_under

    config = tomllib.loads((_BACKEND / "pyproject.toml").read_text(encoding="utf-8"))
    precision = config["tool"]["coverage"]["report"]["precision"]

    assert precision >= 2, (
        "coverage precision is what the fail-under comparison rounds to. At 0, a 94.83% run "
        "prints FAIL and exits 0."
    )
    # The demonstration, not just the setting: the figure that slipped through must now be caught.
    assert should_fail_under(94.83, 95, precision), "94.83% must fail a 95% floor"
    assert not should_fail_under(95.0, 95, precision), "95.00% must pass a 95% floor"
