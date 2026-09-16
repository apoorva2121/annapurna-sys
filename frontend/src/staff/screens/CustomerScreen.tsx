import { type ReactElement, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { formatINR } from '@shared/money';
import { Button } from '@shared/ui/button';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import {
  type ConsentState,
  type Customer,
  type CustomerPreference,
  useAddPreference,
  useCustomer,
  useCustomerHistory,
  useEraseCustomer,
  useRecordConsent,
  useRemovePreference,
} from '@staff/api/customers';
import { CURRENT_NOTICE_VERSION, NOTICE_LANGUAGE } from '@staff/consentVersion';

/**
 * One customer: who they are, how they like things, what they agreed to, and what they have eaten.
 *
 * **Manager surface** — dense, a table rather than cards, numbers right-aligned and tabular.
 *
 * **The allergy is the only thing on this screen that reaches the kitchen**, and it is copied onto
 * an order when the customer is attached rather than joined at cooking time. So the screen says
 * which preferences are critical in a word as well as a colour, because a chef reading a ticket at
 * two metres is the person the flag is really for.
 *
 * **No consent tick is ever pre-filled.** `docs/compliance-rules.md` §B2: consent is explicit, and
 * a box somebody did not tick is not consent. Every control here starts from what the server
 * recorded, and a purpose nobody has ever been asked about renders as *not asked* rather than as
 * *no* — "we never asked" and "they said no" are different facts.
 *
 * **Erasure names what it destroys and what it keeps**, in the confirmation, before it is pressed.
 * It cannot be undone, and after it the same person returning is a new customer with no history —
 * which is what erasure means and is the sort of thing somebody should hear beforehand.
 */
export default function CustomerScreen(): ReactElement {
  const { customerId = '' } = useParams();
  const customer = useCustomer(customerId);
  const history = useCustomerHistory(customerId);

  return (
    <div className="flex flex-col gap-page p-page">
      <Link to="/customers" className="text-sm text-muted-foreground" data-back>
        {strings.customers.backToList}
      </Link>
      <QueryState
        isPending={customer.isPending}
        error={customer.error}
        pendingLabel={strings.customers.loading}
      >
        {customer.data === undefined ? null : (
          <Profile customer={customer.data} customerId={customerId} />
        )}
      </QueryState>
      <QueryState
        isPending={history.isPending}
        error={history.error}
        pendingLabel={strings.customers.loadingHistory}
      >
        {history.data === undefined ? null : <Visits visits={history.data.visits} />}
      </QueryState>
    </div>
  );
}

function Profile({
  customer,
  customerId,
}: {
  customer: Customer;
  customerId: string;
}): ReactElement {
  return (
    <div className="flex flex-col gap-page">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold">{customer.name ?? strings.customers.noName}</h1>
        <p className="text-sm text-muted-foreground tabular-nums">{customer.phone}</p>
        <p className="text-sm text-muted-foreground">
          {strings.customers.visitSummary(customer.visit_count)}
        </p>
        <p className="text-lg font-semibold tabular-nums">
          {formatINR(customer.lifetime_value)}
        </p>
        {customer.is_erased ? (
          <Notice tone="info" title={strings.customers.erasedTitle}>
            {strings.customers.erasedBody}
          </Notice>
        ) : null}
      </header>

      <Preferences customerId={customerId} preferences={customer.preferences} />
      <Consents customerId={customerId} consents={customer.consents} />
      {customer.is_erased ? null : <Erase customerId={customerId} customer={customer} />}
    </div>
  );
}

function Preferences({
  customerId,
  preferences,
}: {
  customerId: string;
  preferences: CustomerPreference[];
}): ReactElement {
  const [value, setValue] = useState('');
  const add = useAddPreference(customerId);
  const remove = useRemovePreference(customerId);

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-lg font-semibold">{strings.customers.preferencesTitle}</h2>
      <p className="text-sm text-muted-foreground">{strings.customers.preferencesHint}</p>

      {preferences.length === 0 ? (
        <p className="text-sm text-muted-foreground">{strings.customers.noPreferences}</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {preferences.map((preference) => (
            <li
              key={preference.id}
              className="flex min-h-target items-center justify-between gap-2 border-b border-border"
            >
              <span className="flex items-center gap-2">
                <span>{preference.value}</span>
                {preference.is_critical ? (
                  <span className="rounded-full bg-critical-soft px-2 py-0.5 text-xs font-medium text-critical">
                    {strings.customers.allergyBadge}
                  </span>
                ) : null}
              </span>
              <Button
                variant="ghost"
                onClick={() => { remove.mutate(preference.id); }}
                disabled={remove.isPending}
              >
                {strings.customers.removePreference}
              </Button>
            </li>
          ))}
        </ul>
      )}

      <div className="flex min-h-target items-center gap-2">
        <input
          className="min-h-target flex-1 rounded-md border border-border bg-background px-3 text-base"
          value={value}
          onChange={(event) => { setValue(event.target.value); }}
          placeholder={strings.customers.allergyPlaceholder}
          aria-label={strings.customers.allergyPlaceholder}
        />
        <Button
          onClick={() => {
            add.mutate(
              { type: 'allergy', value, is_critical: true },
              {
                onSuccess: () => {
                  setValue('');
                },
              },
            );
          }}
          disabled={value.trim() === '' || add.isPending}
        >
          {strings.customers.addAllergy}
        </Button>
      </div>
      {add.error ? <Notice tone="critical" {...errorProps(add.error)} /> : null}
      {remove.error ? <Notice tone="critical" {...errorProps(remove.error)} /> : null}
    </section>
  );
}

const PURPOSES = ['order_contact', 'service_recognition', 'feedback_followup', 'marketing'] as const;

function Consents({
  customerId,
  consents,
}: {
  customerId: string;
  consents: ConsentState[];
}): ReactElement {
  const record = useRecordConsent(customerId);
  const byPurpose = new Map(consents.map((consent) => [consent.purpose, consent]));

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-lg font-semibold">{strings.customers.consentTitle}</h2>
      <p className="text-sm text-muted-foreground">{strings.customers.consentHint}</p>

      <ul className="flex flex-col gap-2">
        {PURPOSES.map((purpose) => {
          const state = byPurpose.get(purpose);
          return (
            <li
              key={purpose}
              className="flex min-h-target items-center justify-between gap-2 border-b border-border"
            >
              <span className="flex flex-col">
                <span>{strings.customers.purpose[purpose]}</span>
                {/* Never asked is not the same as refused, and the screen must not show them
                    the same way. */}
                <span className="text-xs text-muted-foreground">
                  {state === undefined
                    ? strings.customers.neverAsked
                    : strings.customers.consentState(state.granted, state.occurred_at)}
                </span>
              </span>
              <Button
                variant={state?.granted === true ? 'ghost' : 'primary'}
                onClick={() => {
                  record.mutate({
                    purpose,
                    granted: state?.granted !== true,
                    notice_version: CURRENT_NOTICE_VERSION,
                    notice_language: NOTICE_LANGUAGE,
                  });
                }}
                disabled={record.isPending}
              >
                {state?.granted === true
                  ? strings.customers.withdraw
                  : strings.customers.grant}
              </Button>
            </li>
          );
        })}
      </ul>
      {record.error ? <Notice tone="critical" {...errorProps(record.error)} /> : null}
    </section>
  );
}

function Erase({
  customerId,
  customer,
}: {
  customerId: string;
  customer: Customer;
}): ReactElement {
  const [confirming, setConfirming] = useState(false);
  const erase = useEraseCustomer(customerId);

  if (erase.data !== undefined) {
    return (
      <Notice tone="success" title={strings.customers.erasedTitle}>
        {strings.customers.erasureKept(
          erase.data.orders_retained,
          formatINR(erase.data.lifetime_value_retained),
        )}
      </Notice>
    );
  }

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-lg font-semibold">{strings.customers.eraseTitle}</h2>
      {confirming ? (
        <>
          {/* The confirmation names the person and says what survives, because erasure cannot be
              undone and "Are you sure?" tells nobody anything. */}
          <Notice tone="critical" title={strings.customers.eraseConfirmTitle(customer.phone)}>
            {strings.customers.eraseConfirmBody}
          </Notice>
          <div className="flex gap-2">
            <Button
              variant="destructive"
              onClick={() => { erase.mutate({}); }}
              disabled={erase.isPending}
            >
              {strings.customers.eraseConfirm}
            </Button>
            <Button variant="ghost" onClick={() => { setConfirming(false); }}>
              {strings.customers.eraseCancel}
            </Button>
          </div>
        </>
      ) : (
        <Button variant="ghost" onClick={() => { setConfirming(true); }}>
          {strings.customers.eraseStart}
        </Button>
      )}
      {erase.error ? <Notice tone="critical" {...errorProps(erase.error)} /> : null}
    </section>
  );
}

function Visits({ visits }: { visits: { order_id: string; business_date: string; total: string; items: string[] }[] }): ReactElement {
  if (visits.length === 0) {
    return (
      <section className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold">{strings.customers.visitsTitle}</h2>
        <p className="text-sm text-muted-foreground">{strings.customers.noVisits}</p>
      </section>
    );
  }

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-lg font-semibold">{strings.customers.visitsTitle}</h2>
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-border text-sm text-muted-foreground">
            <th className="py-2 font-medium">{strings.customers.dayHeading}</th>
            <th className="py-2 font-medium">{strings.customers.itemsHeading}</th>
            <th className="py-2 text-right font-medium">{strings.customers.totalHeading}</th>
          </tr>
        </thead>
        <tbody>
          {visits.map((visit) => (
            <tr key={visit.order_id} className="border-b border-border">
              <td className="py-2 tabular-nums">{visit.business_date}</td>
              <td className="py-2">{visit.items.join(', ')}</td>
              <td className="py-2 text-right tabular-nums">{formatINR(visit.total)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
