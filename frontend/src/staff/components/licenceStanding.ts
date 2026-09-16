/**
 * Where the restaurant's FSSAI licence stands on a business date (backlog-issues B8).
 *
 * The date is what the restaurant declared, not a FoSCoS lookup (compliance-rules §A3), so this never
 * says "verified". Thirty days' warning is product convention, not a rule. Dates are compared as
 * `YYYY-MM-DD` strings, which order correctly.
 */
export type LicenceStanding = 'unknown' | 'valid' | 'expiring' | 'expired';

const WARNING_DAYS = 30;

export function licenceStanding(
  expiresOn: string | null | undefined,
  today: string,
): LicenceStanding {
  if (expiresOn === null || expiresOn === undefined || expiresOn === '') {
    return 'unknown';
  }
  if (expiresOn < today) {
    return 'expired';
  }
  const horizon = new Date(`${today}T00:00:00Z`);
  horizon.setUTCDate(horizon.getUTCDate() + WARNING_DAYS);
  return expiresOn <= horizon.toISOString().slice(0, 10) ? 'expiring' : 'valid';
}
