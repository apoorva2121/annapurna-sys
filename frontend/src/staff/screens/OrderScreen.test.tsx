// Taking an order, and the rule the server holds that this screen must not undermine.
//
// **The client sends what was ordered, never what it costs** (`docs/security.md` A04). Adding a dish
// posts its variant, a quantity, its options and the order's version — and nothing named price.
//
// **A dish with nothing to choose is one tap; a required question has to be answered.** The sheet's
// Add stays disabled until every required group has its selection.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import OrderScreen from './OrderScreen';

const MENU = {
  version: 1,
  categories: [
    {
      id: 'c1',
      code: 'MAINS',
      name: 'Mains',
      is_active: true,
      items: [
        {
          id: 'i1',
          code: 'DAL',
          name: 'Dal Makhani',
          description: null,
          food_type: 'veg',
          station_id: 's1',
          image_url: null,
          is_active: true,
          variants: [variant('v1', '470.00')],
          modifier_groups: [],
        },
        {
          id: 'i2',
          code: 'PANEER',
          name: 'Paneer Tikka',
          description: null,
          food_type: 'veg',
          station_id: 's1',
          image_url: null,
          is_active: true,
          variants: [variant('v2', '350.00')],
          modifier_groups: [
            {
              id: 'g1',
              code: 'SPICE',
              name: 'Spice level',
              min_select: 1,
              max_select: 1,
              is_required: true,
              is_active: true,
              modifiers: [
                { id: 'm1', code: 'MILD', name: 'Mild', price_delta: '0.00', is_active: true },
                { id: 'm2', code: 'HOT', name: 'Hot', price_delta: '0.00', is_active: true },
              ],
            },
          ],
        },
      ],
    },
  ],
};

function variant(id: string, price: string): Record<string, unknown> {
  return {
    id,
    code: 'FULL',
    name: 'Full',
    price,
    tax_group_id: 'tg',
    prep_minutes: 12,
    seq: 0,
    is_active: true,
  };
}

const PENDING_LINE = {
  id: 'l1',
  menu_item_variant_id: 'v1',
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
  status: 'pending',
  sent_at: null,
  special_instructions: null,
  cancel_reason: null,
  seq: 1,
  modifiers: [],
};

function order(lines: unknown[] = []): Record<string, unknown> {
  return {
    id: 'o1',
    order_number: '7',
    type: 'dine_in',
    channel: 'pos',
    external_order_id: null,
    status: 'open',
    waiter_employee_id: 'e1',
    covers: 2,
    parent_order_id: null,
    table_ids: ['t6'],
    placed_at: '2026-09-13T12:00:00Z',
    first_sent_at: null,
    served_at: null,
    bill_requested_at: null,
    settled_at: null,
    cancelled_at: null,
    business_date: '2026-09-13',
    subtotal: '0.00',
    discount_total: '0.00',
    charge_total: '0.00',
    tax_total: '0.00',
    round_off: '0.00',
    grand_total: lines.length === 0 ? '0.00' : '493.50',
    cancel_reason: null,
    version: 3,
    lines,
    discounts: [],
    charges: [],
  };
}

function json(body: unknown, status = 200): Response {
  return {
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
    headers: new Headers({ 'content-type': 'application/json' }),
  } as unknown as Response;
}

function renderScreen(current = order()): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn((input: unknown, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === 'POST' || init?.method === 'PATCH') {
      return Promise.resolve(json(order([PENDING_LINE]), 201));
    }
    if (url.endsWith('/staff/menu')) return Promise.resolve(json(MENU));
    if (url.endsWith('/staff/orders/o1')) return Promise.resolve(json(current));
    return Promise.resolve(json({}));
  });
  vi.stubGlobal('fetch', fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/orders/o1']}>
        <Routes>
          <Route path="/orders/:orderId" element={<OrderScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

function posted(fetchMock: ReturnType<typeof vi.fn>, path: string): Record<string, unknown> {
  const post = fetchMock.mock.calls.find(
    ([input, init]) =>
      (init as RequestInit | undefined)?.method === 'POST' && String(input).endsWith(path),
  );
  expect(post).toBeDefined();
  return JSON.parse((post?.[1] as RequestInit).body as string) as Record<string, unknown>;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('OrderScreen', () => {
  it('adds a dish with nothing to choose in one tap, and sends no price', async () => {
    const fetchMock = renderScreen();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: /Dal Makhani/ }));

    const body = posted(fetchMock, '/staff/orders/o1/lines');
    expect(body).toEqual({
      version: 3,
      menu_item_variant_id: 'v1',
      quantity: 1,
      modifier_ids: [],
    });
    expect(Object.keys(body).some((key) => key.includes('price'))).toBe(false);
  });

  it('will not add a dish until its required question is answered', async () => {
    const fetchMock = renderScreen();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: /Paneer Tikka/ }));
    const add = await screen.findByRole('button', { name: 'Add to order' });
    expect(add).toBeDisabled();

    await user.click(screen.getByRole('button', { name: /Mild/ }));
    expect(add).toBeEnabled();
    await user.click(add);

    expect(posted(fetchMock, '/staff/orders/o1/lines')).toMatchObject({
      menu_item_variant_id: 'v2',
      modifier_ids: ['m1'],
    });
  });

  it('sends what is not yet with the kitchen, carrying only the version', async () => {
    const fetchMock = renderScreen(order([PENDING_LINE]));
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Send to kitchen' }));

    expect(posted(fetchMock, '/staff/orders/o1/send')).toEqual({ version: 3 });
  });

  it('changes an unsent dish’s count with the stepper, sending the count and the version', async () => {
    const fetchMock = renderScreen(order([PENDING_LINE]));
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'One more Dal Makhani' }));

    const patch = fetchMock.mock.calls.find(
      ([, init]) => (init as RequestInit | undefined)?.method === 'PATCH',
    );
    expect(String(patch?.[0])).toMatch(/\/staff\/orders\/o1\/lines\/l1$/);
    expect(JSON.parse((patch?.[1] as RequestInit).body as string)).toEqual({
      version: 3,
      quantity: 2,
    });
  });

  it('offers nothing to send when the kitchen already has everything', async () => {
    renderScreen();

    expect(await screen.findByRole('button', { name: 'Send to kitchen' })).toBeDisabled();
  });
});

// Backlog-issues B2: the two steps the M07 second reader found had no button.
describe('asking for the bill and cancelling', () => {
  it('asks for the bill, carrying only the version', async () => {
    const fetchMock = renderScreen(order([PENDING_LINE]));
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Ask for bill' }));

    expect(posted(fetchMock, '/staff/orders/o1/bill')).toEqual({ version: 3 });
  });

  it('cancels only after it is confirmed and a reason is given', async () => {
    const fetchMock = renderScreen();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Cancel order' }));
    expect(await screen.findByText('Nothing has gone to the kitchen yet.')).toBeInTheDocument();
    const confirm = screen.getByRole('button', { name: 'Yes, cancel it' });
    expect(confirm).toBeDisabled();

    await user.type(screen.getByLabelText(/Why is it being cancelled/), 'opened by mistake');
    expect(confirm).toBeEnabled();
    await user.click(confirm);

    expect(posted(fetchMock, '/staff/orders/o1/cancel')).toEqual({
      version: 3,
      reason: 'opened by mistake',
    });
  });

  it('says how many dishes already went to the kitchen before anyone confirms', async () => {
    renderScreen(order([{ ...PENDING_LINE, status: 'sent', sent_at: '2026-09-13T12:05:00Z' }]));
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Cancel order' }));

    expect(await screen.findByText(/1 dish has already gone to the kitchen/)).toBeInTheDocument();
  });
});
