"""menu labelling - allergen statement, calories, serving size, and the licence's expiry

Backlog-issues B8 (`docs/compliance-rules.md` §A2, §A3, §B1). All nullable: NULL on
`allergen_statement` is "never asked", which a screen can show as such; a dish that contains none
says so in words.

Revision ID: 0027_menu_labelling
Revises: 0026_restaurant_settings_version
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "0027_menu_labelling"
down_revision: str | None = "0026_restaurant_settings_version"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.add_column("menu_item", sa.Column("allergen_statement", sa.Text(), nullable=True))
    op.add_column("menu_item", sa.Column("calories_kcal", sa.SmallInteger(), nullable=True))
    op.add_column("menu_item", sa.Column("serving_size", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_menu_item_calories", "menu_item", "calories_kcal IS NULL OR calories_kcal >= 0"
    )
    op.add_column("restaurant", sa.Column("fssai_licence_expires_on", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("restaurant", "fssai_licence_expires_on")
    op.drop_constraint("ck_menu_item_calories", "menu_item", type_="check")
    op.drop_column("menu_item", "serving_size")
    op.drop_column("menu_item", "calories_kcal")
    op.drop_column("menu_item", "allergen_statement")
