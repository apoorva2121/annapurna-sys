import { type ReactElement, useState } from 'react';
import { Link } from 'react-router-dom';

import { Permission } from '@shared/permissions';
import { useEmployees } from '@staff/api/staff';
import { useAuth } from '@staff/auth/AuthContext';
import { QueryState } from '@staff/components/QueryState';
import { strings } from '@staff/strings';

/**
 * The staff list. Manager/owner surface, so a table rather than cards
 * (docs/ui/conventions.md) — but it collapses to a stacked layout below `sm`, because a manager
 * checks the roster on a phone as often as at a desk.
 *
 * Deactivated people stay in the list behind a toggle rather than disappearing: ADR 0008 keeps the
 * row forever, and a manager who deactivates someone by mistake needs to find them again.
 */
export default function StaffListScreen(): ReactElement {
  const [includeInactive, setIncludeInactive] = useState(false);
  const { can } = useAuth();
  const employees = useEmployees(includeInactive);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">{strings.staff.title}</h1>
        {can(Permission.EMPLOYEE_CREATE) && (
          // A link, not a button wrapping a link: it navigates, so it must be openable in a new
          // tab and reachable the way every other link is. Styled to match Button's target size.
          <Link
            to="/staff/new"
            className="inline-flex min-h-12 items-center justify-center rounded bg-foreground px-4 font-medium text-background"
          >
            {strings.staff.add}
          </Link>
        )}
      </div>

      <label className="flex min-h-12 items-center gap-2">
        <input
          type="checkbox"
          className="size-5"
          checked={includeInactive}
          onChange={(event) => {
            setIncludeInactive(event.target.checked);
          }}
        />
        <span>{strings.staff.showInactive}</span>
      </label>

      <QueryState
        isPending={employees.isPending}
        error={employees.error}
        pendingLabel={strings.staff.loading}
      >
        {employees.data !== undefined && employees.data.items.length === 0 ? (
          <p className="rounded border border-border p-4 text-muted-foreground">
            {includeInactive ? strings.staff.emptyInactive : strings.staff.empty}
          </p>
        ) : (
          <ul className="divide-y divide-border rounded border border-border">
            {employees.data?.items.map((employee) => (
              <li key={employee.id}>
                <Link
                  to={`/staff/${employee.id}`}
                  className="flex min-h-12 flex-wrap items-center gap-x-4 gap-y-1 p-3 hover:bg-muted"
                >
                  <span className="font-medium">{employee.full_name}</span>
                  <span className="font-mono text-sm text-muted-foreground">
                    {employee.employee_code}
                  </span>
                  <span className="text-sm text-muted-foreground">
                    {employee.roles.length === 0
                      ? strings.staff.noRoles
                      : employee.roles.join(', ')}
                  </span>
                  {!employee.has_login && (
                    <span className="text-sm text-muted-foreground">{strings.staff.noLogin}</span>
                  )}
                  {/* Status is a word, never a colour alone (docs/ui/conventions.md). */}
                  <span
                    className={
                      employee.is_active
                        ? 'ml-auto text-sm text-success'
                        : 'ml-auto text-sm text-critical'
                    }
                  >
                    {employee.is_active ? strings.staff.active : strings.staff.inactive}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </QueryState>
    </div>
  );
}
