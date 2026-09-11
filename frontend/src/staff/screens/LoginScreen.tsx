import { type FormEvent, type ReactElement, useState } from 'react';
import { Navigate } from 'react-router-dom';

import { ApiClientError } from '@shared/api';
import { useAuth } from '@staff/auth/AuthContext';
import { Button } from '@staff/components/Button';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { strings } from '@staff/strings';

/**
 * The only screen an unauthenticated person can reach.
 *
 * Nothing is rendered before submit — no restaurant name, no logo fetched from an authenticated
 * endpoint, nothing that would confirm to an unauthenticated visitor that a particular account
 * exists (manual test A1).
 */
export default function LoginScreen(): ReactElement {
  const { session, signIn } = useAuth();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<ApiClientError | null>(null);
  const [pending, setPending] = useState(false);

  if (session !== null && session !== undefined) {
    return <Navigate to="/" replace />;
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setError(null);
    setPending(true);
    try {
      await signIn(identifier, password);
    } catch (caught) {
      // The server's message is used verbatim. It is deliberately identical for an unknown
      // identifier and a wrong password, and rewording it here could reintroduce the enumeration
      // hole the backend went to some trouble to close (manual tests B1 and B2).
      setError(
        caught instanceof ApiClientError
          ? caught
          : new ApiClientError({ code: 'client.unexpected', message: strings.errors.title }),
      );
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center p-6">
      <h1 className="text-2xl font-semibold">{strings.appName}</h1>
      <p className="mb-6 text-muted-foreground">{strings.login.title}</p>

      <form
        onSubmit={(event) => {
          void onSubmit(event);
        }}
        className="flex flex-col gap-4"
        noValidate
      >
        <Field
          label={strings.login.identifierLabel}
          hint={strings.login.identifierHint}
          value={identifier}
          onChange={(event) => {
            setIdentifier(event.target.value);
          }}
          autoComplete="username"
          // Not type="email": most staff sign in with a phone number, and type="email" would make
          // a browser reject a valid identifier before it ever reached the server.
          inputMode="text"
          required
          autoFocus
        />
        <Field
          label={strings.login.passwordLabel}
          type="password"
          value={password}
          onChange={(event) => {
            setPassword(event.target.value);
          }}
          autoComplete="current-password"
          required
        />

        {error !== null && (
          <Notice
            tone="critical"
            title={error.code === 'network.unreachable' ? strings.login.offline : error.message}
            code={error.code}
          />
        )}

        <Button type="submit" disabled={pending}>
          {pending ? strings.login.submitting : strings.login.submit}
        </Button>
      </form>
    </main>
  );
}
