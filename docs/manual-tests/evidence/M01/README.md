# Manual-test evidence — M00 and M01

Screenshots captured during the human manual pass. They are kept because a passed checklist is a
claim and a screenshot is the thing itself: `docs/plan/m00-build-log.md` and `m01-build-log.md`
record that these passes happened, and this is what they looked like.

| File | Shows |
|---|---|
| `M00-connectivity-check.png` | The M00 connectivity screen reporting the API reachable |
| `M00-docker-stack.png` | The compose stack running, taken while clearing the Docker blocker |

Moved here from the repository root by finding D9 — evidence belongs beside the script it belongs
to, not loose at the top of the repository.

**Note on the first image:** Commit and Built read `unknown`, which is correct locally. They are
stamped by `docker build --build-arg GIT_SHA=… BUILT_AT=…` and only carry real values in an image
built by CI.
