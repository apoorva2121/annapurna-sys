import { type FormEvent, type ReactElement, useState } from 'react';
import { useParams } from 'react-router-dom';

import { Permission } from '@shared/permissions';
import {
  type Employee,
  useEmployee,
  useRoles,
  useSetActive,
  useSetRoles,
  useUpdateEmployee,
} from '@staff/api/staff';
import { useAuth } from '@staff/auth/AuthContext';
import { Button } from '@shared/ui/button';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { errorProps } from '@staff/components/errorProps';
import { QueryState } from '@staff/components/QueryState';
import { strings } from '@staff/strings';

export default function EmployeeScreen(): ReactElement {
  const { employeeId = '' } = useParams();
  const employee = useEmployee(employeeId);

  return (
    <QueryState
      isPending={employee.isPending}
      error={employee.error}
      pendingLabel={strings.employee.editTitle}
    >
      {employee.data !== undefined && <Loaded employee={employee.data} />}
    </QueryState>
  );
}

function Loaded({ employee }: { employee: Employee }): ReactElement {
  const { can } = useAuth();

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">{employee.full_name}</h1>
        <p className="font-mono text-sm text-muted-foreground">{employee.employee_code}</p>
        <p className={employee.is_active ? 'text-success' : 'text-critical'}>
          {employee.is_active ? strings.staff.active : strings.staff.inactive}
          {!employee.has_login && ` · ${strings.staff.noLogin}`}
        </p>
      </div>

      {can(Permission.EMPLOYEE_EDIT) && <Details employee={employee} />}
      {can(Permission.EMPLOYEE_ROLE_ASSIGN) && <Roles employee={employee} />}
      {can(Permission.EMPLOYEE_DEACTIVATE) && <Activation employee={employee} />}
    </div>
  );
}

function Details({ employee }: { employee: Employee }): ReactElement {
  const update = useUpdateEmployee(employee.id);
  const [fullName, setFullName] = useState(employee.full_name);
  const [phone, setPhone] = useState(employee.phone ?? '');

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    update.mutate({ full_name: fullName, phone: phone === '' ? null : phone });
  }

  return (
    <form onSubmit={onSubmit} className="flex max-w-md flex-col gap-4" noValidate>
      <h2 className="text-lg font-semibold">{strings.employee.editTitle}</h2>
      <Field
        label={strings.employee.fullName}
        value={fullName}
        onChange={(event) => {
          setFullName(event.target.value);
        }}
        required
      />
      <Field
        label={strings.employee.phone}
        value={phone}
        onChange={(event) => {
          setPhone(event.target.value);
        }}
        inputMode="tel"
      />

      {/* Pending, error and success are all rendered — none may be silent. */}
      {update.isError && <Notice tone="critical" {...errorProps(update.error)} />}
      {update.isSuccess && <Notice tone="success" title={strings.employee.saved} />}

      <Button type="submit" disabled={update.isPending} className="self-start">
        {update.isPending ? strings.employee.saving : strings.employee.save}
      </Button>
    </form>
  );
}

function Roles({ employee }: { employee: Employee }): ReactElement {
  const roles = useRoles();
  const setRoles = useSetRoles(employee.id);
  const [selected, setSelected] = useState<string[] | null>(null);

  // The catalogue carries ids; the employee carries codes. Resolve once the catalogue arrives, and
  // let a local edit take over from then on.
  const current =
    selected ??
    (roles.data ?? []).filter((role) => employee.roles.includes(role.code)).map((role) => role.id);

  function toggle(roleId: string): void {
    setSelected(
      current.includes(roleId) ? current.filter((id) => id !== roleId) : [...current, roleId],
    );
  }

  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold">{strings.employee.rolesTitle}</h2>
        <p className="text-sm text-muted-foreground">{strings.employee.rolesHint}</p>
      </div>

      <QueryState isPending={roles.isPending} error={roles.error} pendingLabel="Loading roles…">
        <ul className="space-y-1">
          {roles.data?.map((role) => (
            <li key={role.id}>
              <label className="flex min-h-target items-center gap-3">
                <input
                  type="checkbox"
                  className="size-5"
                  checked={current.includes(role.id)}
                  onChange={() => {
                    toggle(role.id);
                  }}
                />
                <span>{role.name}</span>
                <span className="text-sm text-muted-foreground">{role.description}</span>
              </label>
            </li>
          ))}
        </ul>
      </QueryState>

      {/* A refused grant is the seniority ladder talking, and its message explains itself. */}
      {setRoles.isError && <Notice tone="critical" {...errorProps(setRoles.error)} />}
      {setRoles.isSuccess && <Notice tone="success" title={strings.employee.rolesSaved} />}

      {/* Disabled until the catalogue is here, and this is a data-loss guard rather than polish.
          `current` is built by matching the employee's role codes against the catalogue's ids, so
          before the catalogue arrives it is the empty array — and the server reads `role_ids: []`
          as an authoritative full-set replacement. Tapping Save in that window deletes every
          assignment, revokes every session, and leaves the person unable to sign in at all, while
          reporting success.

          The condition is "is the catalogue in hand", not "is the query healthy": the catalogue is
          cached for an hour, so a failed *background* refetch leaves perfectly good data on screen
          and must not disable a button the user can correctly press. Unticking every box and
          saving remains a real operation — this guards the accident, not the intent. */}
      <Button
        disabled={setRoles.isPending || roles.data === undefined}
        onClick={() => {
          setRoles.mutate(current);
        }}
      >
        {setRoles.isPending ? strings.employee.rolesSaving : strings.employee.rolesSave}
      </Button>
    </section>
  );
}

function Activation({ employee }: { employee: Employee }): ReactElement {
  const setActive = useSetActive(employee.id);

  return (
    <section className="space-y-3">
      {employee.is_active && (
        <p className="text-sm text-muted-foreground">
          {strings.employee.confirmDeactivate(employee.full_name)}
        </p>
      )}
      {setActive.isError && <Notice tone="critical" {...errorProps(setActive.error)} />}
      <Button
        variant={employee.is_active ? 'destructive' : 'secondary'}
        disabled={setActive.isPending}
        onClick={() => {
          setActive.mutate(!employee.is_active);
        }}
      >
        {activationLabel(employee.is_active, setActive.isPending)}
      </Button>
    </section>
  );
}

function activationLabel(isActive: boolean, isPending: boolean): string {
  if (isActive) {
    return isPending ? strings.employee.deactivating : strings.employee.deactivate;
  }
  return isPending ? strings.employee.reactivating : strings.employee.reactivate;
}
