// What "joined on" defaults to, which was wrong for five and a half hours out of every day.
//
// The field used to default to `new Date().toISOString().slice(0, 10)` — the browser's UTC date.
// In India that is *yesterday* from local midnight until 05:30, so anyone adding a waiter during a
// late shift got a joining date one day early, already filled in and looking entirely reasonable.
// Nothing about it appears wrong on screen, and the record is only questioned much later.
//
// These freeze the clock at the times that used to be wrong. Without a fixed clock the test would
// pass or fail depending on what time of day it ran, which is worse than not having it.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthState } from '@staff/auth/AuthContext';
import type { RestaurantSummary, Session } from '@staff/auth/session';

import NewEmployeeScreen from './NewEmployeeScreen';

const RESTAURANT: RestaurantSummary = {
  id: 'r1',
  name: 'Spice Garden - Koregaon Park',
  code: 'SG_KOREGAON',
  timezone: 'Asia/Kolkata',
  currency: 'INR',
  business_day_start: '05:00:00',
  theme: { default: null, schedule: [] },
};

function authFor(restaurant: RestaurantSummary): AuthState {
  const session: Session = {
    employeeId: 'e1',
    passwordChangeRequired: false,
    fullName: 'Priya Nair',
    employeeCode: 'EMP001',
    restaurant,
    restaurants: [restaurant],
    roles: ['owner'],
    permissions: new Set<string>(),
  };
  return {
    session,
    signIn: () => Promise.resolve(),
    signOut: () => Promise.resolve(),
    can: () => true,
  };
}

function renderScreen(restaurant: RestaurantSummary = RESTAURANT): void {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AuthContext.Provider value={authFor(restaurant)}>
          <NewEmployeeScreen />
        </AuthContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function joinedOnField(): HTMLInputElement {
  return screen.getByLabelText(/joined on/i);
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

describe('the joining date default', () => {
  it('is not the local calendar date once midnight has passed', () => {
    // 18:45 UTC on 10 March is 00:15 IST on the 11th. The calendar has rolled over; the business
    // day has not, and with a 05:00 start the answer is still the 10th.
    //
    // This case rules out "convert to the restaurant's zone, then take the date" — the fix someone
    // reaches for first, which corrects the offset and still ignores the 05:00 start. The plain UTC
    // date is accidentally right here, so it is the *next* test that rules that one out. Neither
    // mistake can be caught by testing against the other.
    vi.setSystemTime(new Date(Date.UTC(2026, 2, 10, 18, 45)));

    renderScreen();

    expect(new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Kolkata' })).toBe('2026-03-11');
    expect(joinedOnField().value).toBe('2026-03-10');
  });

  it('is not the UTC date when those differ', () => {
    // 23:45 UTC on the 10th is 05:15 IST on the 11th — past the start, so the 11th. The browser's
    // UTC date says the 10th, and this is the case that separates the two.
    vi.setSystemTime(new Date(Date.UTC(2026, 2, 10, 23, 45)));

    renderScreen();

    expect(new Date().toISOString().slice(0, 10)).toBe('2026-03-10');
    expect(joinedOnField().value).toBe('2026-03-11');
  });

  it('reads the start time from the restaurant rather than assuming 05:00', () => {
    // A restaurant whose day starts at 03:00 gets a different answer for the same instant. A
    // hard-coded default would pass both tests above and be wrong for the first place that moves it.
    vi.setSystemTime(new Date(Date.UTC(2026, 2, 10, 22, 0))); // 03:30 IST on the 11th

    renderScreen({ ...RESTAURANT, business_day_start: '03:00:00' });

    expect(joinedOnField().value).toBe('2026-03-11');
  });

  it('gives the same instant the previous day when the start time is later', () => {
    vi.setSystemTime(new Date(Date.UTC(2026, 2, 10, 22, 0))); // 03:30 IST on the 11th

    renderScreen({ ...RESTAURANT, business_day_start: '05:00:00' });

    expect(joinedOnField().value).toBe('2026-03-10');
  });

  it('is a date the date input will accept', () => {
    // `<input type="date">` silently shows an empty field for anything that is not YYYY-MM-DD, so
    // a malformed default would look like "no default" rather than like a bug.
    vi.setSystemTime(new Date(Date.UTC(2026, 2, 10, 18, 45)));

    renderScreen();

    expect(joinedOnField().value).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
