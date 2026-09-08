"""PostToolUse hook: validate docs and seed data the moment they change.

Reads the hook payload on stdin, works out which file was touched, and runs the matching
validator. Documentation drift and seed-data errors are cheap to fix immediately and expensive
to fix in a batch three weeks later, which is the whole point of running this on every edit.

Never blocks the turn: on failure it returns a systemMessage telling the user what broke and
how to see the detail. Exit code is always 0.
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def emit(message=None):
    if message:
        json.dump({"systemMessage": message, "suppressOutput": True}, sys.stdout)
    sys.exit(0)


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        emit()

    tool_input = payload.get("tool_input") or {}
    tool_response = payload.get("tool_response") or {}
    path = tool_input.get("file_path") or tool_response.get("filePath") or ""
    if not path:
        emit()

    rel = path.replace("\\", "/")

    if "/docs/" in rel and rel.endswith(".md"):
        script, label = "scripts/audit_docs.py", "Docs audit"
    elif "/seed/" in rel and (rel.endswith(".yaml") or rel.endswith(".yml")):
        script, label = "seed/validate.py", "Seed validation"
    else:
        emit()

    try:
        result = subprocess.run(
            [sys.executable, os.path.join(ROOT, script)],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
    except Exception:
        emit()

    if result.returncode == 0:
        emit()

    detail = [ln for ln in (result.stdout or "").splitlines() if ln.strip().startswith("[")]
    summary = detail[0].strip() if detail else (result.stderr or "").strip().splitlines()[-1:] or [""]
    if isinstance(summary, list):
        summary = summary[0]
    emit("%s FAILED after editing %s\n  %s\n  Run: python %s"
         % (label, os.path.basename(rel), summary, script))


if __name__ == "__main__":
    main()
