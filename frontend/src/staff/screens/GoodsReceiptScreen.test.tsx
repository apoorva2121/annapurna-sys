// The money screen, and the four things that make it worth building.
//
// **It sends quantities as the exact strings that were typed.** A delivery of 46.5 kg has to arrive
// at the server as "46500.0000" and not as a float that has been through `Number` (CLAUDE.md
// invariant 3). Same rule as StockReceiveScreen, on a screen where three numbers go the same way.
//
// **The two inputs cannot be mistaken for each other.** "What the bill says" and "What the scale
// says" — not "Quantity" and "Actual". A store manager who types the invoiced figure into both
// boxes destroys the entire value of M06 while every other test in this project stays green, and
// the wording is the only defence against that.
//
// **No rupee variance appears while a weight is editable.** `docs/waste-model.md`: showing the
// value of a loss before it is logged suppresses honest reporting. A screen saying "this weight
// will flag your supplier for ₹4,200" while somebody holds the scale is asking them to choose
// between an accurate number and an awkward conversation.
//
// **Every figure afterwards comes from the server.** The confirmation panel renders the response's
// own `accepted`, `short_delivery` and rupee values, so the screen and the ledger cannot disagree.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import GoodsReceiptScreen from './GoodsReceiptScreen';

const ORDER = {
  id: 'po1',
  po_number: 'PO-000001',
  supplier_id: 's1',
  status: 'sent',
  expected_at: null,
  total_amount: '2100.00',
  created_by: null,
  cancelled_at: null,
  cancel_reason: null,
  lines: [{ stock_item_id: 'i1', quantity_ordered: '50000.0000', unit_price: '0.042000' }],
};

const ITEMS = {
  items: [{ id: 'i1', code: 'PANEER', name: 'Paneer', base_unit: 'g', kind: 'ingredient' }],
};

const POSTED = {
  receipt: {
    id: 'gr1',
    purchase_order_id: 'po1',
    supplier_id: 's1',
    received_at: '2026-09-13T06:00:00Z',
    business_date: '2026-09-13',
    invoice_number: '4471',
    invoice_amount: '2100.00',
    tax_amount: null,
    received_by: 'e1',
    lines: [],
  },
  lines: [
    {
      stock_item_id: 'i1',
      ordered: '50000.0000',
      invoiced: '50000.0000',
      received: '47000.0000',
      rejected: '500.0000',
      accepted: '46500.0000',
      short_delivery: '3000.0000',
      order_shortfall: '3500.0000',
      unit_price: '0.042000',
      landed_unit_cost: '0.042000',
      short_delivery_value: '126.00',
      accepted_value: '1953.00',
    },
  ],
  invoice_line_total: '2100.00',
  short_delivery_value: '126.00',
  accepted_value: '1953.00',
};

function json(body: unknown, status = 200): Response {
  return {
    ok: status < 400,
    status,
    json: () => Promise.resolve(body),
    headers: new Headers({ 'content-type': 'application/json' }),
  } as unknown as Response;
}

function renderScreen(): ReturnType<typeof vi.fn> {
  const fetchMock = vi.fn((input: unknown, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === 'POST') return Promise.resolve(json(POSTED, 201));
    if (url.includes('purchase-orders/po1')) return Promise.resolve(json(ORDER));
    if (url.includes('stock-items')) return Promise.resolve(json(ITEMS));
    return Promise.resolve(json({}));
  });
  vi.stubGlobal('fetch', fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/purchasing/orders/po1/receive']}>
        <Routes>
          <Route path="/purchasing/orders/:poId/receive" element={<GoodsReceiptScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

/** The POST body, typed rather than stringified through `String()`.
 *
 * eslint's `no-base-to-string` is right to refuse the shorter version: `RequestInit['body']` is a
 * union including `FormData` and `Blob`, and `String()` on either yields "[object Object]" — an
 * assertion that would then pass or fail for reasons unrelated to what was sent. */
function postedBody(fetchMock: ReturnType<typeof vi.fn>): Record<string, unknown> {
  const post = fetchMock.mock.calls.find(
    ([, init]) => (init as RequestInit | undefined)?.method === 'POST',
  );
  expect(post).toBeDefined();
  const raw = (post?.[1] as RequestInit).body;
  expect(typeof raw).toBe('string');
  return JSON.parse(raw as string) as Record<string, unknown>;
}

async function weighIn(invoiced: string, received: string): Promise<void> {
  const user = userEvent.setup();
  await user.type(await screen.findByLabelText('What the bill says'), invoiced);
  await user.type(screen.getByLabelText('What the scale says'), received);
  await user.click(screen.getByRole('button', { name: 'Book it in' }));
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('booking in a delivery', () => {
  it('labels the two quantities so they cannot be confused', async () => {
    // The most important assertion in this file. "Quantity" and "Actual" would be indistinguishable
    // to somebody holding a clipboard, and the whole module depends on these being two numbers.
    renderScreen();

    expect(await screen.findByLabelText('What the bill says')).toBeInTheDocument();
    expect(screen.getByLabelText('What the scale says')).toBeInTheDocument();
    // And the ordered quantity is there for context, as text rather than an editable field.
    expect(screen.getByText('50000.0000')).toBeInTheDocument();
  });

  it('says why weighing matters before anyone has typed anything', async () => {
    renderScreen();

    expect(
      await screen.findByText(/the difference between them is the cheapest money/),
    ).toBeInTheDocument();
  });

  it('shows no rupee figure while the weights can still be changed', async () => {
    // docs/waste-model.md: the value of a loss shown before it is logged suppresses honest
    // reporting. Nothing on this form may put a number on the discrepancy.
    renderScreen();

    await screen.findByLabelText('What the bill says');
    expect(screen.queryByText(/₹/)).not.toBeInTheDocument();
  });

  it('retries a failed booking with the same Idempotency-Key it first sent', async () => {
    // ADR 0010. A second tap after a dropped connection is the same delivery. If the first request
    // had in fact landed, a fresh key would book the stock twice.
    const fetchMock = renderScreen();
    let posts = 0;
    fetchMock.mockImplementation((input: unknown, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === 'POST') {
        posts += 1;
        return posts === 1
          ? Promise.reject(new TypeError('offline'))
          : Promise.resolve(json(POSTED, 201));
      }
      if (url.includes('purchase-orders/po1')) return Promise.resolve(json(ORDER));
      if (url.includes('stock-items')) return Promise.resolve(json(ITEMS));
      return Promise.resolve(json({}));
    });

    await weighIn('1000', '1000');
    await vi.waitFor(() => {
      expect(posts).toBe(1);
      expect(screen.getByRole('button', { name: 'Book it in' })).toBeEnabled();
    });
    await userEvent.setup().click(screen.getByRole('button', { name: 'Book it in' }));
    await vi.waitFor(() => {
      expect(posts).toBe(2);
    });

    const keys = fetchMock.mock.calls
      .filter(([, init]) => (init as RequestInit | undefined)?.method === 'POST')
      .map(([, init]) => ((init as RequestInit).headers as Record<string, string>)['Idempotency-Key']);
    expect(keys).toHaveLength(2);
    expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/);
    expect(keys[1]).toBe(keys[0]);
  });

  it('sends the three quantities as the exact strings that were typed', async () => {
    const fetchMock = renderScreen();

    await weighIn('50000', '46500.5');

    const body = postedBody(fetchMock);
    const lines = body.lines as Record<string, unknown>[];
    expect(lines[0]?.quantity_invoiced).toBe('50000.00');
    // The half kilo survives. `Number('46500.5').toFixed(2)` would too, today — and is exactly the
    // float round-trip that stops being safe at the fourth decimal place, which this column has.
    expect(lines[0]?.quantity_received).toBe('46500.50');
    expect(lines[0]?.quantity_rejected).toBe('0.00');
  });

  it('sends null rather than an empty string for the paperwork nobody filled in', async () => {
    // A market trader who charges no tax and a delivery where nobody wrote the tax down are
    // different facts; storing zero for the second would state a figure nobody reported.
    const fetchMock = renderScreen();

    await weighIn('1000', '1000');

    const body = postedBody(fetchMock);
    expect(body.invoice_number).toBeNull();
    expect(body.invoice_amount).toBeNull();
    expect(body.tax_amount).toBeNull();
  });

  it('refuses a weight that is not a number, without asking the server', async () => {
    const fetchMock = renderScreen();

    await weighIn('50000', 'about forty seven');

    expect(await screen.findByText(/Enter a quantity/)).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.some(([, init]) => (init as RequestInit | undefined)?.method === 'POST'),
    ).toBe(false);
  });

  it('asks why something was refused before it will post', async () => {
    const user = userEvent.setup();
    renderScreen();

    await user.type(await screen.findByLabelText('What the bill says'), '50000');
    await user.type(screen.getByLabelText('What the scale says'), '47000');
    await user.type(screen.getByLabelText('Refused on quality'), '500');
    await user.click(screen.getByRole('button', { name: 'Book it in' }));

    expect(await screen.findByText(/Say why it was refused/)).toBeInTheDocument();
  });

  it('uses text inputs, so the browser never normalises a weight', async () => {
    // `type="number"` lets the browser rewrite "46500.50" as "46500.5" before the app sees it — a
    // silent change to a figure the ledger is supposed to carry exactly.
    renderScreen();

    const invoiced = await screen.findByLabelText('What the bill says');
    expect(invoiced).not.toHaveAttribute('type', 'number');
    expect(invoiced).toHaveAttribute('inputmode', 'decimal');
  });
});

describe('after it is booked in', () => {
  it('shows the money, now that the weights are fixed', async () => {
    renderScreen();

    await weighIn('50000', '47000');

    // Every one of these is a server field, not a browser calculation.
    expect(await screen.findByRole('heading', { name: 'Booked in' })).toBeInTheDocument();
    expect(screen.getByText('46500.0000')).toBeInTheDocument();
    // Twice on purpose: once in the headline sentence and once on the item's own row, because the
    // manager reading the sentence and the manager checking which item are the same person at two
    // different moments.
    expect(screen.getAllByText(/₹126\.00/)).toHaveLength(2);
  });

  it('marks the short-delivered row with a word and not only a colour', async () => {
    // docs/ui/conventions.md rule 5. Commercial kitchens are full of colour-blind men and
    // steamed-up screens, and this is the row somebody has to act on.
    renderScreen();

    await weighIn('50000', '47000');

    const tags = await screen.findAllByText('Billed and not delivered');
    expect(tags.length).toBeGreaterThan(0);
  });
});
