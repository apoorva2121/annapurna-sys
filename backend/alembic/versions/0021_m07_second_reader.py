"""m07 - second reader: a comp never outgrows its authorisation, and no cash into a counted till

Two findings from M07's independent second reader, each closed in the database as well as in the
service, so that a later code path cannot quietly reopen either.

**`order_discount.authorised_amount`.** A percentage or a comp is recomputed whenever the bill
changes, so a manager's comp on one dal used to stretch over the two more a waiter ordered after
it, while the audit row still named one. The rupee figure at the moment of authorisation is now
stored beside the running `amount`, and `amount <= authorised_amount` is a CHECK. Existing rows are
backfilled from `amount`, the figure their authoriser last saw; the follows-order trigger is paused
for that one statement because it rightly refuses to touch a settled order's discounts.

**No payment into a closed till.** A settle racing a close could post its cash into the till the
close had just counted, moving a closed till's expected cash. The service now share-locks the open
till. This trigger share-locks the till as well and refuses a closed one, so a caller that forgets
the lock fails loudly instead of corrupting the count.

Revision ID: 0021_m07_second_reader
Revises: 0020_m07_order_permissions
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0021_m07_second_reader"
down_revision: str | None = "0020_m07_order_permissions"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column(
        "order_discount", sa.Column("authorised_amount", sa.Numeric(12, 2), nullable=True)
    )
    op.execute("ALTER TABLE order_discount DISABLE TRIGGER trg_order_discount_follows_order")
    op.execute(
        "UPDATE order_discount SET authorised_amount = amount WHERE authorised_amount IS NULL"
    )
    op.execute("ALTER TABLE order_discount ENABLE TRIGGER trg_order_discount_follows_order")
    op.alter_column("order_discount", "authorised_amount", nullable=False)
    op.create_check_constraint(
        "ck_order_discount_within_authorised", "order_discount", "amount <= authorised_amount"
    )

    op.execute(
        """
        CREATE FUNCTION payment_into_open_till_only() RETURNS trigger AS $$
        DECLARE
            till_status text;
        BEGIN
            IF NEW.cash_session_id IS NULL THEN
                RETURN NEW;
            END IF;
            SELECT status INTO till_status FROM cash_session
             WHERE id = NEW.cash_session_id AND restaurant_id = NEW.restaurant_id
               FOR SHARE;
            IF till_status IS DISTINCT FROM 'open' THEN
                RAISE EXCEPTION
                    'Cash session % is closed: no payment goes into a till already counted.',
                    NEW.cash_session_id;
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_payment_into_open_till_only
        BEFORE INSERT ON payment
        FOR EACH ROW EXECUTE FUNCTION payment_into_open_till_only();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER trg_payment_into_open_till_only ON payment")
    op.execute("DROP FUNCTION payment_into_open_till_only()")
    op.drop_constraint("ck_order_discount_within_authorised", "order_discount", type_="check")
    op.drop_column("order_discount", "authorised_amount")
