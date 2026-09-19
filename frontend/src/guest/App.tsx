import { type ReactElement, useEffect, useState } from 'react';

import { type GuestSession, GuestApiError, openSession, setGuestToken } from './api';
import { BillScreen } from './screens/BillScreen';
import { FeedbackScreen } from './screens/FeedbackScreen';
import { MenuScreen } from './screens/MenuScreen';
import { strings } from './strings';

/**
 * The guest app. Three screens, no sign-in, and a QR code for authentication.
 *
 * **Guest surface** (`docs/ui/conventions.md`): the only surface on a device we do not own, a
 * network we do not control, for a person who has never seen this product and will use it once.
 * Nothing here is learnable — it works the first time or it does not work.
 *
 * **The whole session is the URL.** `?t=<slug>` is the sticker on the table and `?b=<token>` is the
 * QR on the bill. The token is exchanged once and kept in memory only: nothing is written to
 * storage, because a phone that opens this once should carry nothing away afterwards.
 *
 * **Which screens exist depends on which code was scanned**, which is decision 1 of
 * `docs/modules/M10-customers-spec.md`: the table sticker opens the menu and nothing else, and the
 * bill QR opens that bill and its three questions. A photographed sticker is worth the menu, which
 * is on the wall anyway.
 */
export default function App(): ReactElement {
  const [session, setSession] = useState<GuestSession | null>(null);
  const [error, setError] = useState<GuestApiError | null>(null);
  const [tab, setTab] = useState<'menu' | 'bill' | 'feedback'>('menu');

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const tableSlug = params.get('t');
    const orderToken = params.get('b');
    const code = tableSlug === null ? { order_token: orderToken ?? '' } : { table_slug: tableSlug };

    openSession(code)
      .then((opened) => {
        setGuestToken(opened.token);
        setSession(opened);
        setTab(opened.scope === 'order' ? 'bill' : 'menu');
      })
      .catch((reason: unknown) => {
        setError(
          reason instanceof GuestApiError
            ? reason
            : new GuestApiError(0, {
                code: 'guest.unreachable',
                message: strings.scan.offlineBody,
              }),
        );
      });
  }, []);

  if (error !== null) {
    return (
      <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-4 p-6">
        <h1 className="text-2xl font-semibold">
          {error.status === 401 ? strings.scan.refusedTitle : strings.scan.offlineTitle}
        </h1>
        <p className="text-base text-muted-foreground">{error.message}</p>
      </main>
    );
  }

  if (session === null) {
    return (
      <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center p-6">
        <p className="text-base text-muted-foreground">{strings.scan.loading}</p>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col gap-4 p-4">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">{session.restaurant_name}</h1>
      </header>

      {session.scope === 'order' ? (
        <nav className="flex gap-2" aria-label={strings.bill.title}>
          <TabButton current={tab} value="bill" onSelect={setTab}>
            {strings.bill.title}
          </TabButton>
          <TabButton current={tab} value="menu" onSelect={setTab}>
            {strings.menu.title}
          </TabButton>
          <TabButton current={tab} value="feedback" onSelect={setTab}>
            {strings.feedback.title}
          </TabButton>
        </nav>
      ) : null}

      {tab === 'menu' ? <MenuScreen /> : null}
      {tab === 'bill' ? <BillScreen /> : null}
      {tab === 'feedback' ? <FeedbackScreen /> : null}
    </main>
  );
}

function TabButton({
  current,
  value,
  onSelect,
  children,
}: {
  current: string;
  value: 'menu' | 'bill' | 'feedback';
  onSelect: (value: 'menu' | 'bill' | 'feedback') => void;
  children: string;
}): ReactElement {
  const selected = current === value;
  return (
    <button
      type="button"
      // Selected is a ring, never a thicker border: a control that changes size under a thumb
      // moves the one beside it, and the next tap lands on the wrong thing.
      className={`min-h-target flex-1 rounded-md px-3 text-base ${
        selected ? 'bg-brand-soft text-brand ring-2 ring-brand' : 'bg-muted text-foreground'
      }`}
      aria-current={selected ? 'page' : undefined}
      onClick={() => {
        onSelect(value);
      }}
    >
      {children}
    </button>
  );
}
