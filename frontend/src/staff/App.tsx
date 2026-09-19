import type { ReactElement } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';

import { Permission } from '@shared/permissions';
import { RequireAuth, RequirePermission } from '@staff/auth/guards';
import { AppShell } from '@staff/components/AppShell';
import EmployeeScreen from '@staff/screens/EmployeeScreen';
import DishCostScreen from '@staff/screens/DishCostScreen';
import GoodsReceiptScreen from '@staff/screens/GoodsReceiptScreen';
import NewPurchaseOrderScreen from '@staff/screens/NewPurchaseOrderScreen';
import PurchaseOrdersScreen from '@staff/screens/PurchaseOrdersScreen';
import SuppliersScreen from '@staff/screens/SuppliersScreen';
import SupplierVarianceScreen from '@staff/screens/SupplierVarianceScreen';
import StockCountScreen from '@staff/screens/StockCountScreen';
import StockOnHandScreen from '@staff/screens/StockOnHandScreen';
import StockProduceScreen from '@staff/screens/StockProduceScreen';
import StockReceiveScreen from '@staff/screens/StockReceiveScreen';
import BillScreen from '@staff/screens/BillScreen';
import BillsScreen from '@staff/screens/BillsScreen';
import CashScreen from '@staff/screens/CashScreen';
import InvoiceScreen from '@staff/screens/InvoiceScreen';
import KitchenScreen from '@staff/screens/KitchenScreen';
import KitchenTicketScreen from '@staff/screens/KitchenTicketScreen';
import FloorPlanScreen from '@staff/screens/FloorPlanScreen';
import OrderScreen from '@staff/screens/OrderScreen';
import TableMapScreen from '@staff/screens/TableMapScreen';
import MenuItemScreen from '@staff/screens/MenuItemScreen';
import MenuScreen from '@staff/screens/MenuScreen';
import MenuCodesScreen from '@staff/screens/MenuCodesScreen';
import ShiftsSetupScreen from '@staff/screens/ShiftsSetupScreen';
import ModifierGroupsScreen from '@staff/screens/ModifierGroupsScreen';
import StockItemsScreen from '@staff/screens/StockItemsScreen';
import HomeScreen from '@staff/screens/HomeScreen';
import InboxScreen from '@staff/screens/InboxScreen';
import LoginScreen from '@staff/screens/LoginScreen';
import MyShiftsScreen from '@staff/screens/MyShiftsScreen';
import NewEmployeeScreen from '@staff/screens/NewEmployeeScreen';
import ProfileScreen from '@staff/screens/ProfileScreen';
import RecipeScreen from '@staff/screens/RecipeScreen';
import RosterScreen from '@staff/screens/RosterScreen';
import AuditScreen from '@staff/screens/AuditScreen';
import MyPerformanceScreen from '@staff/screens/MyPerformanceScreen';
import ComplianceScreen from '@staff/screens/ComplianceScreen';
import WorkloadScreen from '@staff/screens/WorkloadScreen';
import NotificationsScreen from '@staff/screens/NotificationsScreen';
import DesignGalleryScreen from '@staff/screens/DesignGalleryScreen';
import DishPerformanceScreen from '@staff/screens/DishPerformanceScreen';
import SalesReportScreen from '@staff/screens/SalesReportScreen';
import TodayScreen from '@staff/screens/TodayScreen';
import VarianceReportScreen from '@staff/screens/VarianceReportScreen';
import WasteReportScreen from '@staff/screens/WasteReportScreen';
import RestaurantSettingsScreen from '@staff/screens/RestaurantSettingsScreen';
import StaffListScreen from '@staff/screens/StaffListScreen';
import StationsScreen from '@staff/screens/StationsScreen';
import TaskScreen from '@staff/screens/TaskScreen';
import TasksScreen from '@staff/screens/TasksScreen';
import ThreadScreen from '@staff/screens/ThreadScreen';
import TaxRatesScreen from '@staff/screens/TaxRatesScreen';
import ComplaintsScreen from '@staff/screens/ComplaintsScreen';
import CustomerScreen from '@staff/screens/CustomerScreen';
import CustomersScreen from '@staff/screens/CustomersScreen';
import FeedbackScreen from '@staff/screens/FeedbackScreen';
import WasteScreen from '@staff/screens/WasteScreen';
import WasteSummaryScreen from '@staff/screens/WasteSummaryScreen';

/**
 * The staff application's routes.
 *
 * Every staff route sits inside `RequireAuth`, and the ones that need a permission additionally
 * sit inside `RequirePermission`. Both are presentation: the server authorises every request on
 * its own, so a route reachable by typing its URL is refused with a readable message rather than a
 * blank screen (manual test C3).
 */
export default function App(): ReactElement {
  return (
    <Routes>
      <Route path="/login" element={<LoginScreen />} />

      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<HomeScreen />} />
        <Route path="profile" element={<ProfileScreen />} />
        {/* M11. Every role holds these, cleaner included, so the guards are here for the same
            reason as everywhere else — presentation — rather than to draw a line. */}
        <Route
          path="messages"
          element={
            <RequirePermission permission={Permission.MESSAGE_SEND}>
              <InboxScreen />
            </RequirePermission>
          }
        />
        <Route
          path="messages/:conversationId"
          element={
            <RequirePermission permission={Permission.MESSAGE_SEND}>
              <ThreadScreen />
            </RequirePermission>
          }
        />
        <Route
          path="tasks"
          element={
            <RequirePermission permission={Permission.TASK_VIEW}>
              <TasksScreen />
            </RequirePermission>
          }
        />
        <Route
          path="tasks/:taskId"
          element={
            <RequirePermission permission={Permission.TASK_VIEW}>
              <TaskScreen />
            </RequirePermission>
          }
        />
        {/* M17. The workload screen is behind `performance.view.team` because it is about the
            roster; a person's own figures are behind nothing at all, because ADR 0011 makes
            `performance.view.own` a structural guarantee held by every role — a guard here would
            imply it could be absent. */}
        <Route
          path="workload"
          element={
            <RequirePermission permission={Permission.PERFORMANCE_VIEW_TEAM}>
              <WorkloadScreen />
            </RequirePermission>
          }
        />
        <Route path="my-performance" element={<MyPerformanceScreen />} />
        {/* M14. The trail is the owner's, the administrator's and the accountant's — the P1
            design withholds it from the manager, because the person who runs the floor is
            frequently the subject of the record. The centre has no permission at all: what it
            shows is decided per condition by what each person can act on, so a guard here would
            be a second, weaker copy of that rule. */}
        <Route
          path="audit"
          element={
            <RequirePermission permission={Permission.AUDIT_VIEW}>
              <AuditScreen />
            </RequirePermission>
          }
        />
        <Route path="alerts" element={<NotificationsScreen />} />
        {/* M18. Behind `compliance.view`, which the manager holds and the floor does not.
            Opening this route *is* the check — the request behind it evaluates the rule
            catalogue and writes what it found, because ADR 0005 leaves no background job. */}
        <Route
          path="compliance"
          element={
            <RequirePermission permission={Permission.COMPLIANCE_VIEW}>
              <ComplianceScreen />
            </RequirePermission>
          }
        />
        {/* M13. Two permissions, and the split is the P1 design's: a manager reads the
            operations and an accountant reads the books. The financial screens are ones a
            manager does not have rather than ones with blanks in them — a disabled figure is an
            invitation to go looking for the endpoint. */}
        <Route
          path="reports"
          element={
            <RequirePermission permission={Permission.REPORT_OPERATIONAL_VIEW}>
              <TodayScreen />
            </RequirePermission>
          }
        />
        <Route
          path="reports/dishes"
          element={
            <RequirePermission permission={Permission.REPORT_OPERATIONAL_VIEW}>
              <DishPerformanceScreen />
            </RequirePermission>
          }
        />
        <Route
          path="reports/waste"
          element={
            <RequirePermission permission={Permission.REPORT_OPERATIONAL_VIEW}>
              <WasteReportScreen />
            </RequirePermission>
          }
        />
        <Route
          path="reports/sales"
          element={
            <RequirePermission permission={Permission.REPORT_FINANCIAL_VIEW}>
              <SalesReportScreen />
            </RequirePermission>
          }
        />
        <Route
          path="reports/variance"
          element={
            <RequirePermission permission={Permission.REPORT_FINANCIAL_VIEW}>
              <VarianceReportScreen />
            </RequirePermission>
          }
        />
        {/* M12. `shift.view` is held by every role — the permission opens the screen and the
            scope decides the content, so a waiter sees their own shifts and who is on now while
            staffing and corrections stay behind `shift.manage`. */}
        <Route
          path="shifts"
          element={
            <RequirePermission permission={Permission.SHIFT_VIEW}>
              <MyShiftsScreen />
            </RequirePermission>
          }
        />
        <Route
          path="shifts/roster"
          element={
            <RequirePermission permission={Permission.SHIFT_VIEW}>
              <RosterScreen />
            </RequirePermission>
          }
        />
        <Route
          path="staff"
          element={
            <RequirePermission permission={Permission.EMPLOYEE_VIEW}>
              <StaffListScreen />
            </RequirePermission>
          }
        />
        <Route
          path="staff/new"
          element={
            <RequirePermission permission={Permission.EMPLOYEE_CREATE}>
              <NewEmployeeScreen />
            </RequirePermission>
          }
        />
        <Route
          path="staff/:employeeId"
          element={
            <RequirePermission permission={Permission.EMPLOYEE_VIEW}>
              <EmployeeScreen />
            </RequirePermission>
          }
        />

        {/* Setup. One permission for the whole surface — owner and admin only, because a manager
            runs a shift and changing what a day means or what tax is charged is not that. */}
        <Route
          path="settings"
          element={
            <RequirePermission permission={Permission.RESTAURANT_CONFIGURE}>
              <RestaurantSettingsScreen />
            </RequirePermission>
          }
        />
        <Route
          path="settings/floor"
          element={
            <RequirePermission permission={Permission.RESTAURANT_CONFIGURE}>
              <FloorPlanScreen />
            </RequirePermission>
          }
        />
        <Route
          path="settings/stations"
          element={
            <RequirePermission permission={Permission.RESTAURANT_CONFIGURE}>
              <StationsScreen />
            </RequirePermission>
          }
        />
        {/* The menu. `menu.view` for reading, and the write routes guard themselves — a manager
            holds `menu.manage` but not `menu.price`, so the screen renders the price control
            conditionally rather than offering one that 403s. */}
        <Route
          path="menu"
          element={
            <RequirePermission permission={Permission.MENU_VIEW}>
              <MenuScreen />
            </RequirePermission>
          }
        />
        <Route
          path="menu/options"
          element={
            <RequirePermission permission={Permission.MENU_VIEW}>
              <ModifierGroupsScreen />
            </RequirePermission>
          }
        />
        <Route
          // Behind `menu.manage`, not `menu.view`: every waiter holds `menu.view` — they read the
          // menu to take an order — and has no use for a table of database keys. The narrower
          // grant is the easy one to widen later.
          path="menu/codes"
          element={
            <RequirePermission permission={Permission.MENU_MANAGE}>
              <MenuCodesScreen />
            </RequirePermission>
          }
        />
        <Route
          path="menu/:itemId"
          element={
            <RequirePermission permission={Permission.MENU_VIEW}>
              <MenuItemScreen />
            </RequirePermission>
          }
        />
        {/* Stock and cost. Two permissions, because the P1 design separates them: a chef reads
            recipes and may not see rupees, a manager sees rupees and may not change a recipe. */}
        <Route
          path="stock"
          element={
            <RequirePermission permission={Permission.RECIPE_VIEW}>
              <StockItemsScreen />
            </RequirePermission>
          }
        />
        {/* The chef's editor, reached from a dish's variant and from the cost screen. Behind
            `recipe.view`: reading a recipe is the kitchen's job, and the screen itself withholds
            every write from anyone without `recipe.manage`. */}
        <Route
          path="recipes/:variantId"
          element={
            <RequirePermission permission={Permission.RECIPE_VIEW}>
              <RecipeScreen />
            </RequirePermission>
          }
        />
        <Route
          path="costs"
          element={
            <RequirePermission permission={Permission.COST_VIEW}>
              <DishCostScreen />
            </RequirePermission>
          }
        />
        <Route
          path="stock/on-hand"
          element={
            <RequirePermission permission={Permission.STOCK_VIEW}>
              <StockOnHandScreen />
            </RequirePermission>
          }
        />
        <Route
          path="stock/receive"
          element={
            <RequirePermission permission={Permission.STOCK_RECEIVE}>
              <StockReceiveScreen />
            </RequirePermission>
          }
        />
        <Route
          path="stock/produce"
          element={
            <RequirePermission permission={Permission.STOCK_PRODUCE}>
              <StockProduceScreen />
            </RequirePermission>
          }
        />
        <Route
          path="stock/count"
          element={
            <RequirePermission permission={Permission.STOCK_COUNT}>
              <StockCountScreen />
            </RequirePermission>
          }
        />
        {/* M06 procurement. Four permissions across five routes, and the split is the design's:
            reading is `supplier.view`, changing a supplier is `supplier.manage`, raising an order
            is `purchase.manage`, and **booking in a delivery is `stock.receive`** — because it
            writes the stock ledger, so it keeps the ledger's permission. An accountant therefore
            reaches the orders and never the receiving screen, which is separation of duties rather
            than an oversight. */}
        <Route
          path="purchasing/suppliers"
          element={
            <RequirePermission permission={Permission.SUPPLIER_VIEW}>
              <SuppliersScreen />
            </RequirePermission>
          }
        />
        <Route
          path="purchasing/suppliers/:supplierId/variance"
          element={
            <RequirePermission permission={Permission.SUPPLIER_VIEW}>
              <SupplierVarianceScreen />
            </RequirePermission>
          }
        />
        <Route
          path="purchasing/orders"
          element={
            <RequirePermission permission={Permission.SUPPLIER_VIEW}>
              <PurchaseOrdersScreen />
            </RequirePermission>
          }
        />
        <Route
          path="purchasing/orders/new"
          element={
            <RequirePermission permission={Permission.PURCHASE_MANAGE}>
              <NewPurchaseOrderScreen />
            </RequirePermission>
          }
        />
        <Route
          path="purchasing/orders/:poId/receive"
          element={
            <RequirePermission permission={Permission.STOCK_RECEIVE}>
              <GoodsReceiptScreen />
            </RequirePermission>
          }
        />
        {/* M07. The waiter's three screens: the floor behind order.view, taking an order behind
            order.modify, and the bill behind order.settle — each the permission its first write
            needs, so a role that cannot act never lands on a screen full of refusals. */}
        <Route
          path="floor"
          element={
            <RequirePermission permission={Permission.ORDER_VIEW}>
              <TableMapScreen />
            </RequirePermission>
          }
        />
        <Route
          path="orders/:orderId"
          element={
            <RequirePermission permission={Permission.ORDER_MODIFY}>
              <OrderScreen />
            </RequirePermission>
          }
        />
        <Route
          path="orders/:orderId/bill"
          element={
            <RequirePermission permission={Permission.ORDER_SETTLE}>
              <BillScreen />
            </RequirePermission>
          }
        />
        {/* M08. The kitchen display, behind kot.view — which a waiter holds too, deliberately:
            the floor watches the kitchen. The buttons that drive it need kot.update, and the rail
            renders those conditionally rather than offering controls that 403. */}
        <Route
          path="kitchen"
          element={
            <RequirePermission permission={Permission.KOT_VIEW}>
              <KitchenScreen />
            </RequirePermission>
          }
        />
        <Route
          path="kitchen/:ticketId"
          element={
            <RequirePermission permission={Permission.KOT_VIEW}>
              <KitchenTicketScreen />
            </RequirePermission>
          }
        />
        {/* M09. Logging waste is a kitchen and storeroom act — a waiter holds neither permission.
            The summary sits behind stock.view, which everyone in the kitchen has: seeing what was
            thrown away is not the same power as throwing it away. */}
        <Route
          path="waste"
          element={
            <RequirePermission permission={Permission.WASTAGE_LOG}>
              <WasteScreen />
            </RequirePermission>
          }
        />
        <Route
          path="waste/summary"
          element={
            <RequirePermission permission={Permission.STOCK_VIEW}>
              <WasteSummaryScreen />
            </RequirePermission>
          }
        />
        {/* M10. A waiter reads a customer and reads feedback — `docs/customer-experience.md` puts
            the regular's card on their screen, and a rating is about a table they served. Editing
            somebody's details, erasing them at their request, and owning a complaint are a
            manager's. What `customer.view` does *not* grant is the organisation: a person reads the
            customers of the branch they are working in, and a second branch is an assignment. */}
        <Route
          path="customers"
          element={
            <RequirePermission permission={Permission.CUSTOMER_VIEW}>
              <CustomersScreen />
            </RequirePermission>
          }
        />
        <Route
          path="customers/:customerId"
          element={
            <RequirePermission permission={Permission.CUSTOMER_VIEW}>
              <CustomerScreen />
            </RequirePermission>
          }
        />
        <Route
          path="feedback"
          element={
            <RequirePermission permission={Permission.FEEDBACK_VIEW}>
              <FeedbackScreen />
            </RequirePermission>
          }
        />
        <Route
          path="complaints"
          element={
            <RequirePermission permission={Permission.COMPLAINT_MANAGE}>
              <ComplaintsScreen />
            </RequirePermission>
          }
        />
        {/* M07 chunk K. A settled bill behind order.void, the permission both of its writes need,
            and the till behind cash.manage. A waiter holds neither, so reaches neither. */}
        <Route
          path="bills"
          element={
            <RequirePermission permission={Permission.ORDER_VOID}>
              <BillsScreen />
            </RequirePermission>
          }
        />
        <Route
          path="bills/:orderId"
          element={
            <RequirePermission permission={Permission.ORDER_VOID}>
              <InvoiceScreen />
            </RequirePermission>
          }
        />
        <Route
          path="cash"
          element={
            <RequirePermission permission={Permission.CASH_MANAGE}>
              <CashScreen />
            </RequirePermission>
          }
        />
        <Route
          path="settings/tax"
          element={
            <RequirePermission permission={Permission.RESTAURANT_CONFIGURE}>
              <TaxRatesScreen />
        <Route
          // The screen M12 never built. Its endpoint and its client hook both existed; nothing
          // rendered either, so a real restaurant could not create a shift and therefore could not
          // roster anybody. Beside the other things a restaurant sets up once.
          path="settings/shifts"
          element={
            <RequirePermission permission={Permission.SHIFT_MANAGE}>
              <ShiftsSetupScreen />
            </RequirePermission>
          }
        />
            </RequirePermission>
          }
        />
        {/* The design gallery (B11b, decision D4) is for developers, designers and reviewers,
            not for staff, so it exists only in a development build — both the route and the link
            in AppShell. Shipping the route to production without a link is precisely what
            `reachability.test.ts` was added to catch. */}
        {import.meta.env.DEV && <Route path="design" element={<DesignGalleryScreen />} />}
      </Route>

      {/* Anything unknown goes home rather than to a dead end; home is itself behind RequireAuth,
          so a signed-out visitor still lands on the login screen. */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
