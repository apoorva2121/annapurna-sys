import { type ReactElement, useMemo, useState } from 'react';

import { Field } from '@staff/components/Field';
import { QueryState } from '@staff/components/QueryState';
import { useOrderingMenu } from '@staff/api/orders';
import { useModifierGroups } from '@staff/api/menu';
import { strings } from '@staff/strings';

/**
 * Every menu object and the code behind it. Read-only.
 *
 * **Why this page exists.** Codes used to be printed beside every name, so a browse list read
 * *"Veg Starters STARTER_VEG"* — the same thing twice, once for a person and once for the
 * database. The owner had them removed from the screens on 2026-09-19 and asked for this in the
 * same breath: *"u can give another page where the list of items and there respective codes are
 * there, so in case they are required later, people should be able to access it."*
 *
 * That was a better answer than the one suggested to them, which was to keep the code on each
 * dish's own page. A code is a database key; nobody choosing a starter needs to see one, and
 * somebody matching a recipe against `library/dishes.yaml` needs all of them at once.
 *
 * **Read-only is a safety property, not a shortcut.** A code is the join key `library/dishes.yaml`
 * and every M04 recipe use. A screen that let somebody edit one would detach a dish from its
 * recipe — the same failure the never-regenerate-on-rename rule in `codeFromName` exists to
 * prevent. There is deliberately no way to change anything from here.
 *
 * **It is the one screen where a code is information rather than noise**, which makes it the one
 * screen whose test asserts codes are *present*.
 */
export default function MenuCodesScreen(): ReactElement {
  const menu = useOrderingMenu();
  const groups = useModifierGroups();
  const [filter, setFilter] = useState('');

  const rows = useMemo(() => {
    const found: { kind: string; name: string; code: string; within: string | null }[] = [];
    for (const category of menu.data?.categories ?? []) {
      found.push({
        kind: strings.menu.codesKinds.category,
        name: category.name,
        code: category.code,
        within: null,
      });
      for (const item of category.items) {
        found.push({
          kind: strings.menu.codesKinds.dish,
          name: item.name,
          code: item.code,
          within: category.name,
        });
        for (const variant of item.variants) {
          found.push({
            kind: strings.menu.codesKinds.variant,
            name: variant.name,
            code: variant.code,
            within: item.name,
          });
        }
      }
    }
    for (const group of groups.data?.items ?? []) {
      found.push({
        kind: strings.menu.codesKinds.group,
        name: group.name,
        code: group.code,
        within: null,
      });
    }
    return found;
  }, [menu.data, groups.data]);

  // Matched against the code as well as the name: somebody arriving here has usually been handed
  // a code by a recipe file and wants to know which dish it is.
  const needle = filter.trim().toLowerCase();
  const shown =
    needle === ''
      ? rows
      : rows.filter(
          (row) =>
            row.name.toLowerCase().includes(needle) || row.code.toLowerCase().includes(needle),
        );

  return (
    <div className="max-w-3xl space-y-page">
      <div>
        <h1 className="text-2xl font-semibold">{strings.menu.codesTitle}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{strings.menu.codesIntro}</p>
      </div>

      <Field
        label={strings.menu.codesFilter}
        value={filter}
        onChange={(event) => {
          setFilter(event.target.value);
        }}
      />

      <QueryState
        isPending={menu.isPending || groups.isPending}
        error={menu.error ?? groups.error}
        pendingLabel={strings.menu.codesTitle}
      >
        {shown.length === 0 ? (
          <p className="text-muted-foreground">
            {rows.length === 0 ? strings.menu.codesEmpty : strings.menu.codesNoMatch}
          </p>
        ) : (
          // Its own scroller: a code column must not make the page scroll sideways on a phone.
          <div className="overflow-x-auto">
            <ul className="divide-y rounded-md border">
              {shown.map((row) => (
                <li
                  key={`${row.kind}-${row.code}-${row.name}`}
                  className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 p-3"
                >
                  <span className="flex flex-wrap items-baseline gap-x-2">
                    <span className="font-medium">{row.name}</span>
                    <span className="text-xs uppercase tracking-wide text-muted-foreground">
                      {row.kind}
                      {row.within === null ? '' : ` · ${row.within}`}
                    </span>
                  </span>
                  <span className="font-mono text-sm">{row.code}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </QueryState>
    </div>
  );
}
