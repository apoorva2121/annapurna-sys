import { type ReactElement, useState } from 'react';

import { applyTheme, readStoredTheme, storeTheme, THEMES } from '@shared/theme/theme';
import { strings } from '@staff/strings';

/**
 * Choose how the product looks, on this device.
 *
 * Per device rather than per restaurant: one person preferring dark on their own phone is not a
 * decision about the business, and it never reaches the server. The restaurant-wide default and
 * the festive schedule belong on M02's settings screen, where an owner sets them for everyone.
 *
 * Applying is immediate and total — the browser repaints custom properties, so there is nothing to
 * save and nothing to reload. That is worth seeing: it is the clearest evidence that the token
 * layer is real and that a theme is paint rather than code.
 */
export function ThemePicker(): ReactElement {
  const [current, setCurrent] = useState(() => readStoredTheme() ?? 'light');

  function choose(id: string): void {
    // applyTheme returns what was *actually* applied — an unreadable or unknown theme falls back,
    // and the selection has to show the truth rather than the request.
    const applied = applyTheme(id);
    storeTheme(applied);
    setCurrent(applied);
  }

  return (
    <section className="space-y-3">
      <div>
        <h2 className="text-lg font-semibold">{strings.profile.appearance}</h2>
        <p className="text-sm text-muted-foreground">{strings.profile.appearanceHint}</p>
      </div>

      <ul className="grid gap-2 sm:grid-cols-2">
        {THEMES.map((theme) => {
          const selected = theme.id === current;
          return (
            <li key={theme.id}>
              <button
                type="button"
                aria-pressed={selected}
                onClick={() => {
                  choose(theme.id);
                }}
                className={[
                  'flex min-h-target w-full flex-col items-start rounded-md border px-4 py-3 text-left transition-colors',
                  // Selected is a border *and* a tint *and* a word — never colour alone
                  // (docs/ui/conventions.md).
                  selected
                    ? 'border-brand bg-accent text-accent-foreground'
                    : 'border-border bg-card hover:bg-muted',
                ].join(' ')}
              >
                <span className="font-medium">
                  {theme.name}
                  {selected && ` · ${strings.profile.appearanceSelected}`}
                </span>
                <span className="text-sm text-muted-foreground">{theme.description}</span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
