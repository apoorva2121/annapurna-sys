import { type FormEvent, type ReactElement, useState } from 'react';

import { businessDayExample } from '@shared/businessDay';
import { Button } from '@shared/ui/button';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import { type Restaurant, useRestaurant, useUpdateRestaurant } from '@staff/api/setup';

/**
 * The restaurant's own settings — owner and admin only.
 *
 * The whole screen exists for one control. `business_day_start` decides which day every order's
 * takings land in, it is the setting ADR 0004 says owners misunderstand most, and moving it is the
 * one action here that silently restates numbers somebody has already read. Everything else on this
 * page is a text field.
 *
 * So the worked example under it is not decoration and is not a tooltip: a label reading "05:00"
 * teaches nobody what 05:00 does. The sentence is **computed** by `businessDayExample`, which runs
 * the same rule the server runs — an explanation written out as prose would be a second statement
 * of the rule, free to drift, with no way for the reader to tell which one the server obeys.
 */
export default function RestaurantSettingsScreen(): ReactElement {
  const restaurant = useRestaurant();

  return (
    <div className="max-w-2xl space-y-page">
      <h1 className="text-2xl font-semibold">{strings.setup.restaurant.title}</h1>
      <QueryState
        isPending={restaurant.isPending}
        error={restaurant.error}
        pendingLabel={strings.setup.restaurant.loading}
      >
        {restaurant.data === undefined ? null : <SettingsForm restaurant={restaurant.data} />}
      </QueryState>
    </div>
  );
}

function SettingsForm({ restaurant }: { restaurant: Restaurant }): ReactElement {
  const save = useUpdateRestaurant();
  const [timezone, setTimezone] = useState(restaurant.timezone);
  const [currency, setCurrency] = useState(restaurant.currency);
  const [dayStart, setDayStart] = useState(restaurant.business_day_start.slice(0, 5));
  const [gstin, setGstin] = useState(restaurant.gstin ?? '');
  const [fssai, setFssai] = useState(restaurant.fssai_licence ?? '');
  const [address, setAddress] = useState(restaurant.address ?? '');

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    save.mutate({
      timezone,
      currency,
      // The control gives `HH:MM`; the API takes `HH:MM:SS`.
      business_day_start: `${dayStart}:00`,
      // Empty is null, not "". A blank GSTIN is the absence of one, and storing an empty string
      // would make "has a GSTIN" true for a restaurant that does not have one.
      gstin: gstin.trim() === '' ? null : gstin.trim(),
      fssai_licence: fssai.trim() === '' ? null : fssai.trim(),
      address: address.trim() === '' ? null : address.trim(),
    });
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
      <Field
        label={strings.setup.restaurant.timezone}
        hint={strings.setup.restaurant.timezoneHint}
        value={timezone}
        onChange={(event) => {
          setTimezone(event.target.value);
        }}
        required
      />

      <BusinessDayStartField value={dayStart} onChange={setDayStart} />

      <Field
        label={strings.setup.restaurant.currency}
        value={currency}
        onChange={(event) => {
          setCurrency(event.target.value);
        }}
        maxLength={3}
        className="uppercase"
        required
      />
      <Field
        label={strings.setup.restaurant.gstin}
        value={gstin}
        onChange={(event) => {
          setGstin(event.target.value);
        }}
        maxLength={15}
      />
      <Field
        label={strings.setup.restaurant.fssai}
        hint={strings.setup.restaurant.fssaiHint}
        value={fssai}
        onChange={(event) => {
          setFssai(event.target.value);
        }}
        maxLength={32}
      />
      <Field
        label={strings.setup.restaurant.address}
        value={address}
        onChange={(event) => {
          setAddress(event.target.value);
        }}
        maxLength={500}
      />

      {/* Every mutation renders pending, error and success explicitly (restaurant-ui rule 6). */}
      {save.isError && <Notice tone="critical" {...errorProps(save.error)} />}
      {save.isSuccess && <Notice tone="success" title={strings.setup.restaurant.saved} />}

      <Button type="submit" disabled={save.isPending} className="self-start">
        {save.isPending ? strings.setup.restaurant.saving : strings.setup.restaurant.save}
      </Button>
    </form>
  );
}

/**
 * The one control on this screen that needs explaining, with its explanation attached.
 *
 * The example re-computes as the value changes, so someone trying 03:00 to see what it does gets
 * the answer for 03:00 rather than the answer for whatever was saved last.
 */
function BusinessDayStartField({
  value,
  onChange,
}: {
  value: string;
  onChange: (next: string) => void;
}): ReactElement {
  // `null` at midnight, where there is no late-night window to illustrate — say so rather than
  // invent an example. An invalid part-typed value ("0") is treated the same way.
  const example = safeExample(value);

  return (
    <div className="space-y-1">
      <Field
        label={strings.setup.restaurant.businessDayStart}
        type="time"
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
        required
      />
      <p className="text-sm font-medium text-foreground">
        {example === null
          ? strings.setup.restaurant.businessDayMidnight
          : strings.setup.restaurant.businessDayExample(
              example.orderTime,
              example.orderDay,
              example.countsToward,
            )}
      </p>
      <p className="text-sm text-muted-foreground">{strings.setup.restaurant.businessDayWhy}</p>
    </div>
  );
}

function safeExample(value: string): ReturnType<typeof businessDayExample> {
  try {
    return businessDayExample(`${value}:00`);
  } catch {
    // A half-typed time is not an error worth showing; the field itself will refuse to submit.
    return null;
  }
}
