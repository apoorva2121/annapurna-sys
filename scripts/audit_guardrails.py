"""R9 · the guardrails become a gate.  `docs/engineering-guardrails.md` G-20.

G-20 says it plainly: *"Every rule in this table gets a mechanical check in `make check` **or** an
explicit 'manual' status with the item that will mechanise it. A rule nobody can grep for is a
wish."* Until this script existed, twenty rules were wishes.

**The M06 session is why this is no longer deferred.** `make check` reported `make check: clean` on
a run whose own output said `FAIL Required test coverage of 95% not reached` — pytest-cov compares
`round(total, 0) < fail_under` for the exit status while printing the verdict unrounded, so the
floor had a blind spot half a percentage point wide and nothing said so. One rule, found by
accident. The guardrails table lists nineteen more in the same position.

---

## What this script does, and the thing it deliberately does *not* do

It would be easy, and wrong, to write a script that enforces all twenty rules today. Four of them
depend on work that is **deliberately deferred** — argon2 off the event loop (P1-9, deferred to
measured load or M08), Sentry redaction (R3, deferred until a DSN exists), the production smoke
test (R4/R7, needs a deploy), and the `docs/security.md` tagging sweep (G-7). A gate that is red on
the day it ships is a gate somebody switches off in a fortnight, and then the twenty rules are
wishes again with an extra file to maintain.

So it does two jobs instead:

**1 · Enforce what can be enforced now.** Layering, the regression tests R1 bought, and no personal
files committed at the root. These pass today and the script fails the build the moment they stop.

**2 · Keep the table honest.** Every row must either name an enforcement artefact *that exists on
disk*, or carry a status saying it is manual and naming the chunk that will mechanise it. And the
status is cross-checked against `docs/audit/remediation-plan.md`: a row that says "manual → R2"
when R2 is **done** is a stale claim, and a row that claims "enforced" by a chunk still deferred is
a false one. Either way the build fails and somebody has to make the sentence true.

The second job is the one that matters. It is the difference between a document that describes the
controls and a document that *is* the controls — and it is the property whose absence let R9 itself
sit two modules past its own trigger without anything noticing.
"""

import io
import os
import re
import subprocess
import sys

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(path):
    return io.open(path, encoding="utf-8").read()


def ascii_safe(text):
    """The console here is cp1252 and the docs are full of en dashes and arrows.

    `audit_docs.py` carries the same helper for the same reason. Without it the script crashes
    while *printing its findings* — which is a check that fails in the one way that tells you
    nothing about the code."""
    return text.encode("ascii", "replace").decode()


issues = []


def flag(severity, where, message):
    issues.append((severity, where, message))


def walk(root, suffix=".py"):
    for base, _dirs, names in os.walk(root):
        if "__pycache__" in base:
            continue
        for name in names:
            if name.endswith(suffix):
                yield os.path.join(base, name).replace("\\", "/")


# ---------------------------------------------------------------- G-8 · layering is enforced
#
# "A route calls exactly one service method; a service never writes select(/update(/delete( — it
# calls a repository method." Finding D7: auth.py routes called repositories and the services built
# SQL. R8b fixed it; this is what stops it coming back.
print("=== G-8: LAYERING ===")

# **The leading dot is the whole check.** `select(...)` is a service building a statement, which
# is finding D7. `self.session.delete(row)` is the ORM's unit-of-work delete on a row that was
# already fetched through a repository — and `session.add` / `session.flush` / `session.delete` is
# the established pattern in every service here (the route commits, the service flushes). The first
# version of this regex matched both and reported two honest lines, one of which predates R8b's
# layering cleanup and survived it.
_SQL_CALL = re.compile(r"(?<![A-Za-z_.])(select|insert|update|delete)\s*\(")

service_hits = []
for path in walk("backend/app/services"):
    for number, line in enumerate(read(path).split("\n"), 1):
        stripped = line.strip()
        # Comments and docstring prose talk about SQL constantly in this codebase; only code counts.
        if stripped.startswith("#") or stripped.startswith("*"):
            continue
        if _SQL_CALL.search(line):
            service_hits.append("%s:%d" % (path, number))

print("  services building SQL:", service_hits or "none")
for hit in service_hits:
    flag("HIGH", "G-8", "a service builds SQL directly, which belongs in a repository: %s" % hit)

# **Repository *classes*, not the string "app.repositories".** Four route modules import
# DEFAULT_PAGE_SIZE from repositories/base.py, and a page-size constant is not a repository — the
# rule is about a route reaching past its service to the database, not about where a number lives.
# Writing this check against the import path would have failed on four honest lines and taught the
# next person that the script cries wolf.
_REPOSITORY_CLASS = re.compile(r"\b([A-Z][A-Za-z0-9]*Repository)\b")

api_hits = []
for path in walk("backend/app/api"):
    if path.endswith("/deps.py"):
        # deps.py is where the actor is assembled, which genuinely needs two repositories. It is
        # the one exemption and it is named in G-8 itself.
        continue
    for number, line in enumerate(read(path).split("\n"), 1):
        if _REPOSITORY_CLASS.search(line) and not line.strip().startswith("#"):
            api_hits.append("%s:%d" % (path, number))

print("  routes touching a repository:", api_hits or "none")
for hit in api_hits:
    flag("HIGH", "G-8", "a route reaches a repository directly, bypassing its service: %s" % hit)


# ---------------------------------------------------------------- G-1 · the writes that survive
#
# "A write that must survive a failed request is committed by the service before it raises."
# P1-1 was invisible to 262 tests. R1 bought two regression tests; losing either would make the
# finding invisible again, and both are the kind of test that looks deletable to somebody tidying.
print("\n=== G-1: THE FAILURE-PATH WRITES STILL HAVE TESTS ===")

REQUIRED_TESTS = {
    "backend/tests/test_lockout_persistence.py": "test_a_failed_attempt_is_remembered_after_the_request_ends",
    "backend/tests/test_review_regressions.py": "test_a_replayed_refresh_token_kills_the_family_over_http",
}
for path, function in REQUIRED_TESTS.items():
    present = os.path.exists(path) and ("def %s" % function) in read(path)
    print("  %-55s %s" % (function, "present" if present else "MISSING"))
    if not present:
        flag(
            "HIGH",
            "G-1",
            "%s is gone from %s — P1-1's counter or its replay revocation is untested again"
            % (function, path),
        )


# ---------------------------------------------------------------- G-16 · commit discipline
#
# "No personal or binary files at the repository root" (M14, D9).
#
# **Tracked files, not the working directory.** `Apoorva-Tasks.xlsx` sits at the root right now and
# is gitignored on purpose; failing on it would fail on every developer's local scratch file, which
# is the fastest way to get a check deleted. What D9 was about is what gets *committed*.
print("\n=== G-16: NO BINARIES COMMITTED AT THE ROOT ===")

_BINARY_AT_ROOT = re.compile(r"^[^/]+\.(xlsx|xls|docx|doc|pptx|pdf|png|jpg|jpeg|zip|exe)$", re.I)

try:
    tracked = subprocess.run(
        ["git", "ls-files"], capture_output=True, text=True, check=True
    ).stdout.split("\n")
except (OSError, subprocess.CalledProcessError) as exc:  # pragma: no cover - git is always here
    tracked = []
    flag("MED", "G-16", "could not list tracked files: %s" % exc)

root_binaries = [name for name in tracked if _BINARY_AT_ROOT.match(name.strip())]
print("  tracked binaries at root:", root_binaries or "none")
for name in root_binaries:
    flag("HIGH", "G-16", "%s is committed at the repository root" % name)


# ---------------------------------------------------------------- G-6 and G-7 · ratchets
#
# **These two rules are not satisfied today and cannot be made so by this script.** Argon2 really
# does run on the event loop (P1-9, deferred to measured load or M08), and `docs/security.md` really
# does carry two tags across seventeen sections (G-7's sweep, never scheduled). Enforcing either
# outright would make the build red on the day the gate shipped, and a red gate gets switched off
# within a fortnight.
#
# So they ratchet instead: the debt is measured, written down, and **not allowed to grow**. A new
# argon2 call site or a new untagged control section fails the build; paying the debt down lets
# somebody lower the baseline. That is the honest middle between "enforced" and "a wish", and it is
# the only basis on which R9 can claim to have covered these two rows at all.
print("\n=== G-6 / G-7: RATCHETS ON DEBT THAT MAY NOT GROW ===")

# Measured 2026-09-13 by running this script. Lower them as the debt is paid; never raise them.
#
# The second was briefly set to 15, by subtracting the two tagged *lines* from the seventeen
# headings. Both tags turned out to live in one section, so the real figure was 16 and the ratchet
# reported a violation that was arithmetic rather than a regression. A baseline is measured, never
# computed - which is the same mistake, in miniature, that the coverage gate made.
ARGON2_CALLSITE_BASELINE = 8
UNTAGGED_SECTION_BASELINE = 16

_ARGON2 = re.compile(r"(?<![A-Za-z_.])(verify_password|hash_password)\s*\(")

argon2_sites = []
for path in walk("backend/app"):
    if path.endswith("core/security.py"):
        continue
    for number, line in enumerate(read(path).split("\n"), 1):
        # A call already handed to a worker thread is exactly what G-6 asks for.
        if _ARGON2.search(line) and "to_thread" not in line:
            argon2_sites.append("%s:%d" % (path, number))

print(
    "  argon2 call sites on the event loop: %d (baseline %d)"
    % (len(argon2_sites), ARGON2_CALLSITE_BASELINE)
)
if len(argon2_sites) > ARGON2_CALLSITE_BASELINE:
    flag(
        "HIGH",
        "G-6",
        "%d argon2 call sites, up from a baseline of %d. P1-9 is deferred, but the debt may not "
        "grow: put the new one behind asyncio.to_thread. Sites: %s"
        % (len(argon2_sites), ARGON2_CALLSITE_BASELINE, ", ".join(argon2_sites)),
    )
elif len(argon2_sites) < ARGON2_CALLSITE_BASELINE:
    flag(
        "LOW",
        "G-6",
        "only %d argon2 call sites now, below the baseline of %d - lower "
        "ARGON2_CALLSITE_BASELINE so the ratchet keeps its grip"
        % (len(argon2_sites), ARGON2_CALLSITE_BASELINE),
    )

# G-7: a control paragraph that does not say whether it is built is finding D5 exactly -
# `docs/security.md` listed CSP, HSTS, MFA, rate limiting and RLS as present when none existed.
security = read("docs/security.md")
sections = re.split(r"\n#{2,3} ", security)[1:]
untagged = [
    block.split("\n")[0].strip()
    for block in sections
    if "[built:" not in block and "[planned:" not in block
]
print(
    "  untagged sections in security.md: %d (baseline %d)"
    % (len(untagged), UNTAGGED_SECTION_BASELINE)
)
if len(untagged) > UNTAGGED_SECTION_BASELINE:
    flag(
        "HIGH",
        "G-7",
        "%d untagged sections in docs/security.md, up from %d. Every control paragraph carries "
        "[built: Mxx] or [planned: Mxx]; a section that does not say is how D5 happened"
        % (len(untagged), UNTAGGED_SECTION_BASELINE),
    )
elif len(untagged) < UNTAGGED_SECTION_BASELINE:
    flag(
        "LOW",
        "G-7",
        "only %d untagged sections now, below the baseline of %d - lower "
        "UNTAGGED_SECTION_BASELINE so the ratchet keeps its grip"
        % (len(untagged), UNTAGGED_SECTION_BASELINE),
    )


# ---------------------------------------------------------------- G-20 · the table cannot lie
#
# The meta-check, and the reason this script earns its place. Every row of the guardrails table
# must either name an artefact that exists, or say it is manual and name the chunk that will
# mechanise it — and that status is cross-checked against the remediation plan's own state table.
print("\n=== G-20: THE GUARDRAILS TABLE IS HONEST ===")

guardrails = read("docs/engineering-guardrails.md")
plan = read("docs/audit/remediation-plan.md")

# | G-1 | rule | why | enforced by | status |
_ROW = re.compile(r"^\|\s*(G-\d+)\s*\|(.+?)\|(.+?)\|(.+?)\|(.+?)\|\s*$", re.M)
rows = _ROW.findall(guardrails)
print("  rules in the table:", len(rows))
if len(rows) < 15:
    flag(
        "HIGH",
        "G-20",
        "only %d rules parsed from the guardrails table; the table or this parser has changed "
        "shape, and a parser that finds nothing makes every check below vacuous" % len(rows),
    )

# Which remediation chunks are done, from the plan's own state table.
# | R1 | what | findings | ☑ **done** — … | commit |
_CHUNK = re.compile(r"^\|\s*(R\d+[a-z]?)\s*\|(?:[^|]*\|){2}\s*(.+?)\|", re.M)
chunk_state = {chunk: state.strip() for chunk, state in _CHUNK.findall(plan)}
done_chunks = {chunk for chunk, state in chunk_state.items() if "done" in state}
print("  remediation chunks done:", ", ".join(sorted(done_chunks)) or "none")
if not chunk_state:
    flag("HIGH", "G-20", "no chunks parsed from the remediation plan's state table")

# Any path-looking token in the "enforced by" column has to exist. A row citing a test file that
# was renamed is a control that reads as present and is not.
_PATH = re.compile(r"`([A-Za-z0-9_./-]+\.(?:py|json|yaml|yml|md))`")

for rule, _text, _why, enforced_by, status in rows:
    enforced_by, status = enforced_by.strip(), status.strip()
    plain_status = status.replace("*", "").lower()

    for candidate in _PATH.findall(enforced_by):
        # Cited bare (`conftest.py`) or repo-relative; try both, plus the two roots that matter.
        if not any(
            os.path.exists(prefix + candidate)
            for prefix in (
                "",
                "backend/",
                "backend/app/",
                "backend/app/core/",
                "backend/tests/",
                "scripts/",
            )
        ):
            flag(
                "HIGH",
                "G-20",
                "%s claims to be enforced by %s, which does not exist" % (rule, candidate),
            )

    # **Starts with**, not "contains". The first version was `"enforced" in status and "half" not
    # in status` — a substring test with a patch over the one status ("half enforced") it got
    # wrong. It then misread G-16, whose honest status is "enforced for the root-file half; the
    # clean-tree half stays manual", as not-enforced, and reported a stale row that was not stale.
    # A status is a claim about a row's state, so read the claim it leads with.
    claims_enforced = plain_status.lstrip().startswith("enforced")
    cited_chunks = set(re.findall(r"R\d+[a-z]?", status))

    # **A row may cite `R8` while the plan splits it into `R8a` and `R8b`.** Matching the id
    # literally let G-9 sit stale: it says "manual -> R8", R8b is done, and R8b deliberately
    # *declined* the deletion G-9's own "enforced by" column promises. A bare id therefore matches
    # its lettered parts too, or the check has a hole exactly where a chunk got split.
    def _resolve(chunk):
        if chunk in chunk_state:
            return {chunk}
        return {known for known in chunk_state if known.startswith(chunk)}

    resolved = set()
    for chunk in cited_chunks:
        resolved |= _resolve(chunk)
    cited_chunks = resolved or cited_chunks

    # "ratcheted" is a third honest state, and the script has to know the word or it reports its
    # own output as a wish. It means: the rule is not satisfied, the debt is measured here, and a
    # new violation fails the build. G-6 and G-7 are in it.
    ratcheted = "ratchet" in plain_status

    if not claims_enforced and not ratcheted and not cited_chunks and "manual" not in plain_status:
        flag(
            "HIGH",
            "G-20",
            "%s has neither a mechanical check nor a status naming the chunk that will give it "
            "one — which is G-20's definition of a wish" % rule,
        )

    # A row still pointing at a chunk that has since been finished is a stale claim: either the
    # chunk did not actually mechanise it, or the status was never updated. Both need a human.
    stale = {chunk for chunk in cited_chunks if chunk in done_chunks}
    if stale and not claims_enforced and not ratcheted:
        flag(
            "MED",
            "G-20",
            "%s says %s but %s is marked done in the remediation plan — either it was mechanised "
            "and the status is stale, or it was not and the plan is"
            % (rule, status, ", ".join(sorted(stale))),
        )

    # And the reverse: claiming enforcement from a chunk nobody has done yet.
    unfinished = {
        chunk for chunk in cited_chunks if chunk in chunk_state and chunk not in done_chunks
    }
    if claims_enforced and unfinished:
        flag(
            "HIGH",
            "G-20",
            "%s claims to be enforced, but %s is not done"
            % (rule, ", ".join(sorted(unfinished))),
        )


# ---------------------------------------------------------------- deferrals whose trigger fired
#
# Every deferral in the remediation plan carries a trigger — "when a public URL exists", "when real
# staff are on real WiFi". A trigger that has quietly been met turns a deferral into a gap nobody
# is looking at. Two of them are mechanically detectable, so they are checked here; the rest stay
# a human's job, which the plan says plainly.
print("\n=== DEFERRALS WHOSE TRIGGER HAS FIRED ===")

# G-12: R3 is deferred *because* SENTRY_DSN stays unset. If a DSN is ever committed as a default,
# the redaction work is no longer optional and `before_send` has to be there.
config = read("backend/app/core/config.py")
main = read("backend/app/main.py")
dsn_defaulted = re.search(r"sentry_dsn\s*:\s*[^=\n]*=\s*['\"][^'\"]+['\"]", config)
print("  sentry DSN has a non-empty default:", bool(dsn_defaulted))
if dsn_defaulted and "before_send" not in main:
    flag(
        "HIGH",
        "G-12",
        "a Sentry DSN is configured by default but main.py passes no before_send — R3's deferral "
        "was conditional on the DSN staying unset",
    )

# G-14: if R4/R7 is marked done, the deploy happened, and `make smoke-prod` must exist.
makefile = read("Makefile")
deploy_done = any(chunk in done_chunks for chunk in ("R4", "R7"))
print("  deploy chunk (R4/R7) done:", deploy_done)
if deploy_done and "smoke-prod:" not in makefile:
    flag("HIGH", "G-14", "R4/R7 is done but there is no `make smoke-prod` target")


# ---------------------------------------------------------------- report
print("\n" + "=" * 72)
print("GUARDRAIL ISSUES: %d" % len(issues))
for severity, where, message in sorted(issues):
    print(ascii_safe("  [%s] %s: %s" % (severity, where, message)))
if issues:
    print("\nEach of these is a rule in docs/engineering-guardrails.md that has stopped being true.")
sys.exit(1 if issues else 0)
