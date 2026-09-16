import { type ReactElement, useState } from 'react';

import { QueryState } from '@staff/components/QueryState';
import { strings } from '@staff/strings';
import { type Feedback, useFeedbackDay } from '@staff/api/customers';

/**
 * What diners said, for one **business day**.
 *
 * Not a calendar day: a table that ordered at 1am belongs to the night it ate, and
 * `restaurant.business_day_start` is what says so (CLAUDE.md invariant 4). The label says
 * "Business day" for exactly that reason.
 *
 * **Manager surface.** A waiter holds `feedback.view` too, deliberately — a rating is about a table
 * they served, and somebody who cannot see how their service landed cannot improve it. What nobody
 * can do is submit feedback on their own tables: that needs the token printed on the guest's bill.
 *
 * **`source` is on every row**, because a `staff`-entered rating and a guest's own are different
 * evidence and M17 pays attention to these numbers. A manager writing down a phone call is
 * legitimate; hiding that it happened is not.
 *
 * **The empty state says most tables never rate a meal**, which is true and is the thing somebody
 * reading a blank screen needs to know before they conclude the QR code is broken.
 */
export default function FeedbackScreen(): ReactElement {
  const [day, setDay] = useState(() => new Date().toISOString().slice(0, 10));
  const feedback = useFeedbackDay(day);

  return (
    <div className="flex flex-col gap-page p-page">
      <h1 className="text-2xl font-semibold">{strings.feedback.title}</h1>

      <label className="flex flex-col gap-1 text-sm font-medium">
        {strings.feedback.dayLabel}
        <input
          type="date"
          className="min-h-target rounded-md border border-border bg-background px-3 text-base"
          value={day}
          onChange={(event) => { setDay(event.target.value); }}
        />
      </label>

      <QueryState
        isPending={feedback.isPending}
        error={feedback.error}
        pendingLabel={strings.feedback.loading}
      >
        {feedback.data === undefined ? null : feedback.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">{strings.feedback.empty}</p>
        ) : (
          <Table rows={feedback.data} />
        )}
      </QueryState>
    </div>
  );
}

function Table({ rows }: { rows: Feedback[] }): ReactElement {
  return (
    <table className="w-full text-left">
      <thead>
        <tr className="border-b border-border text-sm text-muted-foreground">
          <th className="py-2 text-right font-medium">{strings.feedback.foodHeading}</th>
          <th className="py-2 text-right font-medium">{strings.feedback.serviceHeading}</th>
          <th className="py-2 text-right font-medium">{strings.feedback.returnHeading}</th>
          <th className="py-2 font-medium">{strings.feedback.commentHeading}</th>
          <th className="py-2 font-medium">{strings.feedback.sourceHeading}</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.id} className="border-b border-border">
            <td className="py-2 text-right tabular-nums">
              {strings.feedback.rating(row.food_rating ?? row.overall_rating)}
            </td>
            <td className="py-2 text-right tabular-nums">
              {strings.feedback.rating(row.service_rating)}
            </td>
            <td className="py-2 text-right">{strings.feedback.wouldReturn(row.would_return)}</td>
            <td className="py-2">{row.comment ?? '—'}</td>
            <td className="py-2 text-sm text-muted-foreground">
              {strings.feedback.source[row.source]}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
