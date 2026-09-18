import { type ReactElement, useState } from 'react';
import { Link } from 'react-router-dom';

import { Button } from '@shared/ui/button';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import { useEmployees } from '@staff/api/staff';
import {
  type InboxEntry,
  useCommunicationStream,
  useInbox,
  useStartConversation,
} from '@staff/api/communication';

/**
 * Every conversation this person is in, newest first.
 *
 * **Manager and waiter both.** It is the one screen in the product everybody opens, including the
 * cleaner — who until M11 held no permission at all.
 *
 * **Unread is a number from the server, not a number this screen keeps.** The stream marks the
 * inbox stale and TanStack refetches it; nothing here counts anything. A count maintained in a
 * browser is a second source of truth that disagrees with the server the first time an event is
 * dropped, and the one it disagrees with is the person's.
 *
 * **Urgent is a word and a position, never a colour alone** (`docs/ui/conventions.md`): the badge
 * says *Urgent*, and the row it is on sorts to the top on the server.
 *
 * **The connection state is shown when it is not live.** A messages screen that has quietly
 * stopped updating is worse than one that says so — M08's rule, and it applies here for the same
 * reason.
 */
export default function InboxScreen(): ReactElement {
  const [unreadOnly, setUnreadOnly] = useState(false);
  const inbox = useInbox(unreadOnly);
  const stream = useCommunicationStream();

  return (
    <div className="flex flex-col gap-page p-page">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="text-xl font-semibold md:text-2xl">{strings.messages.title}</h1>
        {stream === 'live' ? null : (
          <span className="rounded-full bg-caution-soft px-2 py-0.5 text-xs font-medium text-caution">
            {strings.messages.reconnecting}
          </span>
        )}
      </div>

      <div className="flex flex-wrap gap-2">
        <Button
          variant={unreadOnly ? 'secondary' : 'primary'}
          onClick={() => { setUnreadOnly(false); }}
        >
          {strings.messages.allFilter}
        </Button>
        <Button
          variant={unreadOnly ? 'primary' : 'secondary'}
          onClick={() => { setUnreadOnly(true); }}
        >
          {strings.messages.unreadFilter}
        </Button>
      </div>

      <StartConversation />

      <QueryState
        isPending={inbox.isPending}
        error={inbox.error}
        pendingLabel={strings.messages.loading}
      >
        {inbox.data === undefined ? null : inbox.data.items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{strings.messages.empty}</p>
        ) : (
          <ul className="flex flex-col">
            {inbox.data.items.map((entry) => (
              <Row key={entry.id} entry={entry} />
            ))}
          </ul>
        )}
      </QueryState>
    </div>
  );
}

function Row({ entry }: { entry: InboxEntry }): ReactElement {
  return (
    <li className="border-b border-border">
      <Link
        to={`/messages/${entry.id}`}
        className="flex min-h-target items-center gap-2 py-3"
      >
        <span className="flex-1 font-medium">
          {entry.title ?? strings.messages.noTitle}
        </span>
        {entry.has_urgent_unread ? (
          <span className="rounded-full bg-critical-soft px-2 py-0.5 text-xs font-medium text-critical">
            {strings.messages.urgent}
          </span>
        ) : null}
        {entry.unread === 0 ? null : (
          <span className="rounded-full bg-info-soft px-2 py-0.5 text-xs font-medium text-info tabular-nums">
            {strings.messages.unread(entry.unread)}
          </span>
        )}
        {entry.is_muted ? (
          <span className="text-xs text-muted-foreground">{strings.messages.muted}</span>
        ) : null}
      </Link>
    </li>
  );
}

/**
 * Start a group with the people you need.
 *
 * A direct conversation that already exists comes back as the one that exists rather than a second
 * one, so this never produces the seven-threads-to-one-person inbox that makes a messaging feature
 * look broken.
 */
function StartConversation(): ReactElement {
  const [open, setOpen] = useState(false);
  const [title, setTitle] = useState('');
  const [chosen, setChosen] = useState<string[]>([]);
  // Active staff only: a conversation is started with somebody who still works here.
  const people = useEmployees(false);
  const start = useStartConversation();

  if (!open) {
    return (
      <Button variant="secondary" onClick={() => { setOpen(true); }}>
        {strings.messages.startTitle}
      </Button>
    );
  }

  return (
    <section className="flex flex-col gap-2 border-b border-border pb-4">
      <h2 className="text-lg font-medium">{strings.messages.startTitle}</h2>

      <label className="text-sm font-medium" htmlFor="conversation-title">
        {strings.messages.startGroupName}
      </label>
      <input
        id="conversation-title"
        className="min-h-target rounded-md border border-border bg-background px-3 text-base"
        value={title}
        onChange={(event) => { setTitle(event.target.value); }}
        placeholder={strings.messages.startGroupNamePlaceholder}
      />

      <p className="text-sm font-medium">{strings.messages.startWith}</p>
      <QueryState isPending={people.isPending} error={people.error} pendingLabel={strings.messages.loading}>
        <div className="flex flex-wrap gap-2">
          {(people.data?.pages ?? []).flatMap((page) => page.items).map((person) => (
            <Button
              key={person.id}
              variant={chosen.includes(person.id) ? 'primary' : 'secondary'}
              onClick={() => {
                setChosen((current) =>
                  current.includes(person.id)
                    ? current.filter((id) => id !== person.id)
                    : [...current, person.id],
                );
              }}
            >
              {person.full_name}
            </Button>
          ))}
        </div>
      </QueryState>

      <Button
        disabled={chosen.length === 0 || start.isPending}
        onClick={() => {
          start.mutate(
            {
              type: 'group',
              ...(title.trim() === '' ? {} : { title }),
              participantIds: chosen,
            },
            {
              onSuccess: () => {
                setOpen(false);
                setTitle('');
                setChosen([]);
              },
            },
          );
        }}
      >
        {start.isPending ? strings.messages.starting : strings.messages.start}
      </Button>

      {start.error === null ? null : <Notice tone="critical" {...errorProps(start.error)} />}
    </section>
  );
}
