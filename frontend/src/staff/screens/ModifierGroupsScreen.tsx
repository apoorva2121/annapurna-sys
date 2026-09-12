import { type FormEvent, type ReactElement, useState } from 'react';

import { formatDelta } from '@shared/money';
import { Button } from '@shared/ui/button';
import { Label } from '@shared/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@shared/ui/select';
import { Switch } from '@shared/ui/switch';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import {
  type ModifierGroup,
  useAddModifier,
  useBulkAttach,
  useCreateModifierGroup,
  useMenuCategories,
  useModifierGroups,
} from '@staff/api/menu';

/**
 * Option groups — "Choose spice level", "Add-ons" — and the bulk apply.
 *
 * **The bulk apply is the point of this screen.** The data model attaches options per dish, so a
 * single dish can opt out (one MAIN_VEG dish already has no onion, so Jain preference is
 * meaningless on it). But nobody describes a menu that way: an owner says "all main courses get a
 * spice level", and `seed/operations.yaml` writes it down exactly like that. This screen is where
 * the second becomes the first, expanded at the moment of applying rather than stored as a rule
 * that would then need reconciling against every exception forever.
 */
export default function ModifierGroupsScreen(): ReactElement {
  const groups = useModifierGroups();
  const items = groups.data?.items ?? [];

  return (
    <div className="max-w-3xl space-y-page">
      <h1 className="text-2xl font-semibold">{strings.menu.modifierGroupsTitle}</h1>

      <QueryState
        isPending={groups.isPending}
        error={groups.error}
        pendingLabel={strings.menu.modifierGroupsTitle}
      >
        {items.length === 0 ? (
          <p className="text-muted-foreground">{strings.menu.modifierGroupsEmpty}</p>
        ) : (
          <div className="space-y-4">
            {items.map((group) => (
              <GroupCard key={group.id} group={group} />
            ))}
          </div>
        )}
      </QueryState>

      <AddGroup />
      {items.length > 0 && <BulkApply groups={items} />}
    </div>
  );
}

function GroupCard({ group }: { group: ModifierGroup }): ReactElement {
  const add = useAddModifier();
  const [name, setName] = useState('');
  const [delta, setDelta] = useState('0');

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const parsed = Number(delta);
    if (!Number.isFinite(parsed) || delta.trim() === '') {
      return;
    }
    add.mutate(
      {
        groupId: group.id,
        body: {
          // Derived from the name, like the seeder does: a person typing "Mild" does not think in
          // codes, and the row still needs a stable key for M07's order lines to name.
          code: slug(name),
          name: name.trim(),
          price_delta: parsed.toFixed(2),
        },
      },
      {
        onSuccess: () => {
          setName('');
          setDelta('0');
        },
      },
    );
  }

  return (
    <section className="space-y-3 rounded-md border p-page">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <h2 className="text-lg font-semibold">{group.name}</h2>
          <p className="font-mono text-xs text-muted-foreground">{group.code}</p>
        </div>
        <p className="text-sm text-muted-foreground">
          {group.is_required ? strings.menu.required : ''} {strings.menu.minSelect}{' '}
          {group.min_select}, {strings.menu.maxSelect} {group.max_select}
        </p>
      </header>

      <ul className="divide-y rounded-md border">
        {group.modifiers.map((modifier) => (
          <li key={modifier.id} className="flex items-center justify-between gap-2 p-2">
            <span>{modifier.name}</span>
            {/* Blank at zero rather than "₹0.00": a free choice should read as a choice, not as a
                price of nothing. */}
            <span className="font-mono text-sm tabular-nums">
              {formatDelta(modifier.price_delta)}
            </span>
          </li>
        ))}
      </ul>

      <form onSubmit={onSubmit} className="flex flex-wrap items-end gap-2">
        <Field
          label={strings.menu.optionName}
          value={name}
          onChange={(event) => {
            setName(event.target.value);
          }}
          required
        />
        <Field
          label={strings.menu.priceDelta}
          hint={strings.menu.priceDeltaHint}
          type="number"
          step="0.01"
          value={delta}
          onChange={(event) => {
            setDelta(event.target.value);
          }}
          required
        />
        <Button type="submit" disabled={add.isPending || name.trim() === ''}>
          {add.isPending ? strings.menu.creating : strings.menu.addOption}
        </Button>
        {add.isError && (
          <div className="w-full">
            <Notice tone="critical" {...errorProps(add.error)} />
          </div>
        )}
      </form>
    </section>
  );
}

function AddGroup(): ReactElement {
  const create = useCreateModifierGroup();
  const [code, setCode] = useState('');
  const [name, setName] = useState('');
  const [min, setMin] = useState('0');
  const [max, setMax] = useState('1');
  const [required, setRequired] = useState(false);

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    create.mutate(
      {
        code: code.trim().toUpperCase(),
        name: name.trim(),
        min_select: Number(min),
        max_select: Number(max),
        is_required: required,
        modifiers: [],
      },
      {
        onSuccess: () => {
          setCode('');
          setName('');
        },
      },
    );
  }

  return (
    <form onSubmit={onSubmit} className="space-y-3 rounded-md border p-page">
      <h2 className="text-lg font-semibold">{strings.menu.addModifierGroup}</h2>
      <div className="flex flex-wrap items-end gap-2">
        <Field
          label={strings.menu.groupCode}
          hint={strings.menu.codeHint}
          value={code}
          onChange={(event) => {
            setCode(event.target.value);
          }}
          required
        />
        <Field
          label={strings.menu.groupName}
          value={name}
          onChange={(event) => {
            setName(event.target.value);
          }}
          required
        />
        <Field
          label={strings.menu.minSelect}
          type="number"
          min={0}
          value={min}
          onChange={(event) => {
            setMin(event.target.value);
          }}
          required
        />
        <Field
          label={strings.menu.maxSelect}
          type="number"
          min={1}
          value={max}
          onChange={(event) => {
            setMax(event.target.value);
          }}
          required
        />
      </div>
      <div className="flex items-center gap-2">
        <Switch id="group-required" checked={required} onCheckedChange={setRequired} />
        <Label htmlFor="group-required">{strings.menu.required}</Label>
      </div>
      {create.isError && <Notice tone="critical" {...errorProps(create.error)} />}
      <Button type="submit" disabled={create.isPending || code.trim() === '' || name.trim() === ''}>
        {create.isPending ? strings.menu.creating : strings.menu.addModifierGroup}
      </Button>
    </form>
  );
}

function BulkApply({ groups }: { groups: ModifierGroup[] }): ReactElement {
  const categories = useMenuCategories(false);
  const apply = useBulkAttach();
  const [categoryId, setCategoryId] = useState('');
  const [selected, setSelected] = useState<string[]>([]);
  const [replace, setReplace] = useState(false);

  return (
    <section className="space-y-3 rounded-md border p-page">
      <h2 className="text-lg font-semibold">{strings.menu.applyToCategory}</h2>
      <p className="text-sm text-muted-foreground">{strings.menu.applyToCategoryHint}</p>

      <div className="space-y-1">
        <Label htmlFor="bulk-category">{strings.menu.categoriesTitle}</Label>
        <Select value={categoryId} onValueChange={setCategoryId}>
          <SelectTrigger id="bulk-category">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(categories.data?.items ?? []).map((category) => (
              <SelectItem key={category.id} value={category.id}>
                {category.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <ul className="divide-y rounded-md border">
        {groups.map((group) => (
          <li key={group.id} className="flex items-center gap-2 p-2">
            <Switch
              id={`bulk-${group.id}`}
              checked={selected.includes(group.id)}
              onCheckedChange={() => {
                setSelected((current) =>
                  current.includes(group.id)
                    ? current.filter((id) => id !== group.id)
                    : [...current, group.id],
                );
              }}
            />
            <Label htmlFor={`bulk-${group.id}`}>{group.name}</Label>
          </li>
        ))}
      </ul>

      <div className="flex items-center gap-2">
        <Switch id="bulk-replace" checked={replace} onCheckedChange={setReplace} />
        <Label htmlFor="bulk-replace">{strings.menu.replaceExisting}</Label>
      </div>

      {apply.isError && <Notice tone="critical" {...errorProps(apply.error)} />}
      {apply.isSuccess && (
        <Notice tone="success" title={strings.menu.applied(apply.data.items_updated)} />
      )}
      <Button
        disabled={apply.isPending || categoryId === '' || selected.length === 0}
        onClick={() => {
          apply.mutate({ categoryId, modifierGroupIds: selected, replace });
        }}
      >
        {apply.isPending ? strings.menu.creating : strings.menu.apply}
      </Button>
    </section>
  );
}

/**
 * `"Jain (no onion/garlic)"` → `JAIN_NO_ONION_GARLIC`.
 *
 * Matches `app/seed/menu.py`'s rule, so a group created here and one seeded from YAML end up with
 * codes of the same shape. A regex replace rather than spreading the string into characters:
 * spreading yields code points and breaks rich characters, and the codes have to survive a dish
 * name written in any script.
 */
function slug(name: string): string {
  const collapsed = name
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '');
  return collapsed.slice(0, 32) || 'OPTION';
}
