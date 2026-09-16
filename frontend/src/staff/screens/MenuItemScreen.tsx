import { type FormEvent, type ReactElement, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { formatDelta, formatINR, parseAmount } from '@shared/money';
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
            <Link data-back to="/menu" className="text-info underline underline-offset-4">
              {strings.menu.backToMenu}
            </Link>
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

            {/* Said once, at the top, for someone who holds `menu.view` and nothing else —
                which is every waiter. Rendering the forms and letting the save 403 was the M03
                behaviour, and it reads as a broken product rather than as a boundary in one. */}
            {!can(Permission.MENU_MANAGE) && <Notice tone="info" title={strings.menu.readOnly} />}
            <DishDetails dish={dish} mayManage={can(Permission.MENU_MANAGE)} />
            <Variants dish={dish} mayPrice={can(Permission.MENU_PRICE)} />
            <AttachedGroups
              // Keyed, so moving between dishes rebuilds the tick list from the new dish rather
              // than carrying the previous dish's selection into a PUT.
              key={dish.id}
              dish={dish}
              groups={groups.data?.items ?? []}
              mayManage={can(Permission.MENU_MANAGE)}
            />
          </>
        )}
      </QueryState>
    </div>
  );
}

function DishDetails({ dish, mayManage }: { dish: MenuItem; mayManage: boolean }): ReactElement {
  const update = useUpdateItem();
  const [name, setName] = useState(dish.name);
  const [description, setDescription] = useState(dish.description ?? '');
  const [foodType, setFoodType] = useState<FoodType>(dish.food_type);
  const [allergens, setAllergens] = useState(dish.allergen_statement ?? '');
  const [calories, setCalories] = useState(
    dish.calories_kcal === null || dish.calories_kcal === undefined
      ? ''
      : String(dish.calories_kcal),
  );
  const [serving, setServing] = useState(dish.serving_size ?? '');
  const [problem, setProblem] = useState<string | null>(null);

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const kcal = calories.trim();
    if (kcal !== '' && !/^\d{1,5}$/.test(kcal)) {
      setProblem(strings.menu.caloriesProblem);
      return;
    }
    setProblem(null);
    update.mutate({
      id: dish.id,
      changes: {
        name: name.trim(),
        description: description.trim() || null,
        food_type: foodType,
        // Blank is "never asked", sent as null; a dish with none says so in words (B8).
        allergen_statement: allergens.trim() || null,
        calories_kcal: kcal === '' ? null : Number.parseInt(kcal, 10),
        serving_size: serving.trim() || null,
      },
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

      <Field
        label={strings.menu.allergens}
        hint={strings.menu.allergensHint}
        value={allergens}
        maxLength={500}
        onChange={(event) => {
          setAllergens(event.target.value);
        }}
      />
      <Field
        label={strings.menu.calories}
        hint={strings.menu.caloriesHint}
        inputMode="numeric"
        value={calories}
        onChange={(event) => {
          setCalories(event.target.value);
        }}
      />
      <Field
        label={strings.menu.servingSize}
        value={serving}
        maxLength={60}
        onChange={(event) => {
          setServing(event.target.value);
        }}
      />

      {problem !== null && <Notice tone="critical" title={problem} />}
      {update.isError && <Notice tone="critical" {...errorProps(update.error)} />}
      {mayManage && (
        <Button type="submit" disabled={update.isPending}>
          {update.isPending ? strings.menu.creating : strings.menu.save}
        </Button>
      )}
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
    // Guarded before sending, and parsed as a *string*. `Number("")` is 0, and a dish silently
    // repriced to zero is the unrecoverable version of this mistake — M02's tax screen shipped
    // exactly that defect. `parseAmount` also refuses `"1e3"` and `"0x10"`, which `Number` accepts.
    const amount = parseAmount(price);
    if (amount === null) {
      return;
    }
    update.mutate(
      { id: variant.id, changes: { price: amount } },
      {
        onSuccess: () => {
          setEditing(false);
        },
      },
    );
  }

  return (
    <TableRow>
      <TableCell>
        {/* The way into the recipe editor, from the thing a recipe is attached to. A chef arrives
            here from a dish and never from a recipe id, which is why the API grew a route that
            finds a recipe by its variant. */}
        <Link className="text-info underline" to={`/recipes/${variant.id}`}>
          {variant.name}
        </Link>
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
  mayManage,
}: {
  dish: MenuItem;
  groups: ModifierGroup[];
  mayManage: boolean;
}): ReactElement {
  const attach = useAttachModifierGroups();
  // **Seeded from what the dish already has.** The endpoint is a PUT because attachment is a set,
  // so the list sent is the list kept — and this started from nothing ticked, which meant saving
  // any change at all silently detached every group the dish had. It returned 200 and the options
  // simply vanished. Found by the M03/M04 review; the API now carries `modifier_group_ids` for
  // exactly this.
  const [selected, setSelected] = useState<string[]>(dish.modifier_group_ids ?? []);

  function toggle(groupId: string): void {
    setSelected((current) =>
      current.includes(groupId) ? current.filter((id) => id !== groupId) : [...current, groupId],
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
                disabled={!mayManage}
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
      {mayManage && (
        <Button
          disabled={attach.isPending}
          onClick={() => {
            attach.mutate({ itemId: dish.id, modifierGroupIds: selected });
          }}
        >
          {attach.isPending ? strings.menu.creating : strings.menu.saveOptions}
        </Button>
      )}
    </section>
  );
}
