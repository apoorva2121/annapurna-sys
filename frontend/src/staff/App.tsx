import type { ReactElement } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';

import { Permission } from '@shared/permissions';
import { RequireAuth, RequirePermission } from '@staff/auth/guards';
import { AppShell } from '@staff/components/AppShell';
import EmployeeScreen from '@staff/screens/EmployeeScreen';
import HomeScreen from '@staff/screens/HomeScreen';
import LoginScreen from '@staff/screens/LoginScreen';
import NewEmployeeScreen from '@staff/screens/NewEmployeeScreen';
import ProfileScreen from '@staff/screens/ProfileScreen';
import StaffListScreen from '@staff/screens/StaffListScreen';

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
      </Route>

      {/* Anything unknown goes home rather than to a dead end; home is itself behind RequireAuth,
          so a signed-out visitor still lands on the login screen. */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
