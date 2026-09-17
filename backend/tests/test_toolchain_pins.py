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


# ---------------------------------------------------------------------------------------------
# The dev tools live in an *extra*, and every place that installs them has to say so.
#
# CI failed four runs in a row on this: `uv sync --frozen --project backend` installs the runtime
# dependencies and nothing else, because `[project.optional-dependencies]` is an extra rather than
# a PEP 735 dependency-group, and `uv sync` does not install extras unless asked. The next step,
# `ruff check .`, then died with "command not found" about ninety seconds in — which reads like a
# broken toolchain rather than a missing flag.
#
# It stayed invisible locally because an existing `.venv` already had the tools from an earlier
# install, and `make check` never recreates one.


def _ci_yaml() -> str:
    return (_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def _makefile() -> str:
    return (_ROOT / "Makefile").read_text(encoding="utf-8")


def _make_target(name: str) -> list[str]:
    """The recipe lines of one Makefile target."""
    lines = _makefile().splitlines()
    out: list[str] = []
    inside = False
    for line in lines:
        if line.startswith(f"{name}:"):
            inside = True
            continue
        if inside:
            if line.startswith("\t"):
                out.append(line.strip())
            elif line.strip() and not line.startswith("#"):
                break
    return out


def test_every_uv_sync_that_needs_the_dev_tools_asks_for_the_extra() -> None:
    """ruff, mypy, pytest and pip-audit are all in the `dev` extra. A sync without it produces a
    venv that looks fine and has none of them."""
    for haystack, where in (
        (_ci_yaml(), "ci.yml"),
        ("\n".join(_make_target("setup")), "make setup"),
    ):
        for line in haystack.splitlines():
            # A comment explaining the flag is not a command that needs it.
            if "uv sync" not in line or line.strip().startswith("#"):
                continue
            assert "--extra dev" in line or "--all-extras" in line, (
                f"{where} runs `{line.strip()}` without --extra dev. The dev tools are declared in "
                "[project.optional-dependencies], so this installs none of them and the next step "
                "fails with 'command not found'."
            )


def test_ci_pins_uv_the_way_the_image_does() -> None:
    """The project pins ruff exactly and explains why. uv is what *installs* ruff, so an unpinned
    uv is the same class of drift one level further down — and its default behaviour around extras
    and groups has changed between releases."""
    dockerfile = (_BACKEND / "Dockerfile").read_text(encoding="utf-8")
    image_pin = re.search(r"pip install uv==([0-9.]+)", dockerfile)
    assert image_pin is not None, "backend/Dockerfile no longer pins uv"

    ci_pin = re.search(r"uv==([0-9.]+)", _ci_yaml())
    assert ci_pin is not None, (
        "ci.yml installs uv without a version. The image pins "
        f"{image_pin.group(1)}; CI resolving a different one is how the same commit gets two "
        "different toolchains."
    )
    assert ci_pin.group(1) == image_pin.group(1), (
        f"ci.yml pins uv {ci_pin.group(1)}, backend/Dockerfile pins {image_pin.group(1)}."
    )


def test_the_ci_docs_job_runs_every_validator_the_gate_runs() -> None:
    """ci.yml's own header: add a step to the Makefile gate and add it here in the same PR, or the
    two drift and the local gate stops meaning anything. Three validators had drifted out."""
    gate = {line.split()[-1] for line in _make_target("audit-docs") if line.startswith("python ")}
    ci = _ci_yaml()
    missing = sorted(script for script in gate if script not in ci)
    assert not missing, (
        f"`make check` runs {sorted(gate)} but ci.yml never runs {missing}. "
        "A validator that only runs on a laptop is a validator that stops running."
    )


def test_every_path_ci_exports_is_absolute() -> None:
    """The second half of the same CI failure, and the one that survived the first fix.

    `uv sync --extra dev` installed ruff, mypy and pytest correctly — the run log shows
    `+ ruff==0.16.6` — and `ruff check` still died with "command not found". GITHUB_PATH entries
    are used verbatim, and every step in the backend job sets `working-directory: backend`, so the
    relative entry `backend/.venv/bin` was looked for at `backend/backend/.venv/bin`.

    It passed for months because CI installed uv with `--upgrade`: an older uv put the tools
    somewhere already on PATH, so the broken entry never mattered. A newer one creates
    `backend/.venv`, and the latent bug became the visible one.
    """
    for line in _ci_yaml().splitlines():
        if "GITHUB_PATH" not in line or line.strip().startswith("#"):
            continue
        exported = re.search(r'echo\s+"([^"]+)"\s*>>\s*"?\$GITHUB_PATH', line)
        assert exported is not None, f"cannot read the GITHUB_PATH export in: {line.strip()}"
        value = exported.group(1)
        assert value.startswith("$") or value.startswith("/"), (
            f"ci.yml exports the relative path {value!r} to GITHUB_PATH. Steps run with "
            "working-directory set, so a relative entry resolves against the wrong directory and "
            "the tools become unreachable while appearing installed. Use $GITHUB_WORKSPACE."
        )
