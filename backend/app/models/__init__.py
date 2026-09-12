"""Every model is imported here so that `Base.metadata` is complete.

Alembic autogenerate compares the database against this metadata. A model that is defined but never
imported is invisible to that comparison, and the symptom is a migration that silently drops the
table it did not know about. Importing them in one place is what prevents that.
"""

from __future__ import annotations

from app.models.access import EmployeeRoleAssignment, Permission, Role, RolePermission
from app.models.audit import AuditLog
from app.models.base import Base
from app.models.identity import Employee, UserAccount, UserSession
from app.models.inventory import (
    StockBatch,
    StockCount,
    StockCountLine,
    StockMovement,
)
from app.models.menu import (
    MenuCategory,
    MenuItem,
    MenuItemModifierGroup,
    MenuItemVariant,
    Modifier,
    ModifierGroup,
)
from app.models.setup import DiningArea, RestaurantTable, Station, TaxGroup, TaxRate
from app.models.stock import (
    IngredientProfile,
    PreparationProfile,
    Recipe,
    RecipeLine,
    StockItem,
)
from app.models.tenancy import Organization, Restaurant

__all__ = [
    "AuditLog",
    "Base",
    "DiningArea",
    "Employee",
    "EmployeeRoleAssignment",
    "IngredientProfile",
    "MenuCategory",
    "MenuItem",
    "MenuItemModifierGroup",
    "MenuItemVariant",
    "Modifier",
    "ModifierGroup",
    "Organization",
    "Permission",
    "PreparationProfile",
    "Recipe",
    "RecipeLine",
    "Restaurant",
    "RestaurantTable",
    "Role",
    "RolePermission",
    "Station",
    "StockBatch",
    "StockCount",
    "StockCountLine",
    "StockItem",
    "StockMovement",
    "TaxGroup",
    "TaxRate",
    "UserAccount",
    "UserSession",
]
