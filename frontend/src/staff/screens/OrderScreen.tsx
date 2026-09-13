import { type ReactElement, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { formatDelta, formatINR } from '@shared/money';
import { Button } from '@shared/ui/button';
import { FoodTypeMark } from '@shared/ui/foodTypeMark';
import { Sheet, SheetContent, SheetFooter, SheetHeader, SheetTitle } from '@shared/ui/sheet';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { QuantityStepper } from '@staff/components/QuantityStepper';
import { QueryState } from '@staff/components/QueryState';
import { WaiterSurface } from '@staff/components/WaiterSurface';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import type { MenuVariant, ModifierGroup } from '@staff/api/menu';
import {
  type DishNames,
  type Order,
  type OrderLine,
  type OrderingItem,
  type OrderingMenu,
  dishNames,
  useAddLine,
  useChangeQuantity,
  useOrder,
  useOrderStep,
  useOrderingMenu,
  useRemoveLine,
} from '@staff/api/orders';

/**
 * Taking an order at the table: the screen a waiter holds in one hand.
 *
 * **A dish with nothing to choose is one tap.** One variant and no questions goes straight onto the
 * order; anything with a choice opens a sheet from the bottom, within thumb reach, that will not add
 * the dish until every required question is answered.
 *
 * **What the kitchen has seen is not deleted.** An unsent line comes off with one tap. A sent one asks
 * why first, and the reason is kept with the order — the server refuses a sent line without one.
 *
 * **The primary action is bottom-right**: Send to kitchen. Every figure on the screen is the server's
 * string, shown and never added up here (CLAUDE.md invariant 3).
 */
export default function OrderScreen(): ReactElement {
  const { orderId } = useParams<{ orderId: string }>();
  const order = useOrder(orderId);
  const menu = useOrderingMenu();
  return (
    <WaiterSurface>
      <QueryState
        isPending={order.isPending}
        error={order.error}
        pendingLabel={strings.orders.loadingOrder}
      >
        {order.data !== undefined && (
          <OrderTaking
            order={order.data}
            menu={menu.data}
            menuPending={menu.isPending}
            menuError={menu.error}
          />
        )}
      </QueryState>
    </WaiterSurface>
  );
}

type RemoveMutation = ReturnType<typeof useRemoveLine>;
type ChangeMutation = ReturnType<typeof useChangeQuantity>;
type SendMutation = ReturnType<typeof useOrderStep>;

const OFF_THE_BILL: ReadonlySet<string> = new Set(['cancelled', 'returned']);

// The server's limit on one line (`OrderLineAddRequest`); the stepper stops there rather than
// letting a tap earn a refusal.
const MAX_QUANTITY = 99;

function OrderTaking({
  order,
  menu,
  menuPending,
  menuError,
}: {
  order: Order;
  menu: OrderingMenu | undefined;
  menuPending: boolean;
  menuError: unknown;
}): ReactElement {
  const add = useAddLine();
  const remove = useRemoveLine();
  const change = useChangeQuantity();
  const send = useOrderStep('send');
  const [choosing, setChoosing] = useState<OrderingItem | null>(null);
  const names = useMemo(() => dishNames(menu), [menu]);
  const failure = add.error ?? remove.error ?? change.error ?? send.error;

  function pick(item: OrderingItem): void {
    const variants = item.variants.filter((variant) => variant.is_active);
    const only = variants[0];
    if (only !== undefined && variants.length === 1 && item.modifier_groups.length === 0) {
      add.mutate({ order, variantId: only.id, quantity: 1, modifierIds: [] });
      return;
    }
    setChoosing(item);
  }

  return (
    <div className="flex flex-col gap-4">
      <OrderHeader order={order} />
      {failure !== null && <Notice tone="critical" {...errorProps(failure)} />}
      <LineList order={order} names={names} remove={remove} change={change} />
      <QueryState
        isPending={menuPending}
        error={menuError}
        pendingLabel={strings.orders.loadingMenu}
      >
        <MenuPicker menu={menu} pending={add.isPending} onPick={pick} />
      </QueryState>
      <OptionsSheet
        item={choosing}
        pending={add.isPending}
        onClose={() => {
          setChoosing(null);
        }}
        onAdd={(variantId, modifierIds) => {
          add.mutate(
            { order, variantId, quantity: 1, modifierIds },
            {
              onSuccess: () => {
                setChoosing(null);
              },
            },
          );
        }}
      />
      <ActionBar order={order} send={send} />
    </div>
  );
}

function OrderHeader({ order }: { order: Order }): ReactElement {
  return (
    <div className="flex items-center justify-between gap-3">
      <Link to="/floor" className="min-h-target underline">
        {strings.orders.backToTables}
      </Link>
      <div className="text-right">
        <p className="font-semibold">{strings.orders.orderLabel(order.order_number)}</p>
        <p className="font-mono tabular-nums">{formatINR(order.grand_total)}</p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- lines

function LineList({
  order,
  names,
  remove,
  change,
}: {
  order: Order;
  names: DishNames;
  remove: RemoveMutation;
  change: ChangeMutation;
}): ReactElement {
  if (order.lines.length === 0) {
    return <p className="text-muted-foreground">{strings.orders.nothingYet}</p>;
  }
  return (
    <ul className="flex flex-col">
      {order.lines.map((line) => (
        <LineRow
          key={line.id}
          line={line}
          order={order}
          names={names}
          remove={remove}
          change={change}
        />
      ))}
    </ul>
  );
}

function LineRow({
  line,
  order,
  names,
  remove,
  change,
}: {
  line: OrderLine;
  order: Order;
  names: DishNames;
  remove: RemoveMutation;
  change: ChangeMutation;
}): ReactElement {
  // `null` until a sent line is being taken off; then the reason being typed.
  const [reason, setReason] = useState<string | null>(null);
  const off = OFF_THE_BILL.has(line.status);

  function takeOff(): void {
    if (line.status === 'pending') {
      remove.mutate({ order, lineId: line.id });
      return;
    }
    setReason('');
  }

  return (
    <li className="flex flex-col gap-2 border-b border-border py-3">
      <div className="flex items-start justify-between gap-3">
        <LineText line={line} names={names} off={off} />
        <div className="flex flex-col items-end gap-1">
          <span className="font-mono tabular-nums">{formatINR(line.line_total)}</span>
          {!off && reason === null && (
            <Button variant="ghost" disabled={remove.isPending} onClick={takeOff}>
              {strings.orders.takeOff}
            </Button>
          )}
        </div>
      </div>
      {/* Only an unsent dish changes count: once the kitchen has it, fewer is a reason, not a tap. */}
      {line.status === 'pending' && (
        <QuantityStepper
          value={line.quantity}
          min={1}
          max={MAX_QUANTITY}
          label={names.dishes.get(line.menu_item_variant_id) ?? ''}
          disabled={change.isPending}
          onChange={(quantity) => {
            change.mutate({ order, lineId: line.id, quantity });
          }}
        />
      )}
      {reason !== null && (
        <ReasonForm
          value={reason}
          pending={remove.isPending}
          onChange={setReason}
          onCancel={() => {
            setReason(null);
          }}
          onConfirm={() => {
            remove.mutate(
              { order, lineId: line.id, reason: reason.trim() },
              {
                onSuccess: () => {
                  setReason(null);
                },
              },
            );
          }}
        />
      )}
    </li>
  );
}

function LineText({
  line,
  names,
  off,
}: {
  line: OrderLine;
  names: DishNames;
  off: boolean;
}): ReactElement {
  const options = line.modifiers
    .map((chosen) => names.options.get(chosen.modifier_id) ?? '')
    .filter((name) => name !== '');
  const dish = names.dishes.get(line.menu_item_variant_id) ?? '';
  return (
    <div className={off ? 'text-muted-foreground line-through' : ''}>
      <p className="font-medium">{`${String(line.quantity)} × ${dish}`}</p>
      {options.length > 0 && <p className="text-sm text-muted-foreground">{options.join(', ')}</p>}
      <p className="text-sm">{strings.orders.lineStatuses[line.status] ?? line.status}</p>
    </div>
  );
}

function ReasonForm({
  value,
  pending,
  onChange,
  onCancel,
  onConfirm,
}: {
  value: string;
  pending: boolean;
  onChange: (value: string) => void;
  onCancel: () => void;
  onConfirm: () => void;
}): ReactElement {
  return (
    <div className="flex flex-col gap-2">
      <Field
        label={strings.orders.takeOffReason}
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      />
      <div className="flex justify-end gap-2">
        <Button variant="secondary" onClick={onCancel}>
          {strings.orders.keep}
        </Button>
        <Button
          variant="destructive"
          disabled={pending || value.trim().length < 3}
          onClick={onConfirm}
        >
          {strings.orders.confirmTakeOff}
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- the menu

function priceLabel(item: OrderingItem): string {
  const prices = item.variants
    .filter((variant) => variant.is_active)
    .map((variant) => variant.price);
  const first = prices[0];
  if (first === undefined) {
    return '';
  }
  return prices.length === 1 ? formatINR(first) : strings.orders.from(formatINR(first));
}

function MenuPicker({
  menu,
  pending,
  onPick,
}: {
  menu: OrderingMenu | undefined;
  pending: boolean;
  onPick: (item: OrderingItem) => void;
}): ReactElement {
  const categories = (menu?.categories ?? []).filter((category) => category.is_active);
  return (
    <div className="flex flex-col gap-4">
      {categories.map((category) => (
        <section key={category.id} className="flex flex-col gap-2">
          <h2 className="text-lg font-semibold">{category.name}</h2>
          <ul className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {category.items
              .filter((item) => item.is_active)
              .map((item) => (
                <li key={item.id}>
                  <button
                    type="button"
                    disabled={pending}
                    onClick={() => {
                      onPick(item);
                    }}
                    className="flex min-h-target w-full items-center justify-between gap-3 rounded-lg border border-border bg-card p-3 text-left disabled:opacity-60"
                  >
                    <span className="flex items-center gap-2">
                      <FoodTypeMark foodType={item.food_type} />
                      <span>{item.name}</span>
                    </span>
                    <span className="font-mono tabular-nums">{priceLabel(item)}</span>
                  </button>
                </li>
              ))}
          </ul>
        </section>
      ))}
    </div>
  );
}

function OptionsSheet({
  item,
  pending,
  onClose,
  onAdd,
}: {
  item: OrderingItem | null;
  pending: boolean;
  onClose: () => void;
  onAdd: (variantId: string, modifierIds: string[]) => void;
}): ReactElement {
  return (
    <Sheet
      open={item !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
    >
      <SheetContent side="bottom">
        {item !== null && <Choices key={item.id} item={item} pending={pending} onAdd={onAdd} />}
      </SheetContent>
    </Sheet>
  );
}

function countIn(group: ModifierGroup, chosen: readonly string[]): number {
  return group.modifiers.filter((modifier) => chosen.includes(modifier.id)).length;
}

/** The selection after tapping one option: a single-choice question swaps, a multi-choice one adds
 *  until its limit and then ignores the tap, and tapping a chosen option unchooses it. */
function nextChoice(
  group: ModifierGroup,
  current: readonly string[],
  modifierId: string,
): string[] {
  if (current.includes(modifierId)) {
    return current.filter((id) => id !== modifierId);
  }
  const inGroup = new Set(group.modifiers.map((modifier) => modifier.id));
  if (group.max_select === 1) {
    return [...current.filter((id) => !inGroup.has(id)), modifierId];
  }
  if (countIn(group, current) >= group.max_select) {
    return [...current];
  }
  return [...current, modifierId];
}

function Choices({
  item,
  pending,
  onAdd,
}: {
  item: OrderingItem;
  pending: boolean;
  onAdd: (variantId: string, modifierIds: string[]) => void;
}): ReactElement {
  const variants = item.variants.filter((variant) => variant.is_active);
  const groups = item.modifier_groups.filter((group) => group.is_active);
  const [variantId, setVariantId] = useState(variants[0]?.id ?? '');
  const [chosen, setChosen] = useState<string[]>([]);
  const ready =
    variantId !== '' && groups.every((group) => countIn(group, chosen) >= group.min_select);

  return (
    <div className="flex flex-col gap-4">
      <SheetHeader>
        <SheetTitle>{item.name}</SheetTitle>
      </SheetHeader>
      {variants.length > 1 && (
        <VariantChoice variants={variants} value={variantId} onChange={setVariantId} />
      )}
      {groups.map((group) => (
        <GroupChoice
          key={group.id}
          group={group}
          chosen={chosen}
          onToggle={(modifierId) => {
            setChosen((current) => nextChoice(group, current, modifierId));
          }}
        />
      ))}
      <SheetFooter>
        <Button
          size="lg"
          disabled={!ready || pending}
          onClick={() => {
            onAdd(variantId, chosen);
          }}
        >
          {pending ? strings.orders.adding : strings.orders.addToOrder}
        </Button>
      </SheetFooter>
    </div>
  );
}

function VariantChoice({
  variants,
  value,
  onChange,
}: {
  variants: MenuVariant[];
  value: string;
  onChange: (variantId: string) => void;
}): ReactElement {
  return (
    <div className="grid grid-cols-2 gap-2">
      {variants.map((variant) => {
        const selected = variant.id === value;
        return (
          <Button
            key={variant.id}
            variant={selected ? 'primary' : 'secondary'}
            aria-pressed={selected}
            onClick={() => {
              onChange(variant.id);
            }}
          >
            {`${selected ? '✓ ' : ''}${variant.name} · ${formatINR(variant.price)}`}
          </Button>
        );
      })}
    </div>
  );
}

function GroupChoice({
  group,
  chosen,
  onToggle,
}: {
  group: ModifierGroup;
  chosen: string[];
  onToggle: (modifierId: string) => void;
}): ReactElement {
  const rule =
    group.min_select > 0 ? strings.orders.required : strings.orders.upTo(group.max_select);
  return (
    <fieldset className="flex flex-col gap-2">
      <legend className="font-semibold">
        {group.name} <span className="text-sm font-normal text-muted-foreground">{rule}</span>
      </legend>
      <div className="grid grid-cols-2 gap-2">
        {group.modifiers
          .filter((modifier) => modifier.is_active)
          .map((modifier) => {
            const selected = chosen.includes(modifier.id);
            return (
              <Button
                key={modifier.id}
                variant={selected ? 'primary' : 'secondary'}
                aria-pressed={selected}
                onClick={() => {
                  onToggle(modifier.id);
                }}
              >
                {`${selected ? '✓ ' : ''}${modifier.name} ${formatDelta(modifier.price_delta)}`.trim()}
              </Button>
            );
          })}
      </div>
    </fieldset>
  );
}

// ---------------------------------------------------------------- actions

function ActionBar({ order, send }: { order: Order; send: SendMutation }): ReactElement {
  const unsent = order.lines.some((line) => line.status === 'pending');
  const billable = order.lines.some((line) => !OFF_THE_BILL.has(line.status));
  return (
    <div className="sticky bottom-0 flex items-center justify-between gap-3 border-t border-border bg-background py-3">
      {billable ? (
        <Button asChild variant="secondary" size="lg">
          <Link to={`/orders/${order.id}/bill`}>{strings.orders.bill}</Link>
        </Button>
      ) : (
        <span />
      )}
      <Button
        size="lg"
        disabled={!unsent || send.isPending}
        onClick={() => {
          send.mutate({ order });
        }}
      >
        {send.isPending ? strings.orders.sending : strings.orders.sendToKitchen}
      </Button>
    </div>
  );
}
