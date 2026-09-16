// Errors a person can act on.
//
// Found in the M03 manual pass on 2026-09-13: adding a menu section, a supplier and a station each
// failed with "The request was not valid." and a code, and nothing else. The server already said
// which field was wrong; this helper threw that away. A restaurant manager cannot fix a form that
// will not say what is wrong with it.

import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { ApiClientError } from '@shared/api';
import { Notice } from '@staff/components/Notice';

import { errorProps, fieldErrors } from './errorProps';

const GSTIN_RULE = 'Use the 15-character GSTIN, for example 27AAPFU0939F1ZV.';
const TERMS_RULE = 'Must be 365 or less.';

const invalid = new ApiClientError({
  code: 'request.invalid',
  message: 'Please fix the 2 highlighted fields.',
  details: {
    fields: [
      { field: 'gstin', code: 'field.format', message: GSTIN_RULE },
      { field: 'payment_terms_days', code: 'field.out_of_range', message: TERMS_RULE },
    ],
  },
});

describe('fieldErrors', () => {
  it('puts each rule under the field it belongs to', () => {
    expect(fieldErrors(invalid)).toEqual({ gstin: GSTIN_RULE, payment_terms_days: TERMS_RULE });
  });

  it('is empty for an error that is not about fields, or is not ours at all', () => {
    const conflict = new ApiClientError({ code: 'table.order_open', message: 'Settle it first.' });
    const malformed = new ApiClientError({
      code: 'request.invalid',
      message: 'Please fix the highlighted field.',
      details: { fields: 'not a list' },
    });
    expect(fieldErrors(conflict)).toEqual({});
    expect(fieldErrors(malformed)).toEqual({});
    expect(fieldErrors(new Error('boom'))).toEqual({});
  });
});

describe('errorProps', () => {
  it('says what to fix, not only that the request was not valid', () => {
    const props = errorProps(invalid, { gstin: 'GSTIN' });

    expect(props.title).toBe('Please fix the 2 highlighted fields.');
    // A form mistake shows its sentences and no issue number (D12).
    expect(props.issue).toBeUndefined();
    // A field the screen names gets its label; one it does not still reads as words, not as
    // `payment_terms_days`.
    expect(props.lines).toEqual([`GSTIN: ${GSTIN_RULE}`, `Payment terms days: ${TERMS_RULE}`]);
  });

  it('renders every rule in the notice, so a field the form does not show is still explained', () => {
    render(<Notice tone="critical" {...errorProps(invalid, { gstin: 'GSTIN' })} />);

    expect(screen.getByRole('alert')).toHaveTextContent(`GSTIN: ${GSTIN_RULE}`);
    expect(screen.getByRole('alert')).toHaveTextContent(`Payment terms days: ${TERMS_RULE}`);
    expect(screen.getByRole('alert')).not.toHaveTextContent('The request was not valid.');
  });

  it('still gives a title for a throw it did not model', () => {
    expect(errorProps(new Error('boom'))).toEqual({
      title: 'Something went wrong.',
      issue: undefined,
      lines: [],
    });
  });
});

// Backlog-issues B12 (owner decisions D11, D12): the code is never shown; the number is.
describe('an error a person reports', () => {
  it('shows the sentence and the issue number, never the code', () => {
    const refusal = new ApiClientError({
      code: 'cash.payout_exceeds_till',
      message: 'Not enough cash in the till. Only ₹2,000.00 is available.',
      issue: 1042,
    });

    render(<Notice tone="critical" {...errorProps(refusal)} />);

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Not enough cash in the till. Only ₹2,000.00 is available.');
    expect(alert).toHaveTextContent('Issue 1042');
    expect(alert).not.toHaveTextContent('cash.payout_exceeds_till');
  });
});
