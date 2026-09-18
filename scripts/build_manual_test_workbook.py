"""Build the manual-test workbook the owner runs the pass from.

`docs/manual-tests/M*.md` is the source of truth and stays that way — this script reads those files
and writes an .xlsx. Nothing is authored here that is not in the markdown, so a step edited in the
script would be lost on the next build, and that is deliberate.

Three sheets:

* **How to test** — the logins, the URL, and what to do before starting. A test script whose
  preconditions live somewhere else is a test script nobody runs.
* **Test cases** — all 332 steps, one row each, with empty Result and Notes columns.
* **Bugs** — empty, for the owner to fill. Its Test ID column points back at the step that found it,
  which is what makes a bug list actionable rather than a list of complaints.

Usage:  python scripts/build_manual_test_workbook.py [output.xlsx]
"""

from __future__ import annotations

import pathlib
import re
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SOURCE = _ROOT / "docs" / "manual-tests"

_STAGING = "https://restaurant-os-api-bvsbcve2xq-as.a.run.app"

_HEADER = PatternFill("solid", fgColor="1F2937")
_HEADER_FONT = Font(color="FFFFFF", bold=True, size=11)
_MODULE_FILL = PatternFill("solid", fgColor="EEF2FF")
_WRAP = Alignment(wrap_text=True, vertical="top")

_MODULE_NAMES = {
    "M00": "Foundation — the stack runs at all",
    "M01": "Identity — signing in, roles, lockout",
    "M02": "Restaurant setup — floor, stations, tax",
    "M03": "Menu — dishes, variants, modifiers",
    "M04": "Recipes — what a dish is made of, and what it costs",
    "M05": "Inventory — the stock ledger",
    "M06": "Procurement — suppliers, orders, deliveries",
    "M07": "Orders — taking, settling, refunding",
    "M08": "Kitchen — the display and the rail",
    "M09": "Waste — logging what was thrown away",
    "M10": "Customers — regulars, feedback, complaints, guest app",
    "M11": "Communication — messages, tasks, attachments",
    "M12": "Shifts — the roster and the clock",
}


def _clean(cell: str) -> str:
    """Markdown emphasis and links out; the person reading this is not reading markdown."""
    text = cell.strip()
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # [label](url) -> label
    text = text.replace("**", "").replace("`", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _sections(markdown: str) -> dict[str, str]:
    """Map a section letter to its heading, so every step says which area it belongs to."""
    out: dict[str, str] = {}
    for line in markdown.splitlines():
        match = re.match(r"^##\s+([A-Z])\s*[·\-·�]\s*(.+)$", line)
        if match:
            out[match.group(1)] = _clean(match.group(2))
    return out


def read_steps() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(_SOURCE.glob("M*.md")):
        if "template" in path.name:
            continue
        module = path.name[:3]
        text = path.read_text(encoding="utf-8")
        sections = _sections(text)
        for line in text.splitlines():
            match = re.match(r"^\|\s*([A-Z])(\d+)\s*\|(.+?)\|(.+?)\|\s*$", line)
            if not match:
                continue
            letter, number, step, expect = match.groups()
            rows.append(
                {
                    "module": module,
                    "module_name": _MODULE_NAMES.get(module, ""),
                    "area": sections.get(letter, ""),
                    "id": f"{module}-{letter}{number}",
                    "step": _clean(step),
                    "expect": _clean(expect),
                }
            )
    return rows


def _style_header(sheet, width_map: dict[str, int]) -> None:
    for cell in sheet[1]:
        cell.fill = _HEADER
        cell.font = _HEADER_FONT
        cell.alignment = Alignment(vertical="center", wrap_text=True)
    sheet.row_dimensions[1].height = 28
    sheet.freeze_panes = "A2"
    for column, width in width_map.items():
        sheet.column_dimensions[column].width = width


def build(destination: pathlib.Path) -> int:
    rows = read_steps()
    book = Workbook()

    # ---------------------------------------------------------------- how to test
    guide = book.active
    guide.title = "How to test"
    guide.append(["Restaurant OS — manual test pass"])
    guide["A1"].font = Font(bold=True, size=14)
    lines: list[tuple[str, str]] = [
        ("", ""),
        ("Where", _STAGING),
        ("", ""),
        ("Sign in as", "owner@spicegarden.test  —  sees everything"),
        ("Other logins", "admin@ / manager@ / chef@ / waiter1@ / kitchen1@ / store@ @spicegarden.test"),
        ("Password", "All seeded logins share one password. Read it from Secret Manager:"),
        ("", "console.cloud.google.com/security/secret-manager  ->  SEED_PASSWORD  ->  View secret value"),
        ("", ""),
        ("Your own account", "apoorva.dixit21@gmail.com is a SEPARATE, EMPTY organization (Annapurna Staging)."),
        ("", "It shows no data on purpose. Use it to test the empty-restaurant path, not the features."),
        ("", ""),
        ("How to run this", "Work down the Test cases sheet. For each row: do the Step, compare with What you should see."),
        ("", "Put Pass or Fail in the Result column. Anything that is not clearly a pass is a fail."),
        ("", "When something fails, add a row to the Bugs sheet and put its Bug ID back in the row."),
        ("", ""),
        ("If a step needs data that is not there", "Say so in Notes rather than skipping it. Missing data is itself a finding."),
        ("Judgement steps", "Some steps ask whether wording is good enough to act on. Your opinion IS the test result."),
        ("", ""),
        ("Total steps", str(len(rows))),
        ("Modules", ", ".join(sorted({row["module"] for row in rows}))),
    ]
    for label, value in lines:
        guide.append([label, value])
    for cell in guide["A"]:
        # Only *set* a font when one is wanted. Assigning `cell.font` back to itself hands openpyxl
        # a StyleProxy rather than a Font, and it fails with "unhashable type: 'StyleProxy'" —
        # an error that names the symptom and not the line that caused it.
        if cell.value and cell.row > 1:
            cell.font = Font(bold=True)
        cell.alignment = Alignment(vertical="top")
    guide.column_dimensions["A"].width = 24
    guide.column_dimensions["B"].width = 110
    for row in guide.iter_rows(min_col=2, max_col=2):
        for cell in row:
            cell.alignment = _WRAP

    # ---------------------------------------------------------------- test cases
    cases = book.create_sheet("Test cases")
    cases.append(
        ["Module", "What this module is", "Area", "Test ID", "Step - what to do",
         "What you should see", "Result", "Notes", "Bug ID"]
    )
    for row in rows:
        cases.append(
            [row["module"], row["module_name"], row["area"], row["id"],
             row["step"], row["expect"], "", "", ""]
        )
    _style_header(
        cases,
        {"A": 9, "B": 34, "C": 30, "D": 11, "E": 62, "F": 62, "G": 9, "H": 30, "I": 9},
    )
    for row in cases.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = _WRAP
        if row[0].row % 2 == 0:
            for cell in row:
                cell.fill = _MODULE_FILL

    verdict = DataValidation(type="list", formula1='"Pass,Fail,Blocked,Skipped"', allow_blank=True)
    verdict.error = "Use Pass, Fail, Blocked or Skipped."
    cases.add_data_validation(verdict)
    verdict.add(f"G2:G{len(rows) + 1}")
    cases.auto_filter.ref = f"A1:I{len(rows) + 1}"

    # ---------------------------------------------------------------- bugs
    bugs = book.create_sheet("Bugs")
    bugs.append(
        ["Bug ID", "Test ID", "Module", "Screen / URL", "What I did",
         "What I expected", "What I saw", "How bad", "Screenshot", "Status", "Notes"]
    )
    _style_header(
        bugs,
        {"A": 9, "B": 11, "C": 9, "D": 28, "E": 46, "F": 46, "G": 46,
         "H": 12, "I": 22, "J": 12, "K": 34},
    )
    severity = DataValidation(
        type="list", formula1='"Blocker,Major,Minor,Cosmetic,Question"', allow_blank=True
    )
    status = DataValidation(type="list", formula1='"Open,Fixed,Wont fix,Not a bug"', allow_blank=True)
    for validation, column in ((severity, "H"), (status, "J")):
        bugs.add_data_validation(validation)
        validation.add(f"{column}2:{column}400")
    bugs.auto_filter.ref = "A1:K1"

    # An example row, greyed, so the shape is obvious. Row 2 so it sorts first and is easy to delete.
    bugs.append(
        ["EG", "M05-B1", "M05", "/stock/on-hand",
         "Signed in as owner, opened Stock on hand",
         "A banner saying 1 item has been used without a recorded delivery",
         "No banner at all", "Major", "(paste or link)", "Open",
         "DELETE THIS EXAMPLE ROW"]
    )
    for cell in bugs[2]:
        cell.font = Font(italic=True, color="9CA3AF")
        cell.alignment = _WRAP

    destination.parent.mkdir(parents=True, exist_ok=True)
    book.save(destination)
    print(f"  {len(rows)} test steps across {len({r['module'] for r in rows})} modules")
    print(f"  written to {destination}")
    return 0


if __name__ == "__main__":
    out = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else _ROOT / "Restaurant-OS-manual-tests.xlsx"
    sys.exit(build(out))
