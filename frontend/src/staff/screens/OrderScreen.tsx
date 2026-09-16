import { type ReactElement, useMemo, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { formatDelta, formatINR } from '@shared/money';
import { Permission } from '@shared/permissions';
import { Button } from '@shared/ui/button';
import { FoodTypeMark } from '@shared/ui/foodTypeMark';
import { Sheet, SheetContent, SheetFooter, SheetHeader, SheetTitle } from '@shared/ui/sheet';
import { useAuth } from '@staff/auth/AuthContext';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { QuantityStepper } from '@staff/components/QuantityStepper';
import { QueryState } from '@staff/components/QueryState';
import { WaiterSurface } from '@staff/components/WaiterSurface';
import { errorProps, fieldErrors } from '@staff/components/errorProps';
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
  useCancelOrder,
  useChangeQuantity,
  useClaimOrder,
  useMoveOrder,
  useOrder,
  useOrderStep,
  useOrderingMenu,
  useRemoveLine,
  useWaiters,
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
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-3">
        <Link data-back to="/floor" className="min-h-target underline">
          {strings.orders.backToTables}
        </Link>
        <div className="text-right">
          <p className="font-semibold">{strings.orders.orderLabel(order.order_number)}</p>
          <p className="font-mono tabular-nums">{formatINR(order.grand_total)}</p>
        </div>
      </div>
      <WaiterLine order={order} />
    </div>
  );
}

const LIVE = new Set(['open', 'sent', 'served']);

/**
 * Who is serving this table (2026-09-14). The waiter was stored on every order and shown nowhere,
 * and it was whoever opened the order.
 *
 * **Assign to me** appears only on a dine-in order nobody is serving. Moving an order somebody is
 * serving is **Change waiter**, only for order.assign, because taking a busy table takes its credit.
 * A takeaway or delivery is a counter order: nobody serves it at a table.
 */
function WaiterLine({ order }: { order: Order }): ReactElement {
  const { can } = useAuth();
  const claim = useClaimOrder();
  if (order.type !== 'dine_in') {
    return <p className="text-sm text-muted-foreground">{strings.orders.counterOrder}</p>;
  }
  const live = LIVE.has(order.status);
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p>
          {order.waiter === null
            ? strings.orders.noWaiter
            : strings.orders.waiterLabel(order.waiter.full_name)}
        </p>
        <div className="flex flex-wrap gap-2">
          {live && order.waiter === null && can(Permission.ORDER_MODIFY) && (
            <Button
              variant="secondary"
              disabled={claim.isPending}
              onClick={() => {
                claim.mutate({ order });
              }}
            >
              {claim.isPending ? strings.orders.assigning : strings.orders.assignToMe}
            </Button>
          )}
          {live && can(Permission.ORDER_ASSIGN) && <MoveOrder order={order} />}
        </div>
      </div>
      {claim.isError && <Notice tone="critical" {...errorProps(claim.error)} />}
    </div>
  );
}

// The server's `Reason`: three characters at least, so the move waits for them.
const MOVE_REASON_MIN = 3;

/** Change waiter: choose who serves the table now, and say why. A sheet from the bottom, like every
 *  other question on this screen. The person already serving is not offered. */
function MoveOrder({ order }: { order: Order }): ReactElement {
  const [open, setOpen] = useState(false);
  const [chosen, setChosen] = useState<string | null>(null);
  const [reason, setReason] = useState('');
  const waiters = useWaiters(open);
  const move = useMoveOrder();
  const choices = (waiters.data?.items ?? []).filter((person) => person.id !== order.waiter?.id);
  const picked = choices.find((person) => person.id === chosen);
  const ready = picked !== undefined && reason.trim().length >= MOVE_REASON_MIN;
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <Button
        variant="secondary"
        onClick={() => {
          setOpen(true);
        }}
      >
        {strings.orders.changeWaiter}
      </Button>
      <SheetContent side="bottom">
        <SheetHeader>
          <SheetTitle>{strings.orders.moveTitle(order.order_number)}</SheetTitle>
        </SheetHeader>
        <div className="flex flex-col gap-3 py-3">
          {move.isError && <Notice tone="critical" {...errorProps(move.error)} />}
          <QueryState
            isPending={waiters.isPending}
            error={waiters.error}
            pendingLabel={strings.orders.loadingWaiters}
          >
            <fieldset className="flex flex-col gap-1">
              <legend className="sr-only">{strings.orders.moveChoose}</legend>
              {choices.map((person) => (
                <label key={person.id} className="flex min-h-target items-center gap-3">
                  <input
                    type="radio"
                    name="waiter"
                    value={person.id}
                    checked={chosen === person.id}
                    onChange={() => {
                      setChosen(person.id);
                    }}
                  />
                  {person.full_name}
                </label>
              ))}
            </fieldset>
          </QueryState>
          <Field
            label={strings.orders.moveReason}
            hint={strings.orders.moveReasonHint}
            value={reason}
            onChange={(event) => {
              setReason(event.target.value);
            }}
            error={fieldErrors(move.error).reason}
          />
        </div>
        <SheetFooter className="gap-2">
          <Button
            variant="secondary"
            size="lg"
            onClick={() => {
              setOpen(false);
            }}
          >
            {strings.orders.keepWaiter}
          </Button>
          <Button
            size="lg"
            disabled={!ready || move.isPending}
            onClick={() => {
              if (picked === undefined) return;
              move.mutate(
                { order, employeeId: picked.id, reason: reason.trim() },
                {
                  onSuccess: () => {
                    setOpen(false);
                    setChosen(null);
                    setReason('');
                  },
                },
              );
            }}
          >
            {picked === undefined
              ? strings.orders.moveChoose
              : strings.orders.moveTo(picked.full_name)}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
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
          {line.provisional === undefined ? (
            <span className="font-mono tabular-nums">{formatINR(line.line_total)}</span>
          ) : (
            // No price until the server has priced it (CLAUDE.md invariant 3, backlog-issues B11).
            <span className="text-sm text-muted-foreground">
              {line.provisional === 'adding' ? strings.orders.adding : strings.orders.saving}
            </span>
          )}
          {!off && reason === null && line.provisional === undefined && (
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
          disabled={change.isPending || line.provisional === 'adding'}
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
  const askForBill = useOrderStep('bill');
  const unsent = order.lines.some((line) => line.status === 'pending');
  const billable = order.lines.some((line) => !OFF_THE_BILL.has(line.status));
  return (
    <div className="sticky bottom-0 flex flex-col gap-2 border-t border-border bg-background py-3">
      {askForBill.isError && <Notice tone="critical" {...errorProps(askForBill.error)} />}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-2">
          <CancelOrder order={order} />
          {billable && order.bill_requested_at === null && (
            <Button
              variant="secondary"
              size="lg"
              disabled={askForBill.isPending}
              onClick={() => {
                askForBill.mutate({ order });
              }}
            >
              {strings.orders.askForBill}
            </Button>
          )}
          {billable && (
            <Button asChild variant="secondary" size="lg">
              <Link to={`/orders/${order.id}/bill`}>{strings.orders.bill}</Link>
            </Button>
          )}
        </div>
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
    </div>
  );
}

// The server's `Reason` (`schemas/orders.py`): three characters at least, so Confirm waits for them.
const CANCEL_REASON_MIN = 3;

/**
 * Cancelling an order that was never settled (backlog-issues B2), behind a confirmation.
 *
 * A sheet from the bottom, like every other question on this screen, because a centred dialog on a
 * phone covers the order it is asking about. It says how many dishes already went to the kitchen
 * before anyone confirms — a count, never a rupee figure added up here (CLAUDE.md invariant 3) —
 * and asks why, which the server keeps with the order.
 */
function CancelOrder({ order }: { order: Order }): ReactElement {
  const cancel = useCancelOrder();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState('');
  const sent = order.lines.filter(
    (line) => line.status !== 'pending' && !OFF_THE_BILL.has(line.status),
  ).length;
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <Button
        variant="secondary"
        size="lg"
        onClick={() => {
          setOpen(true);
        }}
      >
        {strings.orders.cancelOrder}
      </Button>
      <SheetContent side="bottom">
        <SheetHeader>
          <SheetTitle>{strings.orders.cancelTitle(order.order_number)}</SheetTitle>
        </SheetHeader>
        <div className="flex flex-col gap-3 py-3">
          <p>{sent === 0 ? strings.orders.cancelNothingSent : strings.orders.cancelSent(sent)}</p>
          {cancel.isError && <Notice tone="critical" {...errorProps(cancel.error)} />}
          <Field
            label={strings.orders.cancelReason}
            hint={strings.orders.cancelReasonHint}
            value={reason}
            onChange={(event) => {
              setReason(event.target.value);
            }}
            error={fieldErrors(cancel.error).reason}
          />
        </div>
        <SheetFooter className="gap-2">
          <Button
            variant="secondary"
            size="lg"
            onClick={() => {
              setOpen(false);
            }}
          >
            {strings.orders.keepOrder}
          </Button>
          <Button
            size="lg"
            disabled={reason.trim().length < CANCEL_REASON_MIN || cancel.isPending}
            onClick={() => {
              cancel.mutate(
                { order, reason: reason.trim() },
                {
                  onSuccess: () => {
                    setOpen(false);
                    void navigate('/floor');
                  },
                },
              );
            }}
          >
            {cancel.isPending ? strings.orders.cancelling : strings.orders.confirmCancel}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  );
}
