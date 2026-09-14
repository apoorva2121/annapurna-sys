// The bill, splitting it, and settling it.
//
// **Every figure is the server's string.** The screen shows what the order says it totals; one payment
// sends the bill's own `grand_total`, and several send exactly what was typed — never a sum made here.
//
// **Settle carries an Idempotency-Key** (ADR 0010), so the table is charged once however many times
// the button is tapped on a stalled connection.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { AuthContext, type AuthState } from '@staff/auth/AuthContext';

import BillScreen from './BillScreen';

function line(id: string, variantId: string): Record<string, unknown> {
  return {
    id,
    menu_item_variant_id: variantId,
    quantity: 1,
    unit_price: '470.00',
    line_subtotal: '470.00',
    line_discount: '0.00',
    tax_regime: 'gst',
    tax_rate: '0.0500',
    tax_inclusive: false,
    taxable_value: '470.00',
    cgst_amount: '11.75',
    sgst_amount: '11.75',
    tax_amount: '23.50',
    line_total: '493.50',
    status: 'served',
    sent_at: '2026-09-13T12:05:00Z',
    special_instructions: null,
    cancel_reason: null,
    seq: 1,
    modifiers: [],
  };
}

const ORDER = {
  id: 'o1',
  order_number: '7',
  type: 'dine_in',
  channel: 'pos',
  external_order_id: null,
  status: 'served',
  waiter_employee_id: 'e1',
  covers: 2,
  parent_order_id: null,
  table_ids: ['t6'],
  placed_at: '2026-09-13T12:00:00Z',
  first_sent_at: '2026-09-13T12:05:00Z',
  served_at: '2026-09-13T12:30:00Z',
  bill_requested_at: '2026-09-13T12:50:00Z',
  settled_at: null,
  cancelled_at: null,
  business_date: '2026-09-13',
  subtotal: '940.00',
  discount_total: '0.00',
  charge_total: '0.00',
  tax_total: '47.00',
  round_off: '0.00',
  grand_total: '987.00',
  cancel_reason: null,
  version: 6,
  lines: [line('l1', 'v1'), line('l2', 'v2')],
  discounts: [],
  charges: [],
};

const MENU = {
  version: 1,
  categories: [
    {
      id: 'c1',
      name: 'Mains',
      is_active: true,
      items: [
        {
          id: 'i1',
          name: 'Dal Makhani',
          variants: [{ id: 'v1', name: 'Full' }],
          modifier_groups: [],
        },
        {
          id: 'i2',
          name: 'Butter Naan',
          variants: [{ id: 'v2', name: 'One' }],
          modifier_groups: [],
        },
      ],
    },
  ],
};

function json(body: unknown, status = 200): Response {
  return {
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
    headers: new Headers({ 'content-type': 'application/json' }),
  } as unknown as Response;
}

/** What each POST answers with, by the end of its path. Discounts and charges return the order. */
const POSTS: [string, () => unknown][] = [
  ['/discounts', () => ORDER],
  ['/charges', () => ORDER],
  ['/settle', () => ({ id: 'inv1', invoice_number: '2026-27/000001' })],
  ['/split', () => ({ ...ORDER, id: 'o2', order_number: '8' })],
];

function renderScreen(can: AuthState['can'] = () => true): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn((input: unknown, init?: RequestInit) => {
    const url = String(input);
    const posted =
      init?.method === 'POST' ? POSTS.find(([suffix]) => url.endsWith(suffix)) : undefined;
    if (posted !== undefined) return Promise.resolve(json(posted[1](), 201));
    if (url.endsWith('/staff/menu')) return Promise.resolve(json(MENU));
    if (url.endsWith('/staff/orders/o1')) return Promise.resolve(json(ORDER));
    return Promise.resolve(json({}));
  });
  vi.stubGlobal('fetch', fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/orders/o1/bill']}>
        <AuthContext.Provider
          value={{
            session: null,
            signIn: () => Promise.resolve(),
            signOut: () => Promise.resolve(),
            can,
          }}
        >
          <Routes>
            <Route path="/orders/:orderId/bill" element={<BillScreen />} />
          </Routes>
        </AuthContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

function postTo(fetchMock: ReturnType<typeof vi.fn>, suffix: string): RequestInit | undefined {
  const call = fetchMock.mock.calls.find(
    ([input, init]) =>
      (init as RequestInit | undefined)?.method === 'POST' && String(input).endsWith(suffix),
  );
  return call?.[1] as RequestInit | undefined;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('BillScreen', () => {
  it('shows the bill as the server totalled it, and says it is provisional', async () => {
    renderScreen();

    expect(await screen.findByText('₹940.00')).toBeInTheDocument();
    expect(screen.getByText('₹47.00')).toBeInTheDocument();
    expect(screen.getAllByText('₹987.00').length).toBeGreaterThan(0);
    expect(screen.getByText(/Provisional bill/)).toBeInTheDocument();
  });

  it('settles for the bill’s own total with an idempotency key, then shows the invoice', async () => {
    const fetchMock = renderScreen();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: /Cash/ }));
    await user.click(screen.getByRole('button', { name: 'Settle ₹987.00' }));

    expect(await screen.findByText('Invoice 2026-27/000001')).toBeInTheDocument();
    const init = postTo(fetchMock, '/settle');
    expect(JSON.parse(init?.body as string)).toEqual({
      version: 6,
      payments: [{ method: 'cash', amount: '987.00' }],
    });
    expect((init?.headers as Record<string, string>)['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('splits one bill across payments, sending what was typed and adding nothing up', async () => {
    const fetchMock = renderScreen();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Split the payment' }));
    await user.type(screen.getByLabelText('Amount for payment 1'), '500');
    await user.type(screen.getByLabelText('Amount for payment 2'), '487');
    await user.click(screen.getAllByRole('button', { name: /Cash/ })[1] as HTMLElement);
    await user.click(screen.getByRole('button', { name: 'Settle ₹987.00' }));

    expect(await screen.findByText('Invoice 2026-27/000001')).toBeInTheDocument();
    expect(JSON.parse(postTo(fetchMock, '/settle')?.body as string)).toEqual({
      version: 6,
      payments: [
        { method: 'upi', amount: '500.00' },
        { method: 'cash', amount: '487.00' },
      ],
    });
  });

  it('will not settle a split payment with an amount left blank', async () => {
    const fetchMock = renderScreen();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Split the payment' }));
    await user.type(screen.getByLabelText('Amount for payment 1'), '500');
    await user.click(screen.getByRole('button', { name: 'Settle ₹987.00' }));

    expect(await screen.findByText('Enter an amount for every payment.')).toBeInTheDocument();
    expect(postTo(fetchMock, '/settle')).toBeUndefined();
  });

  it('moves the ticked dishes to a separate bill before anything is settled', async () => {
    const fetchMock = renderScreen();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Split by dishes' }));
    await user.click(await screen.findByRole('checkbox', { name: /Butter Naan/ }));
    await user.click(screen.getByRole('button', { name: 'Move to a separate bill' }));

    expect(await screen.findByText('Moved to a separate bill')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'Open the bill for order 8' })).toHaveAttribute(
      'href',
      '/orders/o2/bill',
    );
    expect(JSON.parse(postTo(fetchMock, '/split')?.body as string)).toEqual({
      version: 6,
      line_ids: ['l2'],
    });
  });
});

// Decision D2 (backlog-issues B7): whoever holds `order.discount` may comp or discount, choosing the
// reason from a short list with an optional note, and is recorded as its authoriser by the server.
// No second approval; the monthly comps-by-authoriser report is the check.
describe('discounts and comps', () => {
  function sent(fetchMock: ReturnType<typeof vi.fn>, suffix: string): Record<string, unknown> {
    const body = postTo(fetchMock, suffix)?.body;
    if (typeof body !== 'string') {
      throw new Error(`nothing was posted to ${suffix}`);
    }
    return JSON.parse(body) as Record<string, unknown>;
  }

  it('comps one dish with a reason from the list and a note', async () => {
    const fetchMock = renderScreen();
    const user = userEvent.setup();
    await screen.findByRole('heading', { name: 'Discounts and comps' });

    await user.click(screen.getByRole('radio', { name: 'Comp (on the house)' }));
    await user.click(screen.getByRole('radio', { name: 'Dal Makhani' }));
    await user.click(screen.getByRole('radio', { name: 'Food came out wrong' }));
    await user.type(screen.getByLabelText('Note (optional)'), 'cold');
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    expect(sent(fetchMock, '/orders/o1/discounts')).toEqual({
      version: 6,
      type: 'comp',
      rate: '1.0000',
      order_line_id: 'l1',
      reason: 'Food came out wrong: cold',
    });
  });

  it('takes a percentage off the whole bill, without a float in between', async () => {
    const fetchMock = renderScreen();
    const user = userEvent.setup();
    await screen.findByRole('heading', { name: 'Discounts and comps' });

    await user.click(screen.getByRole('radio', { name: 'Percentage off' }));
    await user.type(screen.getByLabelText('Percent off'), '12.5');
    await user.click(screen.getByRole('radio', { name: 'Regular guest' }));
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    expect(sent(fetchMock, '/orders/o1/discounts')).toEqual({
      version: 6,
      type: 'percentage',
      rate: '0.1250',
      reason: 'Regular guest',
    });
  });

  it('asks for a note when the reason is Other, and sends nothing until it has one', async () => {
    const fetchMock = renderScreen();
    const user = userEvent.setup();
    await screen.findByRole('heading', { name: 'Discounts and comps' });

    await user.click(screen.getByRole('radio', { name: 'Comp (on the house)' }));
    await user.click(screen.getByRole('radio', { name: 'Other' }));
    await user.click(screen.getByRole('button', { name: 'Apply' }));

    expect(await screen.findByText('Say what happened in the note.')).toBeInTheDocument();
    expect(postTo(fetchMock, '/discounts')).toBeUndefined();
  });

  it('is not offered to someone who cannot give one', async () => {
    renderScreen((permission) => permission !== 'order.discount');
    await screen.findByText('Provisional bill. The invoice number is given when it is settled.');

    expect(screen.queryByRole('heading', { name: 'Discounts and comps' })).not.toBeInTheDocument();
  });

  it('adds the optional service charge at the restaurant’s own rate, typing no amount', async () => {
    const fetchMock = renderScreen();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Add service charge' }));

    expect(sent(fetchMock, '/orders/o1/charges')).toEqual({ version: 6, type: 'service_charge' });
  });
});
