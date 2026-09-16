import { type FormEvent, type ReactElement, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { businessToday } from '@shared/businessDay';
import { EmploymentType } from '@shared/enums';
import { useCreateEmployee, useNextEmployeeCode } from '@staff/api/staff';
import { useAuth } from '@staff/auth/AuthContext';
import { Button } from '@shared/ui/button';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';

/**
 * Add an employee, with or without a login.
 *
 * The login half is optional and says so. ADR 0007 makes an employee without credentials a normal
 * shape — a cleaner referenced by shifts and wastage events who never signs in — and a form that
 * demanded a password would quietly make that impossible from the UI.
 */
export default function NewEmployeeScreen(): ReactElement {
  const navigate = useNavigate();
  const create = useCreateEmployee();
  const { session } = useAuth();

  const [fullName, setFullName] = useState('');
  const nextCode = useNextEmployeeCode();
  // Null until somebody types: the next free code is filled in, and theirs wins once they do (D19).
  const [typedCode, setTypedCode] = useState<string | null>(null);
  const employeeCode = typedCode ?? nextCode.data?.employee_code ?? '';
  const [phone, setPhone] = useState('');
  // The restaurant's today, not the browser's. Between local midnight and 05:30 IST those are
  // different days, and the browser's answer is yesterday — a wrong joining date recorded by
  // someone who accepted a default that looked entirely reasonable. `session` is never null here
  // (RequireAuth guards the route), but the fallback keeps the field usable rather than crashing
  // the screen if that ever stops being true.
  const [joinedOn, setJoinedOn] = useState(() =>
    session === null || session === undefined
      ? new Date().toISOString().slice(0, 10)
      : businessToday(session.restaurant.timezone, session.restaurant.business_day_start),
  );
  const [loginIdentifier, setLoginIdentifier] = useState('');
  const [initialPassword, setInitialPassword] = useState('');

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    create.mutate(
      {
        full_name: fullName,
        employee_code: employeeCode,
        joined_on: joinedOn,
        employment_type: EmploymentType.FULL_TIME,
        phone: phone === '' ? undefined : phone,
        login_identifier: loginIdentifier === '' ? undefined : loginIdentifier,
        // A password belongs to a login: none is sent without one (defect sheet row 8).
        initial_password:
          loginIdentifier === '' || initialPassword === '' ? undefined : initialPassword,
      },
      {
        onSuccess: (employee) => {
          // To their page to give them a role, then Finish (decision D14).
          void navigate(`/staff/${employee.id}?added=1`);
        },
      },
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex max-w-md flex-col gap-4" noValidate>
      <h1 className="text-2xl font-semibold">{strings.employee.newTitle}</h1>

      <Field
        label={strings.employee.fullName}
        hint={strings.employee.fullNameHint}
        value={fullName}
        onChange={(event) => {
          setFullName(event.target.value);
        }}
        required
        autoFocus
      />
      <Field
        label={strings.employee.employeeCode}
        hint={strings.employee.employeeCodeHint}
        value={employeeCode}
        onChange={(event) => {
          setTypedCode(event.target.value);
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
      <Field
        label={strings.employee.joinedOn}
        type="date"
        value={joinedOn}
        onChange={(event) => {
          setJoinedOn(event.target.value);
        }}
        required
      />
      <Field
        label={strings.employee.loginIdentifier}
        hint={strings.employee.loginHint}
        value={loginIdentifier}
        onChange={(event) => {
          setLoginIdentifier(event.target.value);
          if (event.target.value === '') {
            setInitialPassword('');
          }
        }}
        autoComplete="off"
      />
      {loginIdentifier !== '' && (
        <Field
          label={strings.employee.initialPassword}
          hint={strings.employee.initialPasswordHint}
          type="password"
          value={initialPassword}
          onChange={(event) => {
            setInitialPassword(event.target.value);
          }}
          autoComplete="new-password"
          minLength={10}
        />
      )}

      {/* The server owns validation messages — a duplicate phone number or employee code comes
          back as a coded conflict with a sentence already written for a human. */}
      {create.isError && <Notice tone="critical" {...errorProps(create.error)} />}

      <Button type="submit" disabled={create.isPending} className="self-start">
        {create.isPending ? strings.employee.creating : strings.employee.create}
      </Button>
    </form>
  );
}
