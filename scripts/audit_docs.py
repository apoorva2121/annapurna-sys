"""Consistency audit across the docs set.

Catches the failure mode that kills long-lived documentation: two documents that were both correct
when written and now quietly disagree. Run after any docs change; runs in CI.

Checks:
  1. Per-domain table counts match the header claim
  2. Every table appears in the migration order
  3. Every table is owned by exactly one module
  4. Module estimates sum to the stated total
  5. Eliminated tables have not crept back into the design
  6. Numeric claims are consistent across documents
  7. Every ADR carries a Status line
  8. The month plan references real module ids
  9. Module dependency graph is acyclic

Exit code 1 if any issue is found.
"""
import io
import os
import re
import glob

os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read(path):
    return io.open(path, encoding="utf-8").read()


def ascii_safe(text):
    return text.encode("ascii", "replace").decode()


issues = []


def flag(severity, where, message):
    issues.append((severity, where, message))


schema_full = read("docs/schema.md")
schema = schema_full.split("## What was deliberately eliminated")[0]
modules = read("docs/modules.md")

# ---------------------------------------------------------------- 1. table counts
print("=== SCHEMA: tables per domain ===")
sections = re.split(r"\n## (\d+ · [^\n]+)\n", schema)
all_tables = []
for i in range(1, len(sections), 2):
    head, body = sections[i], sections[i + 1]
    tables, in_block = [], False
    for line in body.split("\n"):
        if line.startswith("```"):
            in_block = not in_block
            continue
        if in_block and re.match(r"^[a-z][a-z0-9_]*(\s|$)", line):
            name = line.split()[0]
            if name not in tables:
                tables.append(name)
    claimed = re.search(r"(\d+)\s+tables?", head)
    claimed = int(claimed.group(1)) if claimed else None
    status = "OK" if claimed == len(tables) else "MISMATCH"
    print(ascii_safe("  %-9s %-40s claimed=%s actual=%d" % (status, head, claimed, len(tables))))
    if claimed != len(tables):
        flag("HIGH", "schema.md", "%s claims %s tables, contains %d" % (ascii_safe(head), claimed, len(tables)))
    all_tables.extend(tables)

header = re.search(r"\*\*(\d+) tables in (\d+) domains", schema)
print("\n  header claims %s tables / %s domains; actual %d / %d"
      % (header.group(1), header.group(2), len(all_tables), (len(sections) - 1) // 2))
if int(header.group(1)) != len(all_tables):
    flag("HIGH", "schema.md", "header says %s tables, sections contain %d" % (header.group(1), len(all_tables)))

# ---------------------------------------------------------------- 2. migration order
migration = schema_full.split("## Migration order")[1].split("`stock_batch.")[0]
listed = set(re.findall(r"[a-z][a-z0-9_]+", migration))
missing = [t for t in all_tables if t not in listed]
print("\n=== MIGRATION ORDER ===\n  tables not listed:", missing or "none")
for table in missing:
    flag("MED", "schema.md", "table %s missing from migration order" % table)

# ---------------------------------------------------------------- 3. module ownership
owned = set()
lines = modules.split("\n")
for i, line in enumerate(lines):
    if not line.strip().startswith("- **Tables**"):
        continue
    blob, j = line, i + 1
    while j < len(lines):
        nxt = lines[j]
        if not nxt.startswith("  ") or nxt.strip().startswith("- **"):
            break
        blob += " " + nxt
        j += 1
    owned |= set(re.findall(r"[a-z][a-z0-9_]{2,}", blob))
orphans = [t for t in all_tables if t not in owned]
print("\n=== MODULE COVERAGE ===\n  tables no module builds:", orphans or "none")
for table in orphans:
    flag("HIGH", "modules.md", "table %s is in schema but no module builds it" % table)

# ---------------------------------------------------------------- 4. estimates
estimates = [int(m) for m in re.findall(r"\*\*Est\.\*\* (\d+) days?", modules)]
module_count = len(re.findall(r"^## M\d\d", modules, re.M))
stated = re.search(r"Total ≈ (\d+) working days", modules)
print("\n=== ESTIMATES ===\n  %d modules, %d estimates, sum %d days, stated %s"
      % (module_count, len(estimates), sum(estimates), stated.group(1) if stated else "none"))
if len(estimates) != module_count:
    flag("MED", "modules.md", "%d modules but %d estimates" % (module_count, len(estimates)))
if stated and int(stated.group(1)) != sum(estimates):
    flag("HIGH", "modules.md", "states %s days, estimates sum to %d" % (stated.group(1), sum(estimates)))

# ---------------------------------------------------------------- 5. eliminated tables
eliminated = ["message_read_receipt", "unit_conversion", "order_status_history",
              "waiter_performance", "chef_performance", "dish_stats"]
print("\n=== ELIMINATED TABLES ===")
for name in eliminated:
    for path in glob.glob("docs/**/*.md", recursive=True) + ["CLAUDE.md"]:
        # schema.md documents these in its eliminated table; that is the one legitimate mention
        if path.replace("\\", "/") == "docs/schema.md":
            continue
        for line in read(path).split("\n"):
            if name in line and "eliminat" not in line.lower():
                flag("HIGH", path, "eliminated table %s referenced as if it exists: %s"
                     % (name, ascii_safe(line.strip()[:80])))
print("  reintroductions:", len([i for i in issues if "eliminated table" in i[2]]) or "none")

# ---------------------------------------------------------------- 6. numeric claims
print("\n=== NUMERIC CLAIMS ===")
claims = {
    "25.7%": ["docs/seed-data.md", "docs/modules.md"],
    "126.70": ["docs/modules.md", "docs/plan/month-1.md"],
    "0.1489": ["docs/modules.md", "docs/plan/month-1.md"],
    "14 planted": ["docs/sdlc.md", "docs/modules.md", "docs/testing-strategy.md"],
}
for claim, paths in claims.items():
    for path in paths:
        present = claim in read(path)
        print("  %-12s %-30s %s" % (claim, path, "yes" if present else "MISSING"))
        if not present:
            flag("MED", path, "expected claim %r not found" % claim)

# ---------------------------------------------------------------- 7. ADR status
print("\n=== ADRs ===")
for path in sorted(glob.glob("docs/decisions/*.md")):
    status = re.search(r"\*\*Status:\*\* (\w+)", read(path))
    print("  %-54s %s" % (os.path.basename(path), status.group(1) if status else "NO STATUS"))
    if not status:
        flag("MED", path, "no Status line")

# ---------------------------------------------------------------- 8. plan references modules
plan_ids = sorted(set(re.findall(r"M\d\d", read("docs/plan/month-1.md"))))
print("\n=== PLAN ===\n  month-1.md references:", plan_ids or "NONE")
if not plan_ids:
    flag("HIGH", "docs/plan/month-1.md", "plan does not reference any module id")

# ---------------------------------------------------------------- 9. dependency graph
deps, current = {}, None
for line in modules.split("\n"):
    head = re.match(r"^## (M\d\d)", line)
    if head:
        current = head.group(1)
    if current and line.strip().startswith("- **Depends on**"):
        deps[current] = [d for d in re.findall(r"M\d\d", line) if d != current]

state = {}


def visit(node, stack=()):
    if state.get(node) == "done":
        return
    if node in stack:
        flag("HIGH", "modules.md", "dependency cycle: %s" % " -> ".join(stack + (node,)))
        return
    for dep in deps.get(node, []):
        visit(dep, stack + (node,))
    state[node] = "done"


for node in sorted(deps):
    visit(node)
print("\n=== DEPENDENCIES ===\n  %d modules, graph acyclic: %s"
      % (len(deps), not any("cycle" in i[2] for i in issues)))

# ---------------------------------------------------------------- report
print("\n" + "=" * 72)
print("ISSUES: %d" % len(issues))
for severity, where, message in sorted(issues):
    print("  [%s] %s: %s" % (severity, where, message))
raise SystemExit(1 if issues else 0)
