import type { ReactElement } from 'react';
import { Link } from 'react-router-dom';

import { cn } from '@shared/cn';
import { Button } from '@shared/ui/button';
import { QueryState } from '@staff/components/QueryState';
import { strings } from '@staff/strings';
import { type Notice, useMarkNotice, useNotifications } from '@staff/api/audit';

/**
 * Everything true right now that this person can do something about.
 *
 * **Nothing here was written by a job, because there is no job.** Every line is a live query — the
 * stock is negative *now*, the task is overdue *now* — so a warning disappears the moment somebody
 * records the delivery. The alternative this product deliberately avoided is a table filled by a
 * scheduler that is not deployed, which produces an empty centre that looks exactly like nothing
 * being wrong.
 *
 * **A person sees only what they can act on** (`docs/product/vision.md` §25). The filtering happens
 * on the server, per condition, from the permissions somebody holds — so a waiter's centre has
 * their own overdue task in it and no food-cost figure, and it stays that way when a role changes.
 *
 * **Colour never carries the meaning alone** (`docs/ui/conventions.md` rule 5). Every row says what
 * kind of thing it is in words; the tint is the second signal, not the only one.
 */
export default function NotificationsScreen(): ReactElement {
  const notices = useNotifications();

  return (
    <div className="flex flex-col gap-page">
      <h1 className="text-2xl font-semibold">{strings.notifications.title}</h1>
      <QueryState
        isPending={notices.isPending}
        error={notices.error}
        pendingLabel={strings.notifications.loading}
      >
        {notices.data === undefined ? null : notices.data.items.length === 0 ? (
          // An empty centre is the right answer, and the screen says so in words rather than
          // leaving somebody to wonder whether it is broken.
          <div className="flex flex-col gap-2">
            <p className="text-lg">{strings.notifications.allClear}</p>
            <p className="text-sm text-muted-foreground">{strings.notifications.allClearHint}</p>
          </div>
        ) : (
          <ul className="flex flex-col gap-3">
            {notices.data.items.map((notice) => (
              <Row key={notice.key} notice={notice} />
            ))}
          </ul>
        )}
      </QueryState>
    </div>
  );
}

// The locked six (`docs/ui/conventions.md`). `critical` is spent on exactly two conditions —
// stock that has gone negative, and a critical complaint — because a scale where everything is
// red is a scale nobody reads.
const TINTS: Record<string, string> = {
  // **A severity stripe on a normal surface, not a tinted card.** The `-soft` fills are locked
  // (`tokens.css`) so no theme may repaint them — which is right, because a festive theme that
  // made red decorative would break the only promise the kitchen display makes. But locked means
  // *always near-white*, and the Dark theme's `foreground` is near-white too: this card used to
  // set `bg-critical-soft` and no ink, so its text inherited the page foreground and rendered at
  // a contrast ratio of 1.04 against its own background. Identical colours are 1.0. It was
  // invisible, and only in the dark.
  //
  // Design-system rule 11 is that a soft fill always carries its own strong ink. That pairing is
  // right for a *badge* — a word and a colour — and wrong for a whole card, whose detail text
  // would then be a paragraph of red. So the severity moves to a stripe and a badge, and the card
  // keeps a normal surface where `foreground` is guaranteed readable in every theme.
  critical: 'border-l-4 border-l-critical',
  warning: 'border-l-4 border-l-caution',
  caution: 'border-l-4 border-l-caution',
  info: 'border-border',
};

// Rule 11, on the one element it is meant for: soft fill, strong ink, and a word. Both halves of
// each pair are locked tokens, so this contrast holds in every theme — which is exactly what the
// card's inherited `foreground` could not promise.
const BADGES: Record<string, string> = {
  critical: 'bg-critical-soft text-critical',
  warning: 'bg-caution-soft text-caution',
  caution: 'bg-caution-soft text-caution',
  info: 'bg-neutral-soft text-neutral',
};

// Where each kind of condition is dealt with. A notification that cannot be acted on from itself
// is a notification somebody has to go and find the screen for.
const DESTINATIONS: Record<string, string> = {
  'stock.negative': '/stock/on-hand',
  'stock.expiring': '/stock/on-hand',
  'stock.count_awaiting': '/stock/count',
  'complaint.open': '/complaints',
  'task.overdue': '/tasks',
  'cash.variance': '/cash',
};

function Row({ notice }: { notice: Notice }): ReactElement {
  const mark = useMarkNotice();
  const destination = DESTINATIONS[notice.kind];

  return (
    <li className={cn('flex flex-col gap-2 rounded border p-4', TINTS[notice.severity])}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <span className="font-semibold">{notice.subject}</span>
        <span className="flex flex-wrap items-baseline gap-2">
          {/* Severity as a word and a colour, never a colour alone. */}
          <span
            className={cn(
              'rounded-full px-2 py-0.5 text-xs font-medium',
              BADGES[notice.severity] ?? BADGES.info,
            )}
          >
            {strings.notifications.severity[notice.severity] ?? notice.severity}
          </span>
          <span className="text-xs uppercase tracking-wide text-muted-foreground">
            {strings.notifications.kind[notice.kind] ?? notice.kind}
          </span>
        </span>
      </div>
      <p className="text-sm">{notice.detail}</p>
      <div className="flex flex-wrap items-center gap-4">
        {destination !== undefined && (
          <Link className="min-h-target underline" to={destination}>
            {strings.notifications.open}
          </Link>
        )}
        {!notice.read && (
          <Button
            variant="secondary"
            disabled={mark.isPending}
            onClick={() => {
              mark.mutate({ key: notice.key });
            }}
          >
            {strings.notifications.markRead}
          </Button>
        )}
        <Button
          variant="ghost"
          disabled={mark.isPending}
          onClick={() => {
            mark.mutate({ key: notice.key, dismissed: true });
          }}
        >
          {strings.notifications.dismiss}
        </Button>
      </div>
      {/* Said out loud, because "dismiss" on a condition that is still true would otherwise read
          as "fix" — and the difference between the two is the whole point of deriving them. */}
      <p className="text-xs text-muted-foreground">{strings.notifications.dismissHint}</p>
    </li>
  );
}
