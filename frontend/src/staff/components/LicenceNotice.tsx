import type { ReactElement } from 'react';

import { businessToday } from '@shared/businessDay';
import { useAuth } from '@staff/auth/AuthContext';
import { Notice } from '@staff/components/Notice';
import { licenceStanding } from '@staff/components/licenceStanding';
import { strings } from '@staff/strings';

/** Said where bills are made and where the day starts: the licence number printed on every bill
 *  has lapsed, or is about to (backlog-issues B8). Silent when no date was entered. */
export function LicenceNotice(): ReactElement | null {
  const { session } = useAuth();
  if (session === null || session === undefined) {
    return null;
  }
  const { restaurant } = session;
  const expiresOn = restaurant.fssai_licence_expires_on ?? null;
  if (expiresOn === null) {
    // No date declared: nothing to say, and nothing to compute a business day for.
    return null;
  }
  const standing = licenceStanding(
    expiresOn,
    businessToday(restaurant.timezone, restaurant.business_day_start),
  );
  if (standing === 'valid' || standing === 'unknown') {
    return null;
  }
  return standing === 'expired' ? (
    <Notice tone="critical" title={strings.licence.expired(expiresOn)}>
      {strings.licence.expiredHint}
    </Notice>
  ) : (
    <Notice tone="info" title={strings.licence.expiring(expiresOn)} />
  );
}
