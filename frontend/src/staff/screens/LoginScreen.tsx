import { type FormEvent, type ReactElement, useState } from 'react';
import { Navigate } from 'react-router-dom';

import { ApiClientError } from '@shared/api';
import { Button } from '@shared/ui/button';
import { useAuth } from '@staff/auth/AuthContext';
import { OrganizationChoiceNeeded, type OrganizationOption } from '@staff/auth/session';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { strings } from '@staff/strings';

// Where the last choice is kept on this device (backlog-issues B4, decision D1b): an organization id,
// never the login or anything that says who signed in.
const LAST_ORGANIZATION = 'restaurant-os.last-organization';

function remembered(): string | null {
  try {
    return localStorage.getItem(LAST_ORGANIZATION);
  } catch {
    return null;
  }
}

function remember(organizationId: string): void {
  try {
    localStorage.setItem(LAST_ORGANIZATION, organizationId);
  } catch {
    // A browser that refuses storage still signs in; it only forgets the choice.
  }
}

type Choice = { ticket: string; organizations: OrganizationOption[] };

function failure(caught: unknown): ApiClientError {
  return caught instanceof ApiClientError
    ? caught
    : new ApiClientError({ code: 'client.unexpected', message: strings.errors.title });
}

/**
 * The only screen an unauthenticated person can reach.
 *
 * Nothing is rendered before submit — no restaurant name, no logo fetched from an authenticated
 * endpoint, nothing that would confirm to an unauthenticated visitor that a particular account
 * exists (manual test A1).
 *
 * **Which hotel is asked after the password** (backlog-issues B4, decision D1a). Only when the
 * password opens accounts in more than one organization does the second step appear, with the last
 * choice on this device ticked (D1b). Asked before the password, it would tell anyone holding a phone
 * number which businesses that person works at.
 */
export default function LoginScreen(): ReactElement {
  const { session, signIn } = useAuth();
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<ApiClientError | null>(null);
  const [pending, setPending] = useState(false);
  const [choice, setChoice] = useState<Choice | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);

  if (session !== null && session !== undefined) {
    return <Navigate to="/" replace />;
  }

  async function attempt(organization?: { ticket: string; organizationId: string }): Promise<void> {
    setError(null);
    setPending(true);
    try {
      await signIn(identifier, password, organization);
      if (organization !== undefined) remember(organization.organizationId);
    } catch (caught) {
      if (caught instanceof OrganizationChoiceNeeded) {
        const last = remembered();
        setChoice({ ticket: caught.ticket, organizations: caught.organizations });
        setChosen(caught.organizations.some((each) => each.id === last) ? last : null);
        return;
      }
      // A used or expired pass starts over from the login; the server's sentence says why.
      if (organization !== undefined) setChoice(null);
      // The server's message is used verbatim. It is deliberately identical for an unknown
      // identifier and a wrong password, and rewording it here could reintroduce the enumeration
      // hole the backend went to some trouble to close (manual tests B1 and B2).
      setError(failure(caught));
    } finally {
      setPending(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (choice === null) {
      void attempt();
    } else if (chosen !== null) {
      void attempt({ ticket: choice.ticket, organizationId: chosen });
    }
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-sm flex-col justify-center p-6">
      <h1 className="text-2xl font-semibold">{strings.appName}</h1>
      <p className="mb-6 text-muted-foreground">
        {choice === null ? strings.login.title : strings.login.chooseTitle}
      </p>

      <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
        {choice === null ? (
          <Credentials
            identifier={identifier}
            password={password}
            onIdentifier={setIdentifier}
            onPassword={setPassword}
          />
        ) : (
          <Organizations choice={choice} chosen={chosen} onChoose={setChosen} />
        )}

        {error !== null && <SignInProblem error={error} />}

        <Actions
          choosing={choice !== null}
          pending={pending}
          canContinue={chosen !== null}
          onStartOver={() => {
            setChoice(null);
            setChosen(null);
          }}
        />
      </form>
    </main>
  );
}

function Credentials({
  identifier,
  password,
  onIdentifier,
  onPassword,
}: {
  identifier: string;
  password: string;
  onIdentifier: (value: string) => void;
  onPassword: (value: string) => void;
}): ReactElement {
  return (
    <>
      <Field
        label={strings.login.identifierLabel}
        hint={strings.login.identifierHint}
        value={identifier}
        onChange={(event) => {
          onIdentifier(event.target.value);
        }}
        autoComplete="username"
        // Not type="email": most staff sign in with a phone number, and type="email" would make a
        // browser reject a valid identifier before it ever reached the server.
        inputMode="text"
        required
        autoFocus
      />
      <Field
        label={strings.login.passwordLabel}
        type="password"
        value={password}
        onChange={(event) => {
          onPassword(event.target.value);
        }}
        autoComplete="current-password"
        required
      />
    </>
  );
}

/** Which hotel: only the organizations the password opened, with last time's choice ticked. */
function Organizations({
  choice,
  chosen,
  onChoose,
}: {
  choice: Choice;
  chosen: string | null;
  onChoose: (organizationId: string) => void;
}): ReactElement {
  return (
    <fieldset className="flex flex-col gap-1">
      <legend className="mb-2 text-sm text-muted-foreground">{strings.login.chooseHint}</legend>
      {choice.organizations.map((organization) => (
        <label key={organization.id} className="flex min-h-target items-center gap-3">
          <input
            type="radio"
            name="organization"
            value={organization.id}
            checked={chosen === organization.id}
            onChange={() => {
              onChoose(organization.id);
            }}
          />
          {organization.name}
        </label>
      ))}
    </fieldset>
  );
}

function SignInProblem({ error }: { error: ApiClientError }): ReactElement {
  return (
    <Notice
      tone="critical"
      title={error.code === 'network.unreachable' ? strings.login.offline : error.message}
      code={error.code}
    />
  );
}

function Actions({
  choosing,
  pending,
  canContinue,
  onStartOver,
}: {
  choosing: boolean;
  pending: boolean;
  canContinue: boolean;
  onStartOver: () => void;
}): ReactElement {
  if (!choosing) {
    return (
      <Button type="submit" disabled={pending}>
        {pending ? strings.login.submitting : strings.login.submit}
      </Button>
    );
  }
  return (
    <>
      <Button type="submit" disabled={pending || !canContinue}>
        {pending ? strings.login.submitting : strings.login.continue}
      </Button>
      <Button type="button" variant="ghost" onClick={onStartOver}>
        {strings.login.startOver}
      </Button>
    </>
  );
}
