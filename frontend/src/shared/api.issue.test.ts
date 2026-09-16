// Backlog-issues B12 (D11, D12). The server sends an issue number with every error it catalogues; the
// browser makes three errors of its own and must number them from the same catalogue.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { FRONTEND_ISSUES, apiGet } from '@shared/api';

import catalogue from '../../../backend/app/core/issues.json';

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('issue numbers', () => {
  it('carries the number the server sent', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() =>
        Promise.resolve(
          new Response(
            JSON.stringify({
              code: 'cash.payout_exceeds_till',
              message: 'Not enough cash in the till. Only ₹2,000.00 is available.',
              details: {},
              issue: 1042,
            }),
            { status: 422, headers: { 'Content-Type': 'application/json' } },
          ),
        ),
      ),
    );

    await expect(apiGet('/staff/cash/sessions')).rejects.toMatchObject({
      code: 'cash.payout_exceeds_till',
      issue: 1042,
    });
  });

  it('numbers the errors the browser makes from the same catalogue', () => {
    for (const [code, number] of Object.entries(FRONTEND_ISSUES)) {
      expect(catalogue.issues.find((issue) => issue.code === code)?.number).toBe(number);
    }
  });

  it('numbers a dead network', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(() => Promise.reject(new TypeError('Failed to fetch'))),
    );

    await expect(apiGet('/staff/cash/sessions')).rejects.toMatchObject({
      code: 'network.unreachable',
      issue: FRONTEND_ISSUES['network.unreachable'],
    });
  });
});
