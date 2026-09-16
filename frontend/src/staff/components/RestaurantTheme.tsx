import { useEffect } from 'react';

import { businessToday } from '@shared/businessDay';
import { applyTheme, readStoredTheme, resolveTheme } from '@shared/theme/theme';
import { useAuth } from '@staff/auth/AuthContext';
import { NO_RESTAURANT_THEME } from '@staff/auth/session';

/**
 * Applies the restaurant's theme once the session is known.
 *
 * `initialiseTheme()` runs in `main.tsx`, before React mounts and before anyone is signed in — it
 * can only see this device's stored choice and the operating system. The restaurant-wide default
 * and the festive schedule arrive with the session, so they are applied here, on the first render
 * that has one.
 *
 * The order is `resolveTheme`'s and is not re-stated: a device choice still wins, then a festive
 * window covering today, then the restaurant default. Re-implementing that precedence here would be
 * the second copy of a rule that already has one.
 *
 * The date compared is the **business date** (ADR 0004). A festival ending "on the 12th" ends when
 * the restaurant's 12th ends — 5am on the 13th — so the theme does not change under the staff at
 * midnight while they are still serving the 12th.
 *
 * Renders nothing. It is a component rather than a call in `AuthProvider` so that it re-runs
 * naturally whenever the session changes — switching branch changes the restaurant, and the new
 * branch may have a different theme.
 */
export function RestaurantTheme(): null {
  const { session } = useAuth();
  const restaurant = session?.restaurant;
  // Serialised so the effect compares the schedule's *contents*, not the identity of an array the
  // session rebuilds on every token refresh. Extracted rather than inlined because a computed
  // expression in a dependency array cannot be checked statically.
  const theme = restaurant?.theme ?? NO_RESTAURANT_THEME;
  const schedule = JSON.stringify(theme.schedule);

  useEffect(() => {
    if (restaurant === undefined) {
      return;
    }
    const today = businessToday(restaurant.timezone, restaurant.business_day_start);
    const prefersDark =
      typeof matchMedia === 'function' && matchMedia('(prefers-color-scheme: dark)').matches;
    applyTheme(resolveTheme(readStoredTheme(), prefersDark, theme, today));
    // Keyed on the values rather than the object: the session is rebuilt on every refresh, and
    // re-applying an identical theme on a fifteen-minute timer would repaint the page for no reason
    // while somebody is reading it.
  }, [restaurant, theme, schedule]);

  return null;
}
