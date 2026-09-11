import { type ReactElement, useState } from 'react';

import { apiPost } from '@shared/api';
import { setAccessToken } from '@shared/api';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@shared/ui/select';
import { useAuth } from '@staff/auth/AuthContext';
import { strings } from '@staff/strings';

/**
 * Move to another branch of the same company (finding S12).
 *
 * Renders nothing at all for the overwhelming majority of staff, who work at one restaurant — a
 * switcher offering one option is a control that teaches people to ignore controls.
 *
 * **The server decides what is in this list.** `session.restaurants` comes from `/auth/me`, and
 * `POST /auth/switch` re-checks the choice regardless. Building the list client-side from anything
 * else would be a second implementation of a rule that is a tenant boundary.
 *
 * The switch returns a **new access token** scoped to the target, which is the part that actually
 * matters: every later request is authorised by the token, not by what the app believes. Permissions
 * are re-resolved there too — an owner at one branch who waits tables at another arrives as a
 * waiter, and the navigation changes to match on the reload below.
 */
export function BranchSwitcher(): ReactElement | null {
  const { session } = useAuth();
  const [switching, setSwitching] = useState(false);

  if (session == null || session.restaurants.length < 2) {
    return null;
  }

  function choose(restaurantId: string): void {
    setSwitching(true);
    void apiPost<{ access_token: string }>('/auth/switch', { restaurant_id: restaurantId })
      .then((result) => {
        setAccessToken(result.access_token);
        // A full reload rather than invalidating queries. Switching branch changes the tenant scope
        // of every cached answer on the page at once — the staff list, the floor, the tax rates —
        // and a partial refresh would leave one screen showing the other branch's data for as long
        // as it took to notice. Reloading is blunt, instant, and cannot be half-done.
        window.location.reload();
      })
      .catch(() => {
        // The server refused. Reloading would hide why, so the control simply becomes usable again
        // and the session stays where it is.
        setSwitching(false);
      });
  }

  return (
    <Select value={session.restaurant.id} onValueChange={choose} disabled={switching}>
      <SelectTrigger className="w-auto min-w-40" aria-label={strings.nav.branch}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {session.restaurants.map((restaurant) => (
          <SelectItem key={restaurant.id} value={restaurant.id}>
            {restaurant.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
