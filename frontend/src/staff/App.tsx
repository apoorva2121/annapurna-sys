import type { ReactElement } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';

import { Permission } from '@shared/permissions';
import { RequireAuth, RequirePermission } from '@staff/auth/guards';
import { AppShell } from '@staff/components/AppShell';
import EmployeeScreen from '@staff/screens/EmployeeScreen';
import DishCostScreen from '@staff/screens/DishCostScreen';
import StockCountScreen from '@staff/screens/StockCountScreen';
import StockOnHandScreen from '@staff/screens/StockOnHandScreen';
import StockProduceScreen from '@staff/screens/StockProduceScreen';
import StockReceiveScreen from '@staff/screens/StockReceiveScreen';
import FloorPlanScreen from '@staff/screens/FloorPlanScreen';
import MenuItemScreen from '@staff/screens/MenuItemScreen';
import MenuScreen from '@staff/screens/MenuScreen';
import ModifierGroupsScreen from '@staff/screens/ModifierGroupsScreen';
import StockItemsScreen from '@staff/screens/StockItemsScreen';
import HomeScreen from '@staff/screens/HomeScreen';
import LoginScreen from '@staff/screens/LoginScreen';
import NewEmployeeScreen from '@staff/screens/NewEmployeeScreen';
import ProfileScreen from '@staff/screens/ProfileScreen';
import RecipeScreen from '@staff/screens/RecipeScreen';
import RestaurantSettingsScreen from '@staff/screens/RestaurantSettingsScreen';
import StaffListScreen from '@staff/screens/StaffListScreen';
import StationsScreen from '@staff/screens/StationsScreen';
import TaxRatesScreen from '@staff/screens/TaxRatesScreen';

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
        <Route
          path="settings/tax"
          element={
            <RequirePermission permission={Permission.RESTAURANT_CONFIGURE}>
              <TaxRatesScreen />
            </RequirePermission>
          }
        />
      </Route>

      {/* Anything unknown goes home rather than to a dead end; home is itself behind RequireAuth,
          so a signed-out visitor still lands on the login screen. */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
