import { apiPost } from '@shared/api';

/**
 * Move this session to another branch of the same company, optionally landing somewhere specific.
 *
 * Extracted from `BranchSwitcher` when M19's branch comparison needed the same move with a
 * destination attached. One implementation, because two would be two chances to forget the reload
 * and leave half the page showing the other branch's data.
 *
 * **Why a full document load and not a router navigation.** Switching branch changes the tenant
 * scope of every cached answer on the page at once — the staff list, the floor, the tax rates. A
 * partial refresh leaves one screen showing the previous branch for as long as it takes somebody
 * to notice, and "for as long as it takes somebody to notice" is not a property to design a tenant
 * boundary around. Reloading is blunt, instant, and cannot be half-done.
 *
 * **Why the returned access token is deliberately dropped.** It would be discarded by the load
 * anyway — the token lives in a module variable, not in storage — and the app re-authenticates
 * from the refresh cookie, which now resolves to the new branch because the switch recorded it on
 * the session row. Keeping the token would *look* like it mattered and would hide the fact that
 * `user_session.restaurant_id` is what actually carries the choice.
 *
 * **`destination` is how a drill-through survives.** M19 criterion 6 asks that a figure open the
 * rows it came from, already filtered — and another branch's rows are not merely another screen,
 * they are outside this token's scope (invariant 1). Loading the destination URL *is* the reload,
 * so the filter arrives in the URL with the new scope already in force. No handoff through storage,
 * and therefore nothing that can go stale if the switch fails.
 */
export async function switchBranch(restaurantId: string, destination?: string): Promise<void> {
  await apiPost('/auth/switch', { restaurant_id: restaurantId });
  if (destination === undefined) {
    window.location.reload();
  } else {
    window.location.assign(destination);
  }
}
