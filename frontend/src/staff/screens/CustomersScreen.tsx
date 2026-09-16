import { type ReactElement, useState } from 'react';
import { Link } from 'react-router-dom';

import { QueryState } from '@staff/components/QueryState';
import { strings } from '@staff/strings';
import { type CustomerListItem, useCustomers } from '@staff/api/customers';

/**
 * The customers of **this branch**, most recent visit first.
 *
 * **Manager surface**, and deliberately thinner than the profile: number, name, visits, last visit.
 * Not birthdays, not preferences, not lifetime value. A customer list is a competitor's most
 * valuable asset and the P1 design hands `customer.view` to waiters on purpose — so the control is
 * the shape of this screen rather than the permission behind it. None of that stops somebody with
 * an evening and a phone camera; it makes the fast version not exist.
 *
 * **Most recent visit first**, because the person a manager is looking for is nearly always
 * somebody who was here lately.
 *
 * **The branch rule is said out loud** in the hint rather than left to be discovered. A manager
 * who cannot find a regular should learn in one line that the regular belongs to another branch and
 * that switching is how to see them — not conclude the search is broken.
 */
export default function CustomersScreen(): ReactElement {
  const [search, setSearch] = useState('');
  const customers = useCustomers(search);

  return (
    <div className="flex flex-col gap-page p-page">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">{strings.customers.title}</h1>
        <p className="text-sm text-muted-foreground">{strings.customers.branchHint}</p>
      </header>

      <input
        className="min-h-target rounded-md border border-border bg-background px-3 text-base"
        value={search}
        onChange={(event) => { setSearch(event.target.value); }}
        placeholder={strings.customers.searchLabel}
        aria-label={strings.customers.searchLabel}
      />

      <QueryState
        isPending={customers.isPending}
        error={customers.error}
        pendingLabel={strings.customers.loading}
      >
        {customers.data === undefined ? null : <List items={customers.data} search={search} />}
      </QueryState>
    </div>
  );
}

function List({
  items,
  search,
}: {
  items: CustomerListItem[];
  search: string;
}): ReactElement {
  if (items.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        {search === '' ? strings.customers.empty : strings.customers.noResults}
      </p>
    );
  }

  return (
    <table className="w-full text-left">
      <thead>
        <tr className="border-b border-border text-sm text-muted-foreground">
          <th className="py-2 font-medium">{strings.customers.nameHeading}</th>
          <th className="py-2 font-medium">{strings.customers.phoneHeading}</th>
          <th className="py-2 text-right font-medium">{strings.customers.visitsHeading}</th>
          <th className="py-2 text-right font-medium">{strings.customers.lastVisitHeading}</th>
        </tr>
      </thead>
      <tbody>
        {items.map((item) => (
          <tr key={item.id} className="border-b border-border">
            <td className="py-2">
              <Link to={`/customers/${item.id}`} className="flex min-h-target items-center gap-2">
                <span>{item.name ?? strings.customers.noName}</span>
                {item.is_erased ? (
                  <span className="rounded-full bg-info-soft px-2 py-0.5 text-xs font-medium text-info">
                    {strings.customers.erasedTitle}
                  </span>
                ) : null}
              </Link>
            </td>
            <td className="py-2 tabular-nums">{item.phone}</td>
            <td className="py-2 text-right tabular-nums">{item.visit_count}</td>
            <td className="py-2 text-right tabular-nums">
              {item.last_visit_at === null ? '—' : item.last_visit_at.slice(0, 10)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
