"""`make seed` — i.e. `python -m app.seed`, run inside the api container.

Owns its own engine and its own transaction, because nothing about seeding is a request. One
transaction for the whole run, so a failure part way through leaves no half-built demo world
behind: either all nineteen people exist or none of them do.

The two failures below are turned into distinct exit codes rather than a traceback, because both
are configuration mistakes a person can fix in one step, and a stack trace buries the sentence that
tells them which step.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.seed.counts import seed_counts
from app.seed.customers import seed_customer_feedback, seed_customers
from app.seed.identity import MissingSystemRoleError, seed_identity
from app.seed.inventory import seed_inventory
from app.seed.loader import SeedDataNotFoundError
from app.seed.menu import seed_menu
from app.seed.orders import seed_orders
from app.seed.procurement import seed_procurement
from app.seed.setup import seed_setup
from app.seed.stock import seed_stock
from app.seed.waste import seed_waste

logger = logging.getLogger("app.seed")

EXIT_OK = 0
EXIT_NO_SEED_DATA = 2
EXIT_NO_ROLE_CATALOGUE = 3


async def seed() -> None:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            summary = await seed_identity(session)
            # The floor, the stations and the tax rates. After identity, because operations.yaml
            # describes one named restaurant's floor and cannot stand on its own.
            setup = await seed_setup(session)
            # The menu. After setup, because every dish routes to a station and every variant names
            # a tax group, and both are created there.
            menu = await seed_menu(session)
            # Ingredients, preparations and recipes. Last, because a recipe references a dish
            # variant and a preparation is made at a station — both created above.
            stock = await seed_stock(session)
            # Opening stock, and the two planted signals. Last of all, because it consumes the
            # ingredients `seed_stock` just created and cannot run before they exist.
            inventory = await seed_inventory(session)
            # Suppliers, two orders and three deliveries, including one deliberate short delivery.
            # After the inventory seeder and not before: both write the stock ledger, and that one
            # refuses to run at all if any movement already exists.
            procurement = await seed_procurement(session)
            # An open order, a sent one, a settled bill with a credit note, and a till closed ₹50
            # short. After procurement: settlement writes the stock ledger too.
            # M10, and **before** the orders seeder rather than after: a customer goes on a bill
            # while it is open, because a settled order is immutable (invariant 6) and a trigger
            # enforces it. The screens count settled bills, so this ordering is what makes a
            # seeded regular somebody who has actually eaten here.
            customers = await seed_customers(session)
            orders = await seed_orders(session)
            # The twelve wastage reasons, and a few days of waste across all four stages. Last,
            # because logging waste consumes stock: it needs the opening batches and it must not
            # run before the ledger the inventory seeder refuses to open twice.
            waste = await seed_waste(session)
            # The ratings and complaints, which hang off bills that now exist.
            customers = await seed_customer_feedback(session, customers)
            # The physical count, last of all. It has to come after the orders seeder and after
            # waste, because a count's whole meaning is the gap between what the ledger believes
            # and what the shelf holds — and the ledger is only finished once everything that
            # consumes stock has run. Counting first would reconcile a book nobody had written in.
            counts = await seed_counts(session)
            # The single commit. Everything above it is provisional until this line.
            await session.commit()
    finally:
        # Always: a failure must not leave the process holding an open pool.
        await engine.dispose()

    if (
        summary.created_nothing
        and setup.created_nothing
        and menu.created_nothing
        and stock.created_nothing
        and inventory.created_nothing
        and procurement.created_nothing
        and orders.created_nothing
        and waste.reasons_created == 0
        and waste.events_created == 0
        and customers.created_nothing
        and counts.created_nothing
    ):
        logger.info("Seed data already present; nothing to do.")
        return
    logger.info(
        "Seeded %d organizations, %d restaurants, %d employees, %d logins, %d assignments.",
        summary.organizations_created,
        summary.restaurants_created,
        summary.employees_created,
        summary.logins_created,
        summary.assignments_created,
    )
    logger.info(
        "Seeded %d dining areas, %d tables, %d stations, %d tax rates.",
        setup.dining_areas_created,
        setup.tables_created,
        setup.stations_created,
        setup.tax_groups_created,
    )
    logger.info(
        "Seeded %d categories, %d dishes, %d variants, %d modifier groups, %d attachments.",
        menu.categories_created,
        menu.items_created,
        menu.variants_created,
        menu.modifier_groups_created,
        menu.attachments_created,
    )
    logger.info(
        "Seeded %d wastage reasons and %d wastage events across the four stages.",
        waste.reasons_created,
        waste.events_created,
    )
    logger.info(
        "Seeded %d ingredients, %d preparations, %d recipes.",
        stock.ingredients_created,
        stock.preparations_created,
        stock.recipes_created,
    )
    logger.info(
        "Seeded %d opening stock batches and %d deliberately negative positions.",
        inventory.batches_created,
        inventory.negatives_planted,
    )
    logger.info(
        "Seeded %d suppliers, %d orders, %d deliveries and %d deliberate short deliveries.",
        procurement.suppliers_created,
        procurement.orders_created,
        procurement.receipts_created,
        procurement.short_deliveries_planted,
    )
    logger.info(
        "Seeded %d approved stock counts (%d lines) and %d forgotten ones.",
        counts.counts_approved,
        counts.lines_counted,
        counts.counts_abandoned,
    )
    logger.info(
        "Seeded %d orders, %d invoices, %d credit notes and %d deliberately short tills.",
        orders.orders_created,
        orders.invoices_issued,
        orders.credit_notes_issued,
        orders.short_tills_planted,
    )


def run() -> int:
    configure_logging()
    try:
        asyncio.run(seed())
    except SeedDataNotFoundError as exc:
        # Much the most likely failure: the dataset lives at the repository root while the backend
        # runs from /app, so the container has to be given it explicitly.
        logger.error("%s", exc)
        return EXIT_NO_SEED_DATA
    except MissingSystemRoleError as exc:
        # Seeding before migrating. Guessing a role here would hand someone permissions that
        # nobody granted, so it refuses instead.
        logger.error("%s", exc)
        return EXIT_NO_ROLE_CATALOGUE
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(run())
