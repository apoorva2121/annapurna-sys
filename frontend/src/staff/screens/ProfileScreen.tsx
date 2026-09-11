import { useMutation } from '@tanstack/react-query';
import { type FormEvent, type ReactElement, useState } from 'react';

import { useAuth } from '@staff/auth/AuthContext';
import { changePassword } from '@staff/auth/session';
import { Button } from '@shared/ui/button';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';

/**
 * Own profile and password.
 *
 * The permission list is shown in full rather than summarised as a role name. That is the same
 * reasoning as `GET /auth/me` existing at all (ADR 0007): the role name is a label, the
 * permissions are the truth, and a person asking "why can't I see X" needs the truth.
 */
export default function ProfileScreen(): ReactElement {
  const { session } = useAuth();
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');

  const change = useMutation({
    mutationFn: () => changePassword(currentPassword, newPassword),
    onSuccess: () => {
      setCurrentPassword('');
      setNewPassword('');
    },
  });

  if (session === null || session === undefined) {
    return <></>;
  }

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    change.mutate();
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold">{strings.profile.title}</h1>
        <dl className="mt-3 grid max-w-md grid-cols-[auto_1fr] gap-x-6 gap-y-1">
          <dt className="text-muted-foreground">{strings.profile.name}</dt>
          <dd>{session.fullName}</dd>
          <dt className="text-muted-foreground">{strings.profile.code}</dt>
          <dd className="font-mono">{session.employeeCode}</dd>
          <dt className="text-muted-foreground">{strings.profile.restaurant}</dt>
          <dd>{session.restaurant.name}</dd>
          <dt className="text-muted-foreground">{strings.profile.roles}</dt>
          <dd>{session.roles.join(', ')}</dd>
        </dl>
      </div>

      <section>
        <h2 className="text-lg font-semibold">{strings.profile.permissions}</h2>
        <ul className="mt-2 font-mono text-sm text-muted-foreground">
          {[...session.permissions]
            .sort((a, b) => a.localeCompare(b))
            .map((permission) => (
              <li key={permission}>{permission}</li>
            ))}
        </ul>
      </section>

      <form onSubmit={onSubmit} className="flex max-w-md flex-col gap-4" noValidate>
        <h2 className="text-lg font-semibold">{strings.profile.changePassword}</h2>
        {/* Someone else set this password and still knows it. Said plainly rather than nudged,
            because the person needs to understand that until they act, anything done with their
            account is attributed to them. */}
        {session.passwordChangeRequired && (
          <Notice tone="critical" title={strings.profile.mustChange}>
            {strings.profile.mustChangeWhy}
          </Notice>
        )}
        <Field
          label={strings.profile.currentPassword}
          type="password"
          value={currentPassword}
          onChange={(event) => {
            setCurrentPassword(event.target.value);
          }}
          autoComplete="current-password"
          required
        />
        <Field
          label={strings.profile.newPassword}
          hint={strings.employee.passwordHint}
          type="password"
          value={newPassword}
          onChange={(event) => {
            setNewPassword(event.target.value);
          }}
          autoComplete="new-password"
          minLength={10}
          required
        />

        {change.isError && <Notice tone="critical" {...errorProps(change.error)} />}
        {change.isSuccess && <Notice tone="success" title={strings.profile.changed} />}

        <Button type="submit" disabled={change.isPending} className="self-start">
          {change.isPending ? strings.profile.submitting : strings.profile.submit}
        </Button>
      </form>
    </div>
  );
}
