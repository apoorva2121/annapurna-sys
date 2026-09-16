import { KotTicketStatus } from '@shared/enums';

/**
 * The pure parts of the kitchen rail, in their own module.
 *
 * Not a tidiness preference: a screen file that exports anything other than components loses fast
 * refresh, and `npm run lint` runs with `--max-warnings 0`, so the rule is enforced rather than
 * advised. `recipeLine.ts` is here for the same reason.
 */

/**
 * The one thing that happens next, so a chef never has to choose between four controls.
 *
 * `ready` returns null. That is the end of the kitchen's part — a dish is served when it reaches a
 * table, which a kitchen display cannot see, so the rail has no Served button at all (M08 spec
 * decision 5). The absence is the control, not an omission.
 */
export function nextStep(status: KotTicketStatus): KotTicketStatus | null {
  if (status === KotTicketStatus.NEW) {
    return KotTicketStatus.ACKNOWLEDGED;
  }
  if (status === KotTicketStatus.ACKNOWLEDGED) {
    return KotTicketStatus.PREPARING;
  }
  if (status === KotTicketStatus.PREPARING) {
    return KotTicketStatus.READY;
  }
  return null;
}

/**
 * How long this ticket has been on the rail, in whole minutes.
 *
 * Computed on the screen from `printed_at` rather than sent by the server: a server-sent "seven
 * minutes" is stale the instant it arrives and would need a refetch every second to stay true,
 * which is exactly the polling the stream exists to avoid.
 */
export function elapsedMinutes(printedAt: string, now: number): number {
  return Math.max(0, Math.floor((now - Date.parse(printedAt)) / 60000));
}
