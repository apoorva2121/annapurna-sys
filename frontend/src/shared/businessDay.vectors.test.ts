// Backlog-issues B10. The browser's half of the business-day rule, against the cases the backend
// reads too (`contracts/business-day-vectors.json`). A case added there is checked on both sides.
import { describe, expect, it } from 'vitest';

import { businessDateOf } from '@shared/businessDay';

import vectors from '../../../contracts/business-day-vectors.json';

describe('the business-day vectors shared with the backend', () => {
  it('has enough of them to mean something', () => {
    expect(vectors.cases.length).toBeGreaterThanOrEqual(12);
  });

  it.each(vectors.cases)('$name', (vector) => {
    expect(businessDateOf(new Date(vector.instant), vector.timezone, vector.day_starts_at)).toBe(
      vector.business_date,
    );
  });
});
