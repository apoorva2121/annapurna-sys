// A settled bill, and the two documents that may follow it.
//
// **Nothing here edits the bill.** A credit note sends dishes and counts — never a price, a tax or a
// total, which are the server's — and a refund typed by whoever hands the money over.
//
// **Portions come from a stepper bounded by what was billed**, so "three naans" cannot be credited
// on a bill that had one.
//
// **Cancelling withdraws a legal document**, so it asks what the error was before it can be sent.

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi, type Mock } from 'vitest';

import InvoiceScreen from './InvoiceScreen';

function line(id: string, variantId: string, quantity: number): Record<string, unknown> {
  return {
    id,
    menu_item_variant_id: variantId,
    quantity,
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

function settledOrder(invoiceId: string | null): Record<string, unknown> {
  return {
    id: 'o1',
    order_number: '7',
    status: invoiceId === null ? 'served' : 'settled',
    business_date: '2026-09-13',
    grand_total: '987.00',
    version: 7,
    lines: [line('l1', 'v1', 2), line('l2', 'v2', 1)],
    discounts: [],
    charges: [],
    invoice_id: invoiceId,
  };
}

const INVOICE = {
  id: 'inv1',
  order_id: 'o1',
  document_type: 'tax_invoice',
  invoice_number: '2026-27/000001',
  financial_year: '2026-27',
  status: 'issued',
  issued_at: '2026-09-13T13:00:00Z',
  invoice_date: '2026-09-13',
  business_date: '2026-09-13',
  supplier_name: 'Spice Garden',
  supplier_gstin: '27AAAAA0000A1Z5',
  fssai_licence: null,
  recipient_name: null,
  recipient_gstin: null,
  sac_code: '996331',
  taxable_total: '940.00',
  cgst_total: '23.50',
  sgst_total: '23.50',
  non_gst_tax_total: '0.00',
  discount_total: '0.00',
  charge_total: '0.00',
  round_off: '0.00',
  grand_total: '987.00',
  cancelled_at: null,
  cancel_reason: null,
  payments: [
    {
      id: 'p1',
      method: 'upi',
      amount: '987.00',
      tip_amount: '0.00',
      reference: null,
      status: 'success',
      paid_at: '2026-09-13T13:00:00Z',
      credit_note_id: null,
    },
  ],
};

const CREDIT_NOTE = {
  id: 'cn1',
  invoice_id: 'inv1',
  credit_note_number: 'CN/2026-27/00001',
  financial_year: '2026-27',
  issued_at: '2026-09-13T13:30:00Z',
  note_date: '2026-09-13',
  business_date: '2026-09-13',
  reason: 'Sent back cold',
  issued_by: 'e2',
  taxable_total: '235.00',
  cgst_total: '5.88',
  sgst_total: '5.88',
  non_gst_tax_total: '0.00',
  grand_total: '246.76',
  lines: [],
  refunds: [
    {
      id: 'p2',
      method: 'cash',
      amount: '-246.76',
      tip_amount: '0.00',
      reference: null,
      status: 'success',
      paid_at: '2026-09-13T13:30:00Z',
      credit_note_id: 'cn1',
    },
  ],
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

/** The shape `fetch` is mocked with here. Vitest 5 types a bare `vi.fn` as a procedure
 *  returning void, which makes every Promise-returning implementation a misused promise. */
type FetchMock = Mock<(input: unknown, init?: RequestInit) => Promise<Response>>;

function renderScreen(
  invoiceId: string | null = 'inv1',
  credited: unknown[] = [],
): FetchMock {
  let cancelled = false;
  const invoice = (): Record<string, unknown> =>
    cancelled
      ? { ...INVOICE, status: 'cancelled', cancel_reason: 'Billed to the wrong table' }
      : { ...INVOICE, credited };
  // The server as a route table: the first path suffix that matches answers. Only the credit-note
  // and cancel routes are ever posted to, so no responder needs to look at the method.
  const routes: [string, () => unknown][] = [
    ['/credit-notes', () => CREDIT_NOTE],
    [
      '/cancel',
      () => {
        cancelled = true;
        return invoice();
      },
    ],
    ['/staff/invoices/inv1', invoice],
    ['/staff/menu', () => MENU],
    ['/staff/orders/o1', () => settledOrder(invoiceId)],
  ];
  const fetchMock = vi.fn((input: unknown) => {
    const url = String(input);
    const route = routes.find(([suffix]) => url.endsWith(suffix));
    return Promise.resolve(json(route === undefined ? {} : route[1]()));
  });
  vi.stubGlobal('fetch', fetchMock);
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/bills/o1']}>
        <Routes>
          <Route path="/bills/:orderId" element={<InvoiceScreen />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return fetchMock;
}

function postTo(fetchMock: FetchMock, suffix: string): RequestInit | undefined {
  const call = fetchMock.mock.calls.find(
    ([input, init]) =>
      (init)?.method === 'POST' && String(input).endsWith(suffix),
  );
  return call?.[1];
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('InvoiceScreen', () => {
  it('shows the invoice with its tax split and how it was paid', async () => {
    renderScreen();

    expect(await screen.findByText('Invoice 2026-27/000001')).toBeInTheDocument();
    expect(screen.getByText('Issued · Order 7')).toBeInTheDocument();
    expect(screen.getByText('₹940.00')).toBeInTheDocument();
    expect(screen.getAllByText('₹23.50')).toHaveLength(2);
    // Once as the total and once as the UPI payment that covered it. "UPI" alone is ambiguous here:
    // it is also a refund-method button.
    expect(screen.getByRole('heading', { name: 'Payments' })).toBeInTheDocument();
    expect(screen.getAllByText('₹987.00')).toHaveLength(2);
  });

  it('credits whole dishes with a refund, sending dishes and counts but never a price', async () => {
    const fetchMock = renderScreen();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'One more Dal Makhani' }));
    await user.type(screen.getByLabelText('Why is it being credited?'), 'Sent back cold');
    await user.click(screen.getByRole('button', { name: 'Cash' }));
    await user.type(screen.getByLabelText('Amount given back'), '246.76');
    await user.click(screen.getByRole('button', { name: 'Issue credit note' }));

    expect(await screen.findByText('Credit note CN/2026-27/00001 issued')).toBeInTheDocument();
    expect(screen.getByText('Cash refund of ₹246.76')).toBeInTheDocument();
    const init = postTo(fetchMock, '/credit-notes');
    expect(JSON.parse(init?.body as string)).toEqual({
      reason: 'Sent back cold',
      lines: [{ order_line_id: 'l1', quantity: 1 }],
      refunds: [{ method: 'cash', amount: '246.76' }],
    });
    expect((init?.headers as Record<string, string>)['Idempotency-Key']).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('will not issue a credit note with no dish chosen', async () => {
    const fetchMock = renderScreen();
    const user = userEvent.setup();

    await user.type(await screen.findByLabelText('Why is it being credited?'), 'Sent back cold');
    await user.click(screen.getByRole('button', { name: 'Issue credit note' }));

    expect(await screen.findByText('Choose at least one dish to credit.')).toBeInTheDocument();
    expect(postTo(fetchMock, '/credit-notes')).toBeUndefined();
  });

  it('cannot credit more portions than were billed', async () => {
    renderScreen();
    const user = userEvent.setup();

    const more = await screen.findByRole('button', { name: 'One more Butter Naan' });
    await user.click(more);

    expect(more).toBeDisabled();
  });

  it('asks what the error was before it cancels the invoice, then says it is cancelled', async () => {
    const fetchMock = renderScreen();
    const user = userEvent.setup();

    await user.click(await screen.findByRole('button', { name: 'Cancel this invoice' }));
    const confirm = screen.getByRole('button', { name: 'Cancel the invoice' });
    expect(confirm).toBeDisabled();

    await user.type(screen.getByLabelText('What was the error?'), 'Billed to the wrong table');
    await user.click(confirm);

    expect(await screen.findByText('This invoice was cancelled')).toBeInTheDocument();
    expect(JSON.parse(postTo(fetchMock, '/cancel')?.body as string)).toEqual({
      reason: 'Billed to the wrong table',
    });
    expect(screen.queryByRole('button', { name: 'Issue credit note' })).not.toBeInTheDocument();
  });

  it('says an order that has not been settled has no invoice', async () => {
    renderScreen(null);

    expect(await screen.findByText(/has not been settled/)).toBeInTheDocument();
  });
});

// Backlog-issues B6: a second credit note is written knowing what the first already took off.
describe('what has already been credited', () => {
  it('says so beside each dish, and offers only what is left to credit', async () => {
    renderScreen('inv1', [{ order_line_id: 'l1', quantity: 1, amount: '493.50' }]);
    const user = userEvent.setup();

    expect(await screen.findByText('1 already credited · ₹493.50')).toBeInTheDocument();
    const more = screen.getByRole('button', { name: 'One more Dal Makhani' });
    await user.click(more);

    expect(more).toBeDisabled();
  });
});

// Decision D27 (backlog-issues B12): every credit note stays on its invoice, and prints.
describe('credit notes already issued', () => {
  it('lists each one and prints it on request', async () => {
    const print = vi.fn();
    vi.stubGlobal('print', print);
    const note = {
      id: 'cn1',
      credit_note_number: 'CN/2026-27/00001',
      note_date: '2026-09-13',
      reason: 'Sent back cold',
      grand_total: '493.50',
      lines: [
        {
          id: 'cl1',
          order_line_id: 'l1',
          quantity: 1,
          taxable_value: '470.00',
          cgst_amount: '11.75',
          sgst_amount: '11.75',
          tax_amount: '23.50',
          line_total: '493.50',
        },
      ],
    };
    const fetchMock = renderScreen();
    fetchMock.mockImplementation((input: unknown) => {
      const url = String(input);
      if (url.endsWith('/staff/invoices/inv1')) {
        return Promise.resolve(json({ ...INVOICE, credit_notes: [note] }));
      }
      if (url.endsWith('/staff/menu')) return Promise.resolve(json(MENU));
      if (url.endsWith('/staff/orders/o1')) return Promise.resolve(json(settledOrder('inv1')));
      return Promise.resolve(json({}));
    });
    const user = userEvent.setup();

    const print_button = await screen.findByRole('button', {
      name: 'Print credit note CN/2026-27/00001',
    });
    expect(screen.getByText('Sent back cold')).toBeInTheDocument();
    await user.click(print_button);

    expect(print).toHaveBeenCalledTimes(1);
  });
});
