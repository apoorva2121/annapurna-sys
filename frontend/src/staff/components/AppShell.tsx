import { type ReactElement, useState } from 'react';
import { Link, NavLink, Outlet } from 'react-router-dom';

import { Button } from '@shared/ui/button';
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@shared/ui/sheet';
import { useAuth } from '@staff/auth/AuthContext';
import { BranchSwitcher } from '@staff/components/BranchSwitcher';
import { RestaurantTheme } from '@staff/components/RestaurantTheme';
import { HEADER_GROUPS, SERVICE, type NavGroup, visibleGroups } from '@staff/navigation';
import { strings } from '@staff/strings';

/**
 * The frame every signed-in screen renders inside.
 *
 * The navigation is built from permissions, never from a role name (ADR 0007). A waiter therefore
 * sees no Staff link — not because the code checks for "waiter", but because they do not hold
 * `employee.view` (manual test C2). The server refuses the route regardless; this only avoids
 * showing a door that will not open.
 *
 * **The links are data now** (`navigation.ts`), not JSX scattered through this file. They were
 * split into `ServiceLinks`, `InsightLinks` and `EveryonesLinks`, and the comments on each split
 * said the same thing: eslint's complexity budget forced it. The grouping existed in the code and
 * was never shown on the screen.
 *
 * **What the owner saw, on a phone, 2026-09-19:** twenty-five unstyled links wrapping into what
 * reads as a paragraph — *"all the options look like its a paragraph and not the different
 * options."* Three defects underneath one complaint: no link styling at all (they inherited body
 * text), no touch target on any of them (the Sign out button in the same header had one), and
 * twenty-five of them in a row designed for a laptop.
 *
 * **So: the shift screens stay visible, everything else moves into a drawer, below `md` only.** At
 * laptop width there is room for a real nav, and hiding Reports behind a hamburger on a wide
 * screen is worse than the problem being solved. The shift screens survive the drawer because this
 * file's own argument says they must: *"a chef standing at the pass is already inside the app, and
 * going back to a landing page to reach the next screen is not how anybody works a shift"* — and
 * a hamburger is a landing page with fewer steps.
 */

/** The design gallery, linked only in a development build (backlog-issues B11b). */
function DesignGalleryLink(): ReactElement | null {
  if (!import.meta.env.DEV) {
    return null;
  }
  return (
    <NavLink to="/design" className={navLinkClass}>
      {strings.nav.design}
    </NavLink>
  );
}

/**
 * One link's classes, including the current-page state.
 *
 * **`--brand` is the link colour**, which `tokens.css` says in as many words: *"fills: active nav,
 * links, selected state"*. The header used none at all and the home page used `text-info`, so the
 * product had three link appearances depending on the screen.
 *
 * **The active state must not re-flow the layout** (design-system rule 10), so it is colour and a
 * background, never a bolder weight or a thicker border — a row that shifts under a thumb gets the
 * wrong tap. `aria-current="page"` comes from `NavLink` for the same state.
 */
function navLinkClass({ isActive }: { isActive: boolean }): string {
  return [
    'inline-flex min-h-target items-center rounded-md px-2 text-brand underline-offset-4',
    'hover:underline focus-visible:underline',
    isActive ? 'bg-accent text-accent-foreground no-underline' : '',
  ]
    .filter(Boolean)
    .join(' ');
}

function GroupLinks({ group }: { group: NavGroup }): ReactElement {
  return (
    <>
      {group.entries.map((entry) => (
        <NavLink key={entry.to} to={entry.to} className={navLinkClass}>
          {entry.label}
        </NavLink>
      ))}
    </>
  );
}

/**
 * The whole nav, grouped, for a screen wide enough to hold it.
 *
 * Hidden below `md` by CSS rather than unmounted, so the drawer is the only nav on a phone. Note
 * for anyone writing a test: **jsdom loads no stylesheet**, so `hidden` here is invisible to
 * `getAllByRole` and this nav is what the existing permission tests still see. A test for the
 * drawer has to open it.
 */
function WideNav(): ReactElement {
  const { can } = useAuth();
  const groups = visibleGroups(HEADER_GROUPS, can);
  return (
    <nav className="hidden flex-wrap items-center gap-x-1 gap-y-1 md:flex">
      {groups.map((group, index) => (
        <span key={group.heading} className="flex flex-wrap items-center gap-x-1">
          {/* A separator carries the grouping on a wide screen, where headings would be noise. */}
          {index === 0 ? null : (
            <span aria-hidden="true" className="px-1 text-muted-foreground">
              ·
            </span>
          )}
          <GroupLinks group={group} />
        </span>
      ))}
      <DesignGalleryLink />
    </nav>
  );
}

/**
 * A phone: the screens of the shift, then everything else behind one button.
 *
 * The trigger is not icon-only — the design system permits that only for an action done fifty
 * times a shift, and opening a menu is not one — so it is an icon and a word.
 */
function NarrowNav(): ReactElement {
  const { can } = useAuth();
  const [open, setOpen] = useState(false);
  const service = visibleGroups([SERVICE], can);
  const rest = visibleGroups(HEADER_GROUPS, can).filter(
    (group) => group.heading !== SERVICE.heading,
  );

  return (
    <div className="flex w-full flex-wrap items-center gap-x-1 gap-y-1 md:hidden">
      <nav className="flex flex-wrap items-center gap-x-1">
        {service.map((group) => (
          <GroupLinks key={group.heading} group={group} />
        ))}
      </nav>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetTrigger asChild>
          <Button variant="secondary" className="ml-auto">
            <span aria-hidden="true" className="mr-2">
              ☰
            </span>
            {strings.nav.more}
          </Button>
        </SheetTrigger>
        <SheetContent side="right" className="overflow-y-auto">
          <SheetHeader>
            <SheetTitle>{strings.nav.more}</SheetTitle>
          </SheetHeader>
          <div className="flex flex-col gap-4 pt-2">
            {rest.map((group) => (
              <section key={group.heading} className="flex flex-col gap-1">
                <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {group.heading}
                </h2>
                {/* Closing on navigation: a drawer still open over the screen somebody just asked
                    for is the commonest complaint about this pattern. */}
                <div
                  className="flex flex-col"
                  onClick={() => {
                    setOpen(false);
                  }}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      setOpen(false);
                    }
                  }}
                  role="presentation"
                >
                  <GroupLinks group={group} />
                </div>
              </section>
            ))}
            <DesignGalleryLink />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}

export function AppShell(): ReactElement {
  const { session, signOut } = useAuth();
  const [signingOut, setSigningOut] = useState(false);

  return (
    <div className="min-h-screen">
      {/* Applies the restaurant-wide and festive themes once the session is known. Renders nothing. */}
      <RestaurantTheme />
      <header className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-border p-page print:hidden">
        {/* The restaurant name is the tenant, on every screen. If tenant scoping ever broke, this
            is where it would be visible first. */}
        <Link to="/" className="font-semibold">
          {session?.restaurant.name ?? strings.appName}
        </Link>

        <WideNav />
        <NarrowNav />

        {/* Renders nothing for the great majority of staff, who work at one restaurant. */}
        <BranchSwitcher />
        <button
          type="button"
          className="ml-auto min-h-target underline disabled:opacity-60"
          disabled={signingOut}
          onClick={() => {
            setSigningOut(true);
            void signOut().finally(() => {
              setSigningOut(false);
            });
          }}
        >
          {signingOut ? strings.nav.signingOut : strings.nav.signOut}
        </button>
      </header>

      <main className="mx-auto max-w-3xl p-page">
        <Outlet />
      </main>
    </div>
  );
}
