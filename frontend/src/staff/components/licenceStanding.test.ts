// Backlog-issues B8. The FSSAI licence number prints on every bill (compliance-rules §A3), and
// nothing warned when the licence behind it had lapsed.
import { describe, expect, it } from 'vitest';

import { licenceStanding } from './licenceStanding';

describe('licenceStanding', () => {
  it('knows nothing when no date was entered', () => {
    expect(licenceStanding(null, '2026-09-14')).toBe('unknown');
    expect(licenceStanding(undefined, '2026-09-14')).toBe('unknown');
  });

  it('calls a licence valid until yesterday expired', () => {
    expect(licenceStanding('2026-09-13', '2026-09-14')).toBe('expired');
  });

  it('warns within thirty days, the last day included', () => {
    expect(licenceStanding('2026-09-14', '2026-09-14')).toBe('expiring');
    expect(licenceStanding('2026-10-14', '2026-09-14')).toBe('expiring');
    expect(licenceStanding('2026-10-15', '2026-09-14')).toBe('valid');
  });
});
