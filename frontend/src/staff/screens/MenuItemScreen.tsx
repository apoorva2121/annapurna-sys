import { type FormEvent, type ReactElement, useState } from 'react';
import { useParams } from 'react-router-dom';

import { formatDelta, formatINR } from '@shared/money';
import { Button } from '@shared/ui/button';
import { FoodTypeMark, type FoodType } from '@shared/ui/foodTypeMark';
import { Label } from '@shared/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@shared/ui/select';
import { Switch } from '@shared/ui/switch';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@shared/ui/table';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { useAuth } from '@staff/auth/AuthContext';
import { Permission } from '@shared/permissions';
import { strings } from '@staff/strings';
import {
  type MenuItem,
  type MenuVariant,
  type ModifierGroup,
  useAttachModifierGroups,
  useMenuItem,
  useModifierGroups,
  useUpdateItem,
  useUpdateVariant,
} from '@staff/api/menu';

/**
 * One dish: what it is, what it is sold as, and which questions are asked about it.
 *
 * **The price control is permission-conditional, not disabled.** `menu.price` is the owner's;
 * `seed/organization.yaml` withholds it from a manager by name, and the M03 threat table says why —
 * a quiet reprice on cash orders leaves no other trace. A manager sees the price and sees a
 * sentence explaining who can change it. A disabled input that 403s on submit would be worse than
 * either: it looks like a bug in the product rather than a boundary in the product.
 *
 * **`code` is shown and never editable.** It is how `library/dishes.yaml` and every recipe M04
 * attaches find this dish. The hint says so, because a read-only field with no explanation reads
 * as an oversight.
 */
export default function MenuItemScreen(): ReactElement {
  const { itemId } = useParams<{ itemId: string }>();
  const { can } = useAuth();
  const dishes = useMenuItem(itemId);
  const groups = useModifierGroups();
  const dish = dishes.data;

  return (
    <div className="max-w-3xl space-y-page">
      <QueryState
        isPending={dishes.isPending}
        error={dishes.error}
        pendingLabel={strings.menu.dishesTitle}
      >
        {dish === undefined ? (
          <p className="text-muted-foreground">{strings.menu.dishesEmpty}</p>
        ) : (
          <>
            <header className="flex flex-wrap items-center gap-3">
              <FoodTypeMark foodType={dish.food_type} />
              <h1 className="text-2xl font-semibold">{dish.name}</h1>
              <span className="font-mono text-sm text-muted-foreground">{dish.code}</span>
              {!dish.is_active && (
                <span className="rounded-sm bg-neutral-soft px-1.5 py-0.5 text-xs text-neutral">
                  {strings.menu.inactive}
                </span>
              )}
            </header>

            <DishDetails dish={dish} />
            <Variants dish={dish} mayPrice={can(Permission.MENU_PRICE)} />
            <AttachedGroups dish={dish} groups={groups.data?.items ?? []} />
          </>
        )}
      </QueryState>
    </div>
  );
}

function DishDetails({ dish }: { dish: MenuItem }): ReactElement {
  const update = useUpdateItem();
  const [name, setName] = useState(dish.name);
  const [description, setDescription] = useState(dish.description ?? '');
  const [foodType, setFoodType] = useState<FoodType>(dish.food_type);

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    update.mutate({
      id: dish.id,
      changes: { name: name.trim(), description: description.trim() || null, food_type: foodType },
    });
  }

  return (
    <form onSubmit={onSubmit} className="space-y-3 rounded-md border p-page">
      <Field
        label={strings.menu.dishName}
        value={name}
        onChange={(event) => {
          setName(event.target.value);
        }}
        required
      />
      <Field
        label={strings.menu.description}
        value={description}
        onChange={(event) => {
          setDescription(event.target.value);
        }}
      />
      <Field
        label={strings.menu.dishCode}
        hint={strings.menu.dishCodeHint}
        value={dish.code}
        readOnly
        onChange={() => {
          // Read-only by design: the code is a join key, not a label.
        }}
      />

      <div className="space-y-1">
        <Label htmlFor="food-type">{strings.menu.foodType}</Label>
        <Select
          value={foodType}
          onValueChange={(value) => {
            setFoodType(value as FoodType);
          }}
        >
          <SelectTrigger id="food-type">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="veg">{strings.menu.veg}</SelectItem>
            <SelectItem value="non_veg">{strings.menu.nonVeg}</SelectItem>
            <SelectItem value="egg">{strings.menu.egg}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {update.isError && <Notice tone="critical" {...errorProps(update.error)} />}
      <Button type="submit" disabled={update.isPending}>
        {update.isPending ? strings.menu.creating : strings.menu.save}
      </Button>
    </form>
  );
}

function Variants({ dish, mayPrice }: { dish: MenuItem; mayPrice: boolean }): ReactElement {
  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">{strings.menu.variantsTitle}</h2>
      {/* Said once, above the table, rather than repeated per row. A manager reads it and knows
          why there is no button; the owner never sees it. */}
      {!mayPrice && <Notice tone="info" title={strings.menu.priceLocked} />}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>{strings.menu.variantName}</TableHead>
            <TableHead className="text-right">{strings.menu.price}</TableHead>
            <TableHead className="text-right">{strings.menu.prepMinutes}</TableHead>
            {mayPrice && <TableHead />}
          </TableRow>
        </TableHeader>
        <TableBody>
          {dish.variants.map((variant) => (
            <VariantRow key={variant.id} variant={variant} mayPrice={mayPrice} />
          ))}
        </TableBody>
      </Table>
    </section>
  );
}

function VariantRow({
  variant,
  mayPrice,
}: {
  variant: MenuVariant;
  mayPrice: boolean;
}): ReactElement {
  const update = useUpdateVariant();
  const [editing, setEditing] = useState(false);
  const [price, setPrice] = useState(variant.price);

  function save(): void {
    // Guarded before sending. `Number("")` is 0, and a dish silently repriced to zero is the
    // unrecoverable version of this mistake — M02's tax screen shipped exactly that defect.
    const parsed = Number(price);
    if (!Number.isFinite(parsed) || parsed < 0 || price.trim() === '') {
      return;
    }
    update.mutate(
      { id: variant.id, changes: { price: parsed.toFixed(2) } },
      { onSuccess: () => { setEditing(false); } },
    );
  }

  return (
    <TableRow>
      <TableCell>
        {variant.name}
        <span className="ml-2 font-mono text-xs text-muted-foreground">{variant.code}</span>
        {!variant.is_active && (
          <span className="ml-2 rounded-sm bg-neutral-soft px-1.5 py-0.5 text-xs text-neutral">
            {strings.menu.inactive}
          </span>
        )}
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums">
        {editing ? (
          <Field
            label={strings.menu.price}
            type="number"
            min={0}
            step="0.01"
            value={price}
            onChange={(event) => {
              setPrice(event.target.value);
            }}
            required
          />
        ) : (
          formatINR(variant.price)
        )}
      </TableCell>
      <TableCell className="text-right font-mono tabular-nums">{variant.prep_minutes}</TableCell>
      {mayPrice && (
        <TableCell>
          {editing ? (
            <div className="flex gap-2">
              <Button onClick={save} disabled={update.isPending}>
                {strings.menu.save}
              </Button>
              <Button
                variant="secondary"
                onClick={() => {
                  setPrice(variant.price);
                  setEditing(false);
                }}
              >
                {strings.menu.cancel}
              </Button>
            </div>
          ) : (
            <Button
              variant="secondary"
              onClick={() => {
                setEditing(true);
              }}
            >
              {strings.menu.edit}
            </Button>
          )}
          {update.isError && <Notice tone="critical" {...errorProps(update.error)} />}
        </TableCell>
      )}
    </TableRow>
  );
}

function AttachedGroups({
  dish,
  groups,
}: {
  dish: MenuItem;
  groups: ModifierGroup[];
}): ReactElement {
  const attach = useAttachModifierGroups();
  // The dish list does not carry its attachments, so this starts from nothing selected and the
  // whole list is what gets sent. The endpoint is a PUT for the same reason: attachment is a set.
  const [selected, setSelected] = useState<string[]>([]);

  function toggle(groupId: string): void {
    setSelected((current) =>
      current.includes(groupId)
        ? current.filter((id) => id !== groupId)
        : [...current, groupId],
    );
  }

  return (
    <section className="space-y-3">
      <h2 className="text-lg font-semibold">{strings.menu.modifiersTitle}</h2>
      {groups.length === 0 ? (
        <p className="text-muted-foreground">{strings.menu.modifierGroupsEmpty}</p>
      ) : (
        <ul className="divide-y rounded-md border">
          {groups.map((group) => (
            <li key={group.id} className="flex flex-wrap items-center gap-2 p-2">
              <Switch
                id={`group-${group.id}`}
                checked={selected.includes(group.id)}
                onCheckedChange={() => {
                  toggle(group.id);
                }}
              />
              <Label htmlFor={`group-${group.id}`} className="flex-1">
                {group.name}
                <span className="ml-2 font-mono text-xs text-muted-foreground">{group.code}</span>
              </Label>
              <span className="text-sm text-muted-foreground">
                {group.modifiers
                  .map((modifier) => `${modifier.name} ${formatDelta(modifier.price_delta)}`.trim())
                  .join(', ')}
              </span>
            </li>
          ))}
        </ul>
      )}
      {attach.isError && <Notice tone="critical" {...errorProps(attach.error)} />}
      <Button
        disabled={attach.isPending}
        onClick={() => {
          attach.mutate({ itemId: dish.id, modifierGroupIds: selected });
        }}
      >
        {attach.isPending ? strings.menu.creating : strings.menu.save}
      </Button>
    </section>
  );
}
