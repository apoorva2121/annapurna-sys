import { type FormEvent, type ReactElement, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { EmploymentType } from '@shared/enums';
import { useCreateEmployee } from '@staff/api/staff';
import { Button } from '@staff/components/Button';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';

function today(): string {
  // The business day is the restaurant's, not the browser's — but M01 has no business-day helper
  // yet and "joined on" is a date a human picks rather than a timestamp we derive. ISO, because
  // that is what the API takes.
  return new Date().toISOString().slice(0, 10);
}

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

  const [fullName, setFullName] = useState('');
  const [employeeCode, setEmployeeCode] = useState('');
  const [phone, setPhone] = useState('');
  const [joinedOn, setJoinedOn] = useState(today());
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
        initial_password: initialPassword === '' ? undefined : initialPassword,
      },
      {
        onSuccess: (employee) => {
          void navigate(`/staff/${employee.id}`);
        },
      },
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex max-w-md flex-col gap-4" noValidate>
      <h1 className="text-2xl font-semibold">{strings.employee.newTitle}</h1>

      <Field
        label={strings.employee.fullName}
        value={fullName}
        onChange={(event) => {
          setFullName(event.target.value);
        }}
        required
        autoFocus
      />
      <Field
        label={strings.employee.employeeCode}
        value={employeeCode}
        onChange={(event) => {
          setEmployeeCode(event.target.value);
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
        }}
        autoComplete="off"
      />
      {loginIdentifier !== '' && (
        <Field
          label={strings.employee.initialPassword}
          hint={strings.employee.passwordHint}
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
