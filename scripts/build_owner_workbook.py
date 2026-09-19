"""Build the workbook of things only Apoorva can do, and questions only Apoorva can answer.

`docs/owner-actions.md` is the source of truth and stays that way — this script reads its three
tables and writes an .xlsx. Nothing is authored here that is not in the markdown, so a row edited
in the script would be lost on the next build, and that is deliberate. Same rule as
`build_manual_test_workbook.py`, for the same reason.

**A separate file from `Restaurant-OS-manual-tests.xlsx`, on purpose.** That one is 569 steps to
work through in order; this one is a dozen decisions to sit and think about. Mixing them makes both
harder to use — the test pass gets read as homework and the decisions get lost inside it.

Four sheets:

* **Start here** — what the two lists are and which three rows block something.
* **Your actions** — what needs you, with a Done column and a Notes column.
* **Questions for me** — each with options, my recommendation, and the cost of leaving it open.
* **Table URLs** — the live guest links, so a QR can be generated without running anything. Written
  only when a database is reachable; otherwise the sheet says how to get them, because a sheet of
  stale tokens is worse than an empty one.

Usage:
    python scripts/build_owner_workbook.py [output.xlsx]
    DATABASE_URL=... python scripts/build_owner_workbook.py   # includes the table URLs
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.worksheet.worksheet import Worksheet

_ROOT = Path(__file__).resolve().parents[1]
_SOURCE = _ROOT / "docs" / "owner-actions.md"
_DEFAULT_OUT = _ROOT / "Apoorva-actions-and-questions.xlsx"

_HEADER_FILL = PatternFill("solid", fgColor="1F3A5F")
_HEADER_FONT = Font(bold=True, color="FFFFFF", size=11)
_BLOCKER_FILL = PatternFill("solid", fgColor="FFE5E5")
_TITLE_FONT = Font(bold=True, size=14)
_WRAP = Alignment(vertical="top", wrap_text=True)
_TOP = Alignment(vertical="top")


def _clean(cell: str) -> str:
    """Markdown emphasis and links out; the person reading this is not reading markdown."""
    text = cell.strip()
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("**", "").replace("`", "")
    # A single asterisk pair is italics; a lone one is prose. Only strip matched pairs.
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    return text.replace("~~", "")


def _table_after(heading: str) -> list[list[str]]:
    """The first markdown table under a `## heading`, as rows of cleaned cells.

    Parsed rather than hand-copied so the markdown cannot drift from the workbook. A missing
    heading raises rather than producing an empty sheet — an empty sheet reads as "nothing to do".
    """
    text = _SOURCE.read_text(encoding="utf-8")
    if f"\n## {heading}\n" not in text:
        raise SystemExit(f"{_SOURCE.name} has no '## {heading}' section")
    section = text.split(f"\n## {heading}\n", 1)[1].split("\n## ", 1)[0]
    rows = []
    for line in section.split("\n"):
        stripped = line.strip()
        if not stripped.startswith("|") or set(stripped) <= set("|-: "):
            continue
        cells = [_clean(cell) for cell in stripped.strip("|").split("|")]
        rows.append(cells)
    if len(rows) < 2:
        raise SystemExit(f"'## {heading}' parsed to {len(rows)} rows — check the table")
    return rows


def _sheet(wb: Workbook, title: str, rows: list[list[str]], widths: list[int]) -> Worksheet:
    ws = wb.create_sheet(title)
    for index, width in enumerate(widths, start=1):
        ws.column_dimensions[chr(64 + index)].width = width
    for row in rows:
        ws.append(row)
    for cell in ws[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
        cell.alignment = _WRAP
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = _WRAP
    ws.freeze_panes = "A2"
    return ws


def _mark_blockers(ws: Worksheet) -> int:
    """Tint the rows that block something. The marker is in the markdown, not invented here."""
    marked = 0
    for row in ws.iter_rows(min_row=2):
        if any("🔴" in str(cell.value or "") for cell in row):
            for cell in row:
                cell.fill = _BLOCKER_FILL
            marked += 1
    return marked


def _start_here(wb: Workbook, actions: int, questions: int, blockers: int) -> None:
    ws = wb.create_sheet("Start here", 0)
    ws.column_dimensions["A"].width = 110
    lines = [
        ("Restaurant OS — what needs you, and what I need answered", _TITLE_FONT),
        ("", None),
        (
            f"{actions} actions. {questions} questions. {blockers} rows block something.",
            Font(bold=True),
        ),
        ("", None),
        ("Two lists, and they are different in kind.", Font(bold=True)),
        ("", None),
        (
            "YOUR ACTIONS are things only you can do — a console session, a payment method, a "
            "phone in your hand, a conversation with the pilot restaurant. None of them waits on "
            "me.",
            None,
        ),
        ("", None),
        (
            "QUESTIONS FOR ME are decisions I should not make alone. Each names the options, says "
            "which I would choose and why, and says what it costs to leave it open. Leaving one "
            "open is a valid answer for most of them.",
            None,
        ),
        ("", None),
        ("The rows tinted red block something:", Font(bold=True)),
        ("  A5  a restore nobody has performed — the RTO is unverified", None),
        ("  Q3  M19 analytics cannot be specced without the org-vs-branch answer", None),
        ("  Q7  the Neon plan, which A1 and A2 wait on", None),
        ("", None),
        ("Two things cannot be fixed afterwards for data already lost:", Font(bold=True)),
        (
            "  A1  Neon's history window. Six hours is how far back a restore reaches, and nobody "
            "notices a bad settlement within six hours.",
            None,
        ),
        (
            "  A3  GCP_MIN_INSTANCES = 1. Scale-to-zero kills the instance holding every open "
            "kitchen display stream.",
            None,
        ),
        ("", None),
        (
            "This sheet is generated from docs/owner-actions.md. Edit the markdown and rebuild — "
            "anything typed into the workbook is lost on the next build, except the Done and Notes "
            "columns, which are yours.",
            Font(italic=True),
        ),
        ("", None),
        (
            "The 569-step test pass is a separate file: Restaurant-OS-manual-tests.xlsx. "
            "That one is work to get through; this one is decisions to think about.",
            Font(italic=True),
        ),
    ]
    for text, font in lines:
        ws.append([text])
        cell = ws.cell(row=ws.max_row, column=1)
        cell.alignment = _WRAP
        if font is not None:
            cell.font = font


def _table_urls(wb: Workbook) -> None:
    """The live guest links, when a database is reachable.

    **Not written from a cache.** A slug can be regenerated, and a sheet of tokens that no longer
    open anything would send somebody to debug the guest app instead of rerunning this.
    """
    ws = wb.create_sheet("Table URLs")
    for column, width in zip("ABCD", (26, 18, 10, 78), strict=False):
        ws.column_dimensions[column].width = width

    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        ws.append(["No database was reachable when this was built."])
        ws.append([""])
        ws.append(["To get the links, with `make dev` running:"])
        ws.append(["  python scripts/guest_links.py --html guest-qr.html"])
        ws.append([""])
        ws.append(["That writes a page of scannable QR codes as well as printing the links."])
        for row in ws.iter_rows():
            row[0].alignment = _TOP
        return

    sys.path.insert(0, str(_ROOT / "scripts"))
    import asyncio

    from guest_links import DEFAULT_BASE, _rows

    base = os.environ.get("GUEST_BASE_URL", DEFAULT_BASE).rstrip("/")
    rows = asyncio.run(_rows(database_url))

    ws.append(["Restaurant", "Area", "Table", "URL for the QR code"])
    for restaurant, area, code, slug in rows:
        ws.append([restaurant, area, code, f"{base}/guest.html?t={slug}"])
    for cell in ws[1]:
        cell.fill = _HEADER_FILL
        cell.font = _HEADER_FONT
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = _TOP
    ws.freeze_panes = "A2"

    warning = (
        "These are LIVE links, not samples. Each opens that table's menu and its current bill "
        "with no password — that is how a QR on a table works. Treat this sheet like the printed "
        "codes: do not share it, and regenerate the slugs if it leaks."
    )
    ws.append([])
    ws.append([warning])
    ws.cell(row=ws.max_row, column=1).font = Font(bold=True, color="9C2B2B")
    ws.cell(row=ws.max_row, column=1).alignment = _WRAP


def main() -> int:
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else _DEFAULT_OUT

    actions = _table_after("Actions")
    questions = _table_after("Questions")

    wb = Workbook()
    wb.remove(wb.active)

    action_sheet = _sheet(
        wb,
        "Your actions",
        [[*actions[0], "Done", "Your notes"], *[[*row, "", ""] for row in actions[1:]]],
        [5, 46, 62, 26, 34, 8, 34],
    )
    done = DataValidation(type="list", formula1='"yes,not yet,skipped"', allow_blank=True)
    action_sheet.add_data_validation(done)
    done.add(f"F2:F{action_sheet.max_row}")

    question_sheet = _sheet(
        wb,
        "Questions for me",
        [[*questions[0], "Your answer"], *[[*row, ""] for row in questions[1:]]],
        [5, 46, 48, 44, 34, 28, 34],
    )

    _table_urls(wb)
    blockers = _mark_blockers(action_sheet) + _mark_blockers(question_sheet)
    _start_here(wb, len(actions) - 1, len(questions) - 1, blockers)

    wb.save(out)
    print(f"  {len(actions) - 1} actions, {len(questions) - 1} questions, {blockers} blockers")
    print(f"  written to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
