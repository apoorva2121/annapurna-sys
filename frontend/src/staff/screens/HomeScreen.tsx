import type { ReactElement } from 'react';
import { Link } from 'react-router-dom';

import { useAuth } from '@staff/auth/AuthContext';
import { LicenceNotice } from '@staff/components/LicenceNotice';
import { Notice } from '@staff/components/Notice';
import { HOME_GROUPS, visibleGroups } from '@staff/navigation';
import { strings } from '@staff/strings';

/**
 * Where everyone lands after signing in.
 *
 * Acceptance criterion 1 is satisfied here: the page names the restaurant, so the owner can see at
 * a glance which tenant they are in — which is also the first thing that would look wrong if
 * tenant scoping were broken.
 *
 * A waiter and a chef land here too. Their own screens are M07 and M08; until then this page tells
 * them they are signed in and shows them no staff navigation, which is the correct M01 behaviour
 * rather than a placeholder.
 */
/**
 * The screens the header does not carry, grouped.
 *
 * **This used to be a second hand-written list, and it disagreed with the first.** Eight screens
 * were on this page *and* in the header — the owner's report of 2026-09-19: *"the options that are
 * present at the top they should not be repeated below … that is redundant"* — while ten more were
 * here and nowhere else. Both lists carried comments from somebody noticing a gap and patching one
 * side of it.
 *
 * It now renders `HOME_GROUPS` from `navigation.ts`, which is the same source the header reads.
 * The partition is in the data and `navigationDiscipline.test.ts` refuses a screen that appears in
 * both, or in neither.
 *
 * The ten that stay here stay by the owner's decision: they can reach them and did not want the
 * header carrying them.
 */
export default function HomeScreen(): ReactElement {
  const { session, can } = useAuth();
  if (session === null || session === undefined) {
    return <></>;
  }

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-2xl font-semibold">{session.restaurant.name}</h1>
        <p className="text-muted-foreground">{strings.home.greeting(session.fullName)}</p>
      </div>
      <LicenceNotice />

      {session.permissions.size === 0 ? (
        // Empty states explain what will appear and how (docs/ui/conventions.md). A waiter seeing
        // a blank page would reasonably conclude the app is broken.
        <Notice tone="info" title={strings.home.noPermissions} />
      ) : (
        <div className="flex flex-col gap-5">
          {visibleGroups(HOME_GROUPS, can).map((group) => (
            <section key={group.heading} className="flex flex-col gap-1">
              <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {group.heading}
              </h2>
              <ul className="flex flex-col">
                {group.entries.map((entry) => (
                  <li key={entry.to}>
                    {/* `text-brand`, not `text-info`. `tokens.css` names `--brand` as the link
                        colour — "fills: active nav, links, selected state" — and this page using
                        `info` while the header used nothing gave the product three link
                        appearances depending on which screen you were on. */}
                    <Link
                      className="inline-flex min-h-target items-center rounded-md px-2 text-brand underline underline-offset-4"
                      to={entry.to}
                    >
                      {entry.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}

      <p className="text-sm text-muted-foreground">{strings.home.m01Note}</p>
    </div>
  );
}
