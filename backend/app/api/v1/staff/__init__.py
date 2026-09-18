"""The employee surface.

ADR 0009: staff and guest are two applications, not two roles. This router and the guest router
share no middleware, no dependency chain and no handler. A guest request cannot physically enter
this routing tree — that is a structural property, not a discipline.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.staff import (
    attachments,
    cash,
    communication,
    complaints,
    customers,
    employees,
    inventory,
    kot,
    menu,
    orders,
    procurement,
    roles,
    setup,
    stock,
    wastage,
)

router = APIRouter()
router.include_router(attachments.router)
router.include_router(cash.router)
router.include_router(communication.router)
router.include_router(employees.router)
router.include_router(inventory.router)
router.include_router(complaints.router)
router.include_router(customers.router)
router.include_router(kot.router)
router.include_router(menu.router)
router.include_router(orders.router)
router.include_router(procurement.router)
router.include_router(roles.router)
router.include_router(setup.router)
router.include_router(stock.router)
router.include_router(wastage.router)
