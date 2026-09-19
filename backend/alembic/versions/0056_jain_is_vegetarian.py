"""Jain is a vegetarian option, so detach it from every non-vegetarian dish

Found by the owner on 2026-09-19, using the menu screen: a chicken curry offered
**"Jain (no onion/garlic)"**.

Jain dietary practice is vegetarian by definition. The option cannot be satisfied on a non-veg
dish under any preparation, so offering it is not a harmless extra — a Jain customer shown it on
chicken learns that the restaurant does not know what the word means.

`seed/operations.yaml` attached the group by **category**, to `MAIN_NONVEG` and `STARTER_NONVEG`
among others. The seeder now filters on the dish's own `food_type` instead, which is the only
granularity that can express the rule: `CHINESE` holds veg and non-veg dishes side by side, so no
category list could have been right. `food_type` is also the field with a statutory basis
(`docs/compliance-rules.md` §A1, the veg/non-veg mark), which is why it is never empty.

**This migration is for restaurants that already exist.** The seed fix only helps a database
seeded after it; every demo and staging database already carries the wrong rows.

**It detaches, and does not delete.** The group itself, its three modifiers and every attachment
to a vegetarian dish are left exactly as they are — the option is correct there and is one a lot
of Indian restaurants genuinely need. Only the link between the group and a non-vegetarian dish
goes.

**Matched by code, not by name.** A restaurant may have renamed "Preparation preference" to
something of its own; the code is the stable join. A restaurant that never had the group, or that
created its own unrelated group, is untouched.

**The downgrade does not restore the rows**, deliberately. Re-attaching an option that cannot be
satisfied would be re-introducing the defect, and there is no version of this product in which a
chicken dish should offer Jain. `downgrade` is therefore a no-op with a reason rather than a lie.

Revision ID: 0056_jain_is_vegetarian
Revises: 0055_m17_m18_issues
"""

from __future__ import annotations

from alembic import op

revision = "0056_jain_is_vegetarian"
down_revision = "0055_m17_m18_issues"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `menu_item_modifier_group` has no `restaurant_id` of its own — it is reached through the
    # dish — so the join is what scopes this, and it scopes it to every tenant at once, which is
    # what a data correction in a migration is for.
    op.execute(
        """
        DELETE FROM menu_item_modifier_group AS link
        USING menu_item AS item, modifier_group AS grp
        WHERE link.menu_item_id = item.id
          AND link.modifier_group_id = grp.id
          AND grp.code = 'JAIN_PREF'
          AND item.food_type <> 'veg'
        """
    )


def downgrade() -> None:
    """Deliberately does nothing.

    Restoring these rows would put "Jain" back on chicken. There is no state of this product in
    which that is correct, so the downgrade declines rather than pretending the change is
    reversible.
    """
