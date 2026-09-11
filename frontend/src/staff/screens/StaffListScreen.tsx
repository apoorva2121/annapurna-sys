import { type ReactElement, useState } from 'react';
import { Link } from 'react-router-dom';

import { Permission } from '@shared/permissions';
import { useEmployees } from '@staff/api/staff';
import { useAuth } from '@staff/auth/AuthContext';
import { Button } from '@shared/ui/button';
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
  // Pages are an artefact of the transport, not something the list should think about.
  const people = employees.data?.pages.flatMap((page) => page.items) ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">{strings.staff.title}</h1>
        {can(Permission.EMPLOYEE_CREATE) && (
          // `asChild` renders the Link with the button's appearance. It navigates, so it has to
          // stay a link — openable in a new tab, and not a <Link> illegally nested in a <button>.
          <Button asChild>
            <Link to="/staff/new">{strings.staff.add}</Link>
          </Button>
        )}
      </div>

      <label className="flex min-h-target items-center gap-2">
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
        {people.length === 0 ? (
          <p className="rounded border border-border p-4 text-muted-foreground">
            {includeInactive ? strings.staff.emptyInactive : strings.staff.empty}
          </p>
        ) : (
          <ul className="divide-y divide-border rounded border border-border">
            {people.map((employee) => (
              <li key={employee.id}>
                <Link
                  to={`/staff/${employee.id}`}
                  className="flex min-h-target flex-wrap items-center gap-x-4 gap-y-1 p-3 hover:bg-muted"
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

        {/* The endpoint pages at 50. Without this the rest of a large roster would simply not be
            on screen, with nothing to say so. */}
        {employees.hasNextPage && (
          <Button
            variant="secondary"
            disabled={employees.isFetchingNextPage}
            onClick={() => {
              void employees.fetchNextPage();
            }}
          >
            {employees.isFetchingNextPage ? strings.staff.showingMore : strings.staff.showMore}
          </Button>
        )}
      </QueryState>
    </div>
  );
}
