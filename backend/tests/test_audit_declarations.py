"""A mutating service method that declares no audit fails the build.

**This file is M14's actual deliverable.** The decorator is what makes it satisfiable; this is the
rule. It is M00's *"a route with no declared permission fails the build"*, pointed at the second
thing that gets forgotten in exactly the same way — and `docs/modules.md` says why in one line:
*"hand-written audit calls get forgotten exactly where they matter."*

Where they matter is the rare path. The manual price override, the adjustment at the end of a bad
month, the role granted at eleven at night: each written once, in a hurry, by somebody who was
thinking about the feature rather than about the record. A code review catches the missing audit on
the day the method is written and never again.

## Two ways to declare, because there are two kinds of audit-worthy fact

`@audited` writes a **diff**: what the row was, what it became. That is most acts — a price
changed, a role granted, a till closed.

Some facts are not in the row. *"This void sent one line to the kitchen."* *"This settlement found
a dish with no recipe."* *"The payout was 2,000 rupees, and here is why."* A payout does not change
`cash_session` at all; it adds a `cash_movement`, and a diff of the till would be empty. Forcing
those into a diff would have lost the half a person actually reads, so a method may instead call
`record(...)` — **the same single writer the decorator uses** — with the fact it wants recorded.

What the guard insists on is that the method declares *something*. One writer, one rule, and the
form follows the fact.

## What counts as mutating

A public `async` method of a service class whose body adds to, deletes from or merges into the
session, or assigns to an attribute of something that is not `self`. That last one is the
interesting case — `order.status = "settled"` — and it is deliberately blunt: a heuristic that is
sometimes wrong in the direction of *asking for a declaration* costs somebody one line of
exemption, while one that is wrong the other way costs a record nobody knows is missing.

## The exemption list, and the one rule that keeps it honest

Two kinds of exemption, both carrying a reason in prose:

- **A whole module**, for a module where no act is audit-worthy: sending a message, moving a ticket
  along the rail, leaving a rating. The guard asserts such a module contains **no** `@audited`
  method — because if one act there is worth a row, the module is not uniformly exempt and the
  exemption is hiding the next one.
- **One method**, named `Class.method`, for a single act inside a module that is otherwise audited.

An exemption is a decision somebody wrote down. That is the whole mechanism: nothing here stops a
person exempting something they should not, and nothing could. What it stops is the exemption
happening *by omission*, which is how every one of these actually happens.
"""

from __future__ import annotations

import ast
import pathlib

_SERVICES = pathlib.Path(__file__).resolve().parents[1] / "app" / "services"

# Methods on the session that write. `execute()` is not here: a service issuing a bulk UPDATE would
# slip past, and the one that does (`kitchen_stream`) is exempt for its own stated reason anyway.
_WRITES = frozenset({"add", "add_all", "delete", "merge"})


MODULE_EXEMPTIONS: dict[str, str] = {
    "attachments.py": (
        "An attachment is evidence, not a change to the business. The act worth recording is what "
        "the attachment was attached to — a waste log, a complaint — and that act is audited where "
        "it happens. M11's own tests cover the upload path."
    ),
    "complaints.py": (
        "A complaint and its resolution are already a permanent, visible record with their own "
        "reference number and their own screen (M10). An audit row beside each would be a second "
        "copy of the same history, and the one a manager reads is the complaint."
    ),
    "conversations.py": (
        "Messages. M11's spec refuses message search for a retention reason, and auditing every "
        "message would rebuild exactly the corpus that refusal exists to avoid. What a person "
        "*said* is not a change to the restaurant's records."
    ),
    "feedback.py": (
        "A guest leaving a rating. The rating itself is the record, it is immutable once given, "
        "and the person who left it is a customer rather than an actor holding a login."
    ),
    "guest_session.py": (
        "A guest's table session. ADR 0009 keeps guests in a separate realm with no employee "
        "behind them, so there is no actor for a row to name."
    ),
    "kitchen.py": (
        "A ticket moving along the rail. M08's path is one-way and already fully recorded in the "
        "ticket's own timestamps — `acknowledged_at`, `started_at`, `ready_at` — which is a better "
        "record than an audit row because the kitchen screen reads it."
    ),
    "tasks.py": (
        "Tasks. Every state change a task has is already a `task_event` row with an actor and a "
        "timestamp (M11) — an append-only history built for this purpose, which the task screen "
        "renders. A parallel audit trail would be the same facts in a place nobody looks."
    ),
}

METHOD_EXEMPTIONS: dict[str, str] = {
    # ------------------------------------------------------------------ signing in
    "AuthService.logout": (
        "Ends a session and nothing else. `user_session` holds when it ended, and everything the "
        "person did while signed in is audited where it happened."
    ),
    "AuthService.switch_restaurant": (
        "Moves a session between branches the person already holds. Every act they then perform is "
        "audited at the restaurant it was performed in, which is the question somebody asks."
    ),
    "AuthService.change_own_password": (
        "Changing your own password is not an insider act; changing *somebody else's* is, and "
        "`EmployeeService.reset_password` is audited. M01's throttle already records the attempts."
    ),
    # ------------------------------------------------------------------ customers
    "CustomerService.create": (
        "**Auditing this would work against DPDP rather than for it.** An audit row holds old and "
        "new values, so recording every edit to a customer would copy their name and number into a "
        "table M10's erasure does not reach — building the retention problem the erasure exists to "
        "solve. The customer record is itself the record, it is visible on screen, and the one act "
        "that cannot be undone, erasure, *is* audited."
    ),
    "CustomerService.add_preference": "As `create`: an audit row would retain the personal data.",
    "CustomerService.remove_preference": "As `create`: an audit row would retain what was removed.",
    "CustomerService.attach_to_order": (
        "Links a customer to a bill. The bill is audited at settlement and the link is on it."
    ),
    "CustomerService.record_consent": (
        "A consent is its own append-only record with its notice version and its source "
        "(`customer_consent`, M10) — built to be the evidence, and stronger than an audit row "
        "because it holds the words the person agreed to."
    ),
    # ------------------------------------------------------------------ stock counts
    "InventoryService.open_count": (
        "A stock count is its own document with its own lines, its own approver and its own screen "
        "(M05). The audit-worthy act is the *adjustment* approving it produces, which is audited."
    ),
    "InventoryService.record_counted": (
        "Writing a counted figure onto the open count sheet. The sheet is the record, and it is "
        "visible; approving it is what moves stock, and that is audited."
    ),
    "InventoryService.submit_count": (
        "Hands the sheet to a second person. The separation of duties is the control, and "
        "`stock_count` holds who submitted and who approved. Approving it is audited."
    ),
    # ------------------------------------------------------------------ menu structure
    "MenuService.create_category": (
        "A heading on the menu. Nothing about it is price-, recipe- or stock-affecting "
        "(invariant 6), and the prices underneath it each carry their own row."
    ),
    "MenuService.create_modifier_group": (
        "An empty group of options. The *modifier* inside it carries a price, and creating or "
        "repricing one is audited."
    ),
    # ------------------------------------------------------------------ running a service
    "OrderService.mark_ready": (
        "A dish is ready. The kitchen's own timestamps are the record of that (M08)."
    ),
    "OrderService.set_busy": (
        "Busy mode on the floor, which changes how the screen behaves for the next hour and "
        "changes no money, no stock and no record."
    ),
    "OrderService.add_line": (
        "Ordering a dish is the ordinary work of a service, hundreds of times a night. What is "
        "audited is a line *removed* or *changed* after the fact, which is the act somebody would "
        "use to make a bill smaller, and the bill's own lines are the record of what was ordered."
    ),
    "OrderService.send": "Sends what was ordered to the kitchen. The tickets are the record (M08).",
    "OrderService.mark_served": "A dish reached the table. Nothing about the bill changes.",
    "OrderService.request_bill": "A table asks for the bill. Settlement is the audited act.",
    # ------------------------------------------------------------------ the floor
    "SetupService.create_dining_area": (
        "The shape of the room. Not price-, recipe- or stock-affecting, and visible to everyone "
        "who opens the floor plan."
    ),
    "SetupService.create_table": (
        "As `create_dining_area`: furniture. Where a table stands changes nothing about "
        "money, stock or a recipe."
    ),
    "SetupService.create_station": (
        "Where a dish is cooked. Routing, not money — and a dish moving station is visible on the "
        "menu item itself."
    ),
    "SetupService.set_table_status": (
        "A table becomes free, or needs cleaning. This happens a hundred times a night and is the "
        "floor moving rather than a record changing."
    ),
    # ------------------------------------------------------------------ the clock
    "ShiftService.clock_in": (
        "Clocking in *is* the record — `shift_assignment` holds the time, the person and the "
        "shift. What M12 audits is a manager **correcting** somebody's attendance afterwards, "
        "which is the act that could change who was responsible for a night."
    ),
    "ShiftService.clock_out": (
        "As `clock_in`: the time written on the assignment is itself the record, and the "
        "correction of one is what carries a row."
    ),
    # ------------------------------------------------------------------ the roster
    "ShiftService.create_shift": (
        "Defining a shift pattern — 'Evening, 17:00 to 01:00'. Planning, not attendance."
    ),
    "ShiftService.update_shift": "As `create_shift`: the pattern, not who worked it.",
    "ShiftService.assign": (
        "Putting somebody on next Tuesday. **What is audited is a *correction* to attendance after "
        "the fact** (`shift.corrected`), because that is the act that could change who was "
        "responsible for a night — and M17 freezes a published period so a later edit cannot move "
        "a score. A roster that is still in the future has nothing to rewrite."
    ),
    "ShiftService.unassign": (
        "Taking somebody off a shift that has not started — M12 refuses to unassign one that has."
    ),
}


def _methods() -> list[tuple[str, str, str, ast.AsyncFunctionDef]]:
    """Every public async method of every service class, with its module and class."""
    found: list[tuple[str, str, str, ast.AsyncFunctionDef]] = []
    for path in sorted(_SERVICES.glob("*.py")):
        if path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            for member in node.body:
                if isinstance(member, ast.AsyncFunctionDef) and not member.name.startswith("_"):
                    found.append((path.name, node.name, member.name, member))
    return found


def _writes(method: ast.AsyncFunctionDef) -> str | None:
    """Why this method counts as mutating, or `None`."""
    for node in ast.walk(method):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            owner = node.func.value
            named_session = (isinstance(owner, ast.Attribute) and owner.attr == "session") or (
                isinstance(owner, ast.Name) and owner.id == "session"
            )
            if node.func.attr in _WRITES and named_session:
                return f"session.{node.func.attr}()"
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Attribute) and not (
                    isinstance(target.value, ast.Name) and target.value.id == "self"
                ):
                    return f"assigns .{target.attr}"
    return None


def _declares_audit(
    method: ast.AsyncFunctionDef | ast.FunctionDef, helpers: dict[str, ast.AST] | None = None
) -> bool:
    """`@audited` at the signature, `record(...)` in the body, or a private helper that does one.

    The third case is real and worth allowing: three public methods write the same waiter-handover
    row — opening an order, claiming one, reassigning one — so `_waiter_audit` stays a named helper
    rather than being spelled out three times. One level of indirection, not arbitrary depth: a
    chain of helpers is exactly the shape in which an audit quietly stops being written.
    """
    for decorator in method.decorator_list:
        call = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(call, ast.Name) and call.id == "audited":
            return True
    for node in ast.walk(method):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "record"
        ):
            return True
        if helpers is not None and isinstance(node, ast.Call):
            called = node.func
            if (
                isinstance(called, ast.Attribute)
                and isinstance(called.value, ast.Name)
                and called.value.id == "self"
                and called.attr.startswith("_")
            ):
                helper = helpers.get(called.attr)
                if helper is not None and _declares_audit(helper):  # type: ignore[arg-type]
                    return True
    return False


def _helpers_of(module: str) -> dict[str, ast.AST]:
    """Every private method in a module, by name, for the one level of indirection above."""
    path = _SERVICES / module
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        member.name: member
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        for member in node.body
        if isinstance(member, ast.AsyncFunctionDef | ast.FunctionDef)
        and member.name.startswith("_")
    }


def test_the_walk_finds_the_services_it_checks() -> None:
    """An empty parse would make every assertion below pass without reading anything."""
    assert len(_methods()) > 150
    assert sum(1 for *_, method in _methods() if _writes(method)) > 80


def test_every_mutating_service_method_declares_an_audit_or_an_exemption() -> None:
    """**The rule.** A new mutating method arrives undeclared and this fails.

    The message names the method and what to do about it, because a build failure somebody cannot
    act on within a minute is a build failure somebody disables.
    """
    undeclared = [
        f"{module}::{cls}.{name}  ({_writes(method)})"
        for module, cls, name, method in _methods()
        if _writes(method)
        and not _declares_audit(method, _helpers_of(module))
        and module not in MODULE_EXEMPTIONS
        and f"{cls}.{name}" not in METHOD_EXEMPTIONS
    ]

    assert undeclared == [], (
        "These service methods change something and declare no audit:\n  "
        + "\n  ".join(undeclared)
        + "\n\nEither decorate the method with @audited(...), or add it to METHOD_EXEMPTIONS in "
        "this file with a sentence saying why the act is not worth a row. An exemption is a "
        "decision somebody wrote down; an omission is the failure this test exists for."
    )


def test_an_exempt_module_contains_no_audited_method() -> None:
    """The rule that keeps a module exemption honest.

    If one act in a module is worth a row, the module is not uniformly exempt — and the exemption
    is then hiding the *next* audit-worthy method somebody adds beside it.
    """
    contradictions = [
        f"{module}::{cls}.{name}"
        for module, cls, name, method in _methods()
        if module in MODULE_EXEMPTIONS and _declares_audit(method)
    ]

    assert contradictions == [], (
        "These modules are exempt as a whole and yet audit something:\n  "
        + "\n  ".join(contradictions)
        + "\n\nRemove the module from MODULE_EXEMPTIONS and exempt its methods one by one."
    )


def test_every_exemption_carries_a_reason() -> None:
    """A blank reason is an omission with a dictionary entry in front of it."""
    thin = [
        name
        for name, reason in (MODULE_EXEMPTIONS | METHOD_EXEMPTIONS).items()
        if len(reason.split()) < 8
    ]

    assert thin == [], f"these exemptions say too little to be a decision: {thin}"


def test_no_exemption_names_something_that_does_not_exist() -> None:
    """An exemption that outlives its method is an exemption nobody will notice is stale — and the
    method that later takes that name inherits it silently."""
    modules = {module for module, *_ in _methods()}
    methods = {f"{cls}.{name}" for _, cls, name, _ in _methods()}

    assert [module for module in MODULE_EXEMPTIONS if module not in modules] == []
    assert [method for method in METHOD_EXEMPTIONS if method not in methods] == []
