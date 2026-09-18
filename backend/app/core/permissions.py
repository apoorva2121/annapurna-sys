"""Loads and validates the access-control catalogue in permissions.json.

The JSON file is the editable source of truth; this module is the typed, validated view of it that
the rest of the application uses. Validation happens at import time, so a malformed catalogue fails
the boot in the same way a malformed Settings does — loudly, before anyone depends on it.

`PermissionCode` exists so route declarations are checked by mypy. A route asking for a permission
string that is not in the catalogue would otherwise be a permission no role can hold, which reads
as "mysteriously denied" rather than as an error.
"""

from __future__ import annotations

import json
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, model_validator

_CATALOGUE_PATH = Path(__file__).with_name("permissions.json")

# Fail closed: anything we cannot identify is treated as the least senior thing there is.
MOST_JUNIOR_RANK = 9_999

# The top of the ladder. Named rather than written as a bare 0 because `may_reset_password` turns
# on it, and "0" in a comparison there reads as an off-by-one rather than as "the owner".
OWNER_RANK = 0


class PermissionCode(StrEnum):
    """The permissions M01 declares. Mirrors permissions.json, asserted by a test."""

    EMPLOYEE_VIEW = "employee.view"
    EMPLOYEE_CREATE = "employee.create"
    EMPLOYEE_EDIT = "employee.edit"
    EMPLOYEE_DEACTIVATE = "employee.deactivate"
    EMPLOYEE_ROLE_ASSIGN = "employee.role.assign"
    # S105 reads any constant named *PASSWORD* as a hardcoded credential. This is a permission
    # code. Suppressed here rather than project-wide, because the rule is worth keeping.
    EMPLOYEE_PASSWORD_RESET = "employee.password.reset"  # noqa: S105
    ROLE_VIEW = "role.view"
    # M02. Owner and admin only: a manager runs a shift, and changing what a day means or what tax
    # is charged is not running a shift (M02 spec decision 1).
    RESTAURANT_CONFIGURE = "restaurant.configure"
    # M03. Three, not two, because `seed/organization.yaml`'s P1 design already drew the line and
    # drew it better than the spec's first draft did: a manager may fix a dish name or add Friday's
    # special (`menu.manage`) and may not change what anything costs (`menu.price`). The design
    # withholds the second from a manager by name. A binary permission cannot express that — it
    # either hands over the money path or stops the manager doing their job.
    MENU_VIEW = "menu.view"
    MENU_MANAGE = "menu.manage"
    MENU_PRICE = "menu.price"
    # M04. The interesting line is the one that is *absent*: a chef holds `recipe.manage` and not
    # `cost.view`. `seed/organization.yaml` says why — "a chef sees grams, not rupees" — so the
    # recipe editor and the dish-cost screen are different surfaces behind different permissions,
    # and the person who owns the recipe is deliberately not shown what it costs.
    RECIPE_VIEW = "recipe.view"
    RECIPE_MANAGE = "recipe.manage"
    COST_VIEW = "cost.view"

    # M05. These five come straight from `seed/organization.yaml`'s P1 design rather than being
    # invented here — an earlier draft coined `stock.move` and `stock.count.approve`, and
    # `tests/test_permissions_catalogue.py` correctly refused them as enforced-but-undesigned.
    # The design is finer-grained than the invention was, and the grants carry real meaning: the
    # chef holds `stock.produce` and NOT `stock.receive`, because a kitchen turns ingredients into
    # gravy but does not sign for the sack at the door.
    STOCK_VIEW = "stock.view"
    STOCK_RECEIVE = "stock.receive"
    STOCK_PRODUCE = "stock.produce"
    STOCK_ADJUST = "stock.adjust"
    STOCK_COUNT = "stock.count"

    # M06. Three, again straight from `seed/organization.yaml`. The line worth reading is the one
    # between `purchase.manage` and `stock.receive`: raising an order and signing for a delivery
    # are different acts, and posting a receipt writes the stock ledger, so it keeps the ledger's
    # permission. The design's own grants then give separation of duties for free — the accountant
    # holds `purchase.manage` and not `stock.receive`, so the person who reconciles invoices can
    # order and can never receive; the chef holds neither, so a kitchen cannot book in a sack it
    # then cooks.
    SUPPLIER_VIEW = "supplier.view"
    SUPPLIER_MANAGE = "supplier.manage"
    PURCHASE_MANAGE = "purchase.manage"

    # M07. Six straight from `seed/organization.yaml`'s P1 design, and one amendment to it. The
    # waiter's grants are the design's line: `order.settle`, because the person at the table takes
    # the money, and NOT `order.void` or `order.discount`, which the design itself calls the
    # classic leakage vectors. `cash.manage` is the amendment: the design had no cash permission,
    # so the M07 spec added one for owner and manager, in the design file first, which is the only
    # order the design-subset test permits. A waiter takes cash and never closes the till.
    ORDER_VIEW = "order.view"
    ORDER_CREATE = "order.create"
    ORDER_MODIFY = "order.modify"
    ORDER_SETTLE = "order.settle"
    ORDER_VOID = "order.void"
    ORDER_DISCOUNT = "order.discount"
    CASH_MANAGE = "cash.manage"

    # Backlog-issues B2 (2026-09-13). Busy mode on the floor: a settled table is free at once
    # instead of being cleared first. Owner and manager, added to the design first — it changes how
    # every table behaves, so it is not a waiter's switch. Mark ready needs no new permission: it
    # sits behind `order.create`, because whoever seats a table is whoever clears it.
    FLOOR_MANAGE = "floor.manage"

    # Waiter assignment (2026-09-14). Choosing who serves a table when opening it for someone else,
    # and moving an order between waiters with a reason. Owner and manager: a waiter claims only an
    # order nobody is serving (`order.modify`), because taking a busy table takes its credit.
    ORDER_ASSIGN = "order.assign"

    # M08. Both already in `seed/organization.yaml`'s P1 design, so this module amends nothing —
    # the first module since M05 that needed no addition to it.
    #
    # The line worth reading is the waiter's: `kot.view` and **not** `kot.update`. The floor
    # watches the kitchen and does not drive it. Neither code can mark anything served, because a
    # dish is served when it reaches a table and the kitchen cannot see the table — that stays on
    # the order path, behind permissions the waiter already holds. It is also the control against a
    # rail being cleared of food that never left the pass: marking everything ready settles nothing,
    # it only makes the gap to `served_at` visible.
    KOT_VIEW = "kot.view"
    KOT_UPDATE = "kot.update"

    # M09. Both already in `seed/organization.yaml`, so this module amends the design not at all —
    # the second in a row, after M08.
    #
    # The split is a separation of duties rather than a convenience: the people who log most of the
    # waste, the chef and the kitchen staff, hold `wastage.log` and **not** `wastage.approve`.
    # Logging theft as waste is the one thing this module cannot prevent, only make visible and
    # expensive, and an approver who is never the person logging is what makes the expensive
    # reasons — expiry, quality rejection — cost somebody a conversation.
    #
    # A waiter holds neither. Waste is a kitchen and storeroom event; a dish a customer sent back is
    # recorded by whoever takes it off the bill.
    WASTAGE_LOG = "wastage.log"
    WASTAGE_APPROVE = "wastage.approve"

    # M10. All four already in `seed/organization.yaml`, so this module amends the design not at
    # all — the third in a row, and the reason it keeps mattering is that the shipped catalogue must
    # be a *subset* of that design, so a fifth code invented here would be changing the design from
    # inside an implementation.
    #
    # **A waiter holds `customer.view` and `feedback.view`**, which is the design being right rather
    # than generous: `docs/customer-experience.md` puts the regular's card on the waiter's screen -
    # "7th visit, usually orders Butter Chicken + Butter Naan, no onion/garlic" - and a waiter who
    # cannot see a customer cannot greet one. They hold neither `customer.manage` nor
    # `complaint.manage`: editing somebody's details and owning a complaint are accountable acts.
    #
    # The kitchen roles hold none of the four. A chef sees grams, not diners; the allergy that must
    # reach them reaches them on the ticket, copied when the customer was attached.
    #
    # What `customer.view` does **not** grant is the whole organization. A person sees the customers
    # of the restaurant they are working in; handling a second branch is an assignment, which is
    # M01's gesture and not a permission at all.
    CUSTOMER_VIEW = "customer.view"
    CUSTOMER_MANAGE = "customer.manage"
    FEEDBACK_VIEW = "feedback.view"
    COMPLAINT_MANAGE = "complaint.manage"
    # M11. Four codes, and **not one of them is new**: `seed/organization.yaml`'s P1 design
    # already carried exactly these, and already granted three of them to every role including
    # `cleaner`. Reading the design before writing the migration removed three inventions
    # (`conversation.view`, `attachment.manage`, `task.manage`) and one whole feature.
    #
    # **`message.send` is the whole communication surface**, deliberately. There is no
    # `conversation.view`, because the control that matters is *participation*: you read a thread
    # because a participant row says so, and no permission catalogue can express "this thread, not
    # that one". The attachment routes declare it for the same reason - it means "may use the
    # mechanism", and whether you may attach to a particular thing is decided by whether you may
    # write that thing.
    #
    # **The task split is the design's own, read literally.** `task.view` lets anybody write down
    # their own work; giving work to somebody else is `task.assign`, which is the owner's and the
    # manager's. That is what keeps a chef able to note "deep-clean the fryer" without holding a
    # permission the design withheld from them on purpose.
    MESSAGE_SEND = "message.send"
    TASK_VIEW = "task.view"
    TASK_ASSIGN = "task.assign"
    TASK_COMPLETE = "task.complete"


class PermissionSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    resource: str
    action: str
    description: str

    @model_validator(mode="after")
    def _code_matches_resource_and_action(self) -> PermissionSpec:
        expected = f"{self.resource}.{self.action}"
        if self.code != expected:
            raise ValueError(f"permission {self.code!r} should be {expected!r}")
        return self


class RoleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    name: str
    # Seniority. Lower is more senior; see `may_assign_rank`. This is what stops privilege
    # escalation, because permissions alone cannot: in M01 a manager and an owner hold the same
    # seven permissions, so a "you may not grant what you do not hold" rule would permit a manager
    # to make themselves an owner.
    rank: int
    description: str
    permissions: tuple[str, ...]


class Catalogue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    permissions: tuple[PermissionSpec, ...]
    roles: tuple[RoleSpec, ...]

    @model_validator(mode="after")
    def _roles_grant_only_known_permissions(self) -> Catalogue:
        # The typo guard. A role granting "employee.veiw" would otherwise be a permission nobody
        # holds, discovered by a person locked out of a screen mid-service.
        known = {permission.code for permission in self.permissions}
        for role in self.roles:
            unknown = sorted(set(role.permissions) - known)
            if unknown:
                raise ValueError(f"role {role.code!r} grants unknown permissions: {unknown}")
        return self

    @model_validator(mode="after")
    def _codes_are_unique(self) -> Catalogue:
        for label, codes in (
            ("permission", [permission.code for permission in self.permissions]),
            ("role", [role.code for role in self.roles]),
        ):
            duplicates = sorted({code for code in codes if codes.count(code) > 1})
            if duplicates:
                raise ValueError(f"duplicate {label} codes: {duplicates}")
        return self


@lru_cache
def load_catalogue() -> Catalogue:
    raw = json.loads(_CATALOGUE_PATH.read_text(encoding="utf-8"))
    # Keys beginning with an underscore are documentation for whoever edits the file next.
    payload = {key: value for key, value in raw.items() if not key.startswith("_")}
    return Catalogue.model_validate(payload)


CATALOGUE = load_catalogue()


def permissions_for_role(role_code: str) -> frozenset[str]:
    """Every permission a role template grants. Empty for a role that has nothing to do yet."""
    for role in CATALOGUE.roles:
        if role.code == role_code:
            return frozenset(role.permissions)
    return frozenset()


def rank_for_role(role_code: str) -> int:
    """The seniority of a role. An unknown role is treated as the most junior possible, so a bad
    lookup can never accidentally confer authority."""
    for role in CATALOGUE.roles:
        if role.code == role_code:
            return role.rank
    return MOST_JUNIOR_RANK


def may_assign_rank(actor_rank: int, target_rank: int) -> bool:
    """May someone of `actor_rank` grant a role of `target_rank`?

    Sideways and downward, never upward. A manager may appoint another manager or any junior role
    — lateral appointment is not escalation — but may not create anyone more senior than
    themselves. Combined with the service's refusal to let anyone edit their own roles, this closes
    both the direct route (promote myself) and the indirect one (promote an ally, have them
    promote me).
    """
    return target_rank >= actor_rank


def may_reset_password(actor_rank: int, target_rank: int) -> bool:
    """May someone of `actor_rank` set a new password for someone of `target_rank`?

    **Stricter than `may_assign_rank`, and deliberately so.** Appointing a peer is not escalation —
    a manager may appoint another manager. *Acting as* a peer is, because a password is the ability
    to be that person: every order, void, discount and audit row afterwards names the victim, and
    nothing distinguishes it from them doing it themselves (P1-6).

    So this requires **strictly** more senior, with one exception: two owners. Rank 0 is the top of
    the ladder, and a rule of "strictly more senior" would leave co-owners unable to help each other
    and an owner locked out of their own restaurant with no recovery path at all — which in a
    business with no support desk means the product is gone.

    Note this is about *authority*, not visibility; the caller has already established that the
    actor may see the target, and `most_senior_rank_anywhere` is what it must pass as `target_rank`.
    """
    if actor_rank == OWNER_RANK and target_rank == OWNER_RANK:
        return True
    return actor_rank < target_rank
