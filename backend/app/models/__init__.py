"""Every model is imported here so that `Base.metadata` is complete.

Alembic autogenerate compares the database against this metadata. A model that is defined but never
imported is invisible to that comparison, and the symptom is a migration that silently drops the
table it did not know about. Importing them in one place is what prevents that.
"""

from __future__ import annotations

from app.models.access import EmployeeRoleAssignment, Permission, Role, RolePermission
from app.models.audit import AuditLog, Issue
from app.models.base import Base
from app.models.communication import (
    Attachment,
    CommStreamCursor,
    Conversation,
    ConversationParticipant,
    Message,
    Task,
    TaskEvent,
)
from app.models.compliance import ComplianceEvent, ComplianceFinding
from app.models.customers import (
    Complaint,
    Customer,
    CustomerConsent,
    CustomerPreference,
    Feedback,
    FeedbackLine,
)
from app.models.identity import Employee, UserAccount, UserSession
from app.models.inventory import (
    StockBatch,
    StockCount,
    StockCountLine,
    StockMovement,
)
from app.models.kitchen import KotStreamCursor, KotTicket, KotTicketLine
from app.models.menu import (
    MenuCategory,
    MenuItem,
    MenuItemModifierGroup,
    MenuItemVariant,
    Modifier,
    ModifierGroup,
)
from app.models.notifications import Notification
from app.models.orders import (
    CashCount,
    CashMovement,
    CashSession,
    CreditNote,
    CreditNoteLine,
    IdempotencyKey,
    Invoice,
    Order,
    OrderCharge,
    OrderDiscount,
    OrderLine,
    OrderLineModifier,
    OrderTable,
    Payment,
)
from app.models.performance import (
    IncentiveScheme,
    PerformanceNote,
    PerformancePeriod,
    PerformanceScore,
    RecognitionAward,
)
from app.models.procurement import (
    GoodsReceipt,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
    Supplier,
)
from app.models.setup import DiningArea, RestaurantTable, Station, TaxGroup, TaxRate
from app.models.shifts import Shift, ShiftAssignment
from app.models.stock import (
    IngredientProfile,
    PreparationProfile,
    Recipe,
    RecipeLine,
    StockItem,
)
from app.models.tenancy import Organization, Restaurant
from app.models.waste import WastageEvent, WastageReason

__all__ = [
    "Attachment",
    "AuditLog",
    "Base",
    "CashCount",
    "CashMovement",
    "CashSession",
    "CommStreamCursor",
    "Complaint",
    "ComplianceEvent",
    "ComplianceFinding",
    "Conversation",
    "ConversationParticipant",
    "CreditNote",
    "CreditNoteLine",
    "Customer",
    "CustomerConsent",
    "CustomerPreference",
    "DiningArea",
    "Employee",
    "EmployeeRoleAssignment",
    "Feedback",
    "FeedbackLine",
    "GoodsReceipt",
    "GoodsReceiptLine",
    "IdempotencyKey",
    "IncentiveScheme",
    "IngredientProfile",
    "Invoice",
    "Issue",
    "KotStreamCursor",
    "KotTicket",
    "KotTicketLine",
    "MenuCategory",
    "MenuItem",
    "MenuItemModifierGroup",
    "MenuItemVariant",
    "Message",
    "Modifier",
    "ModifierGroup",
    "Notification",
    "Order",
    "OrderCharge",
    "OrderDiscount",
    "OrderLine",
    "OrderLineModifier",
    "OrderTable",
    "Organization",
    "Payment",
    "PerformanceNote",
    "PerformancePeriod",
    "PerformanceScore",
    "Permission",
    "PreparationProfile",
    "PurchaseOrder",
    "PurchaseOrderLine",
    "Recipe",
    "RecipeLine",
    "RecognitionAward",
    "Restaurant",
    "RestaurantTable",
    "Role",
    "RolePermission",
    "Shift",
    "ShiftAssignment",
    "Station",
    "StockBatch",
    "StockCount",
    "StockCountLine",
    "StockItem",
    "StockMovement",
    "Supplier",
    "Task",
    "TaskEvent",
    "TaxGroup",
    "TaxRate",
    "UserAccount",
    "UserSession",
    "WastageEvent",
    "WastageReason",
]
