import { type FormEvent, type ReactElement, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { parseAmount } from '@shared/money';
import { Button } from '@shared/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@shared/ui/select';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import { useCreateOrder, useSuppliers } from '@staff/api/procurement';
import { useStockItems } from '@staff/api/stock';

type Draft = { stockItemId: string; quantity: string; unitPrice: string };

const EMPTY: Draft = { stockItemId: '', quantity: '', unitPrice: '' };

/**
 * Raise an order. Saved as a draft, because sending it fixes the lines.
 *
 * **No total is shown and none is sent.** The server computes `total_amount` from the lines
 * (`docs/security.md` A04), and adding up `quantity × price` here to display it would be
 * arithmetic on money in the browser — the thing CLAUDE.md invariant 3 forbids. The total appears
 * on the order list, from the server, a moment later. A figure one second late and right beats one
 * that is instant and computed twice.
 *
 * **Quantities and prices are strings the whole way.** `parseAmount` validates and pads without a
 * `Number` in between; the M03/M04 review found two screens doing `Number(input).toFixed(2)`,
 * which is exactly the float round-trip the invariant is about, on the write path.
 */
export default function NewPurchaseOrderScreen(): ReactElement {
  const navigate = useNavigate();
  const create = useCreateOrder();
  const suppliers = useSuppliers(false);
  const items = useStockItems('ingredient');

  const [supplierId, setSupplierId] = useState('');
  const [expected, setExpected] = useState('');
  const [lines, setLines] = useState<Draft[]>([EMPTY]);
  const [problem, setProblem] = useState<string | null>(null);

  function update(index: number, patch: Partial<Draft>): void {
    setLines((current) =>
      current.map((line, at) => (at === index ? { ...line, ...patch } : line)),
    );
  }

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const validated = validate(supplierId, lines);
    if (typeof validated === 'string') {
      setProblem(validated);
      return;
    }
    setProblem(null);
    create.mutate(
      {
        supplier_id: supplierId,
        lines: validated,
        expected_at: expected === '' ? null : `${expected}T00:00:00Z`,
      },
      {
        onSuccess: () => {
          void navigate('/purchasing/orders');
        },
      },
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex max-w-2xl flex-col gap-4" noValidate>
      <h1 className="text-2xl font-semibold">{strings.procurement.newOrder}</h1>
      <p className="text-sm text-muted-foreground">{strings.procurement.ordersIntro}</p>

      {problem !== null && <Notice tone="critical" title={problem} />}
      {create.isError && <Notice tone="critical" {...errorProps(create.error)} />}

      <QueryState
        isPending={suppliers.isPending}
        error={suppliers.error}
        pendingLabel={strings.procurement.supplier}
      >
        <div className="flex flex-col gap-1 text-sm">
          <span>{strings.procurement.supplier}</span>
          <Select value={supplierId} onValueChange={setSupplierId}>
            <SelectTrigger aria-label={strings.procurement.supplier}>
              <SelectValue placeholder={strings.procurement.supplier} />
            </SelectTrigger>
            <SelectContent>
              {(suppliers.data?.suppliers ?? []).map((supplier) => (
                <SelectItem key={supplier.id} value={supplier.id}>
                  {supplier.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </QueryState>

      <Field
        label={strings.procurement.expectedAt}
        hint={strings.procurement.expectedAtHint}
        type="date"
        value={expected}
        onChange={(event) => {
          setExpected(event.target.value);
        }}
      />

      <QueryState
        isPending={items.isPending}
        error={items.error}
        pendingLabel={strings.procurement.item}
      >
        <div className="space-y-4">
          {lines.map((line, index) => (
            <OrderLineFields
              // The index is the identity here: these rows have no id until they are saved, and a
              // key derived from the item would collide the moment two rows are both still empty.
              key={index}
              line={line}
              options={items.data?.items ?? []}
              onChange={(patch) => {
                update(index, patch);
              }}
              onRemove={
                lines.length === 1
                  ? undefined
                  : () => {
                      setLines((current) => current.filter((_, at) => at !== index));
                    }
              }
            />
          ))}
        </div>
      </QueryState>

      <div className="flex gap-3">
        <Button
          type="button"
          variant="secondary"
          onClick={() => {
            setLines((current) => [...current, EMPTY]);
          }}
        >
          {strings.procurement.addLine}
        </Button>
        <Button type="submit" disabled={create.isPending}>
          {create.isPending ? strings.procurement.creating : strings.procurement.createOrder}
        </Button>
      </div>
    </form>
  );
}

function OrderLineFields({
  line,
  options,
  onChange,
  onRemove,
}: {
  line: Draft;
  options: { id: string; name: string; base_unit: string }[];
  onChange: (patch: Partial<Draft>) => void;
  onRemove: (() => void) | undefined;
}): ReactElement {
  return (
    <div className="grid gap-3 rounded border p-3 sm:grid-cols-3">
      <div className="flex flex-col gap-1 text-sm sm:col-span-3">
        <span>{strings.procurement.item}</span>
        <Select
          value={line.stockItemId}
          onValueChange={(value) => {
            onChange({ stockItemId: value });
          }}
        >
          <SelectTrigger aria-label={strings.procurement.item}>
            <SelectValue placeholder={strings.procurement.pickItem} />
          </SelectTrigger>
          <SelectContent>
            {options.map((item) => (
              <SelectItem key={item.id} value={item.id}>
                {item.name} ({item.base_unit})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <Field
        label={strings.procurement.quantityOrdered}
        value={line.quantity}
        inputMode="decimal"
        onChange={(event) => {
          onChange({ quantity: event.target.value });
        }}
      />
      <Field
        label={strings.procurement.unitPrice}
        value={line.unitPrice}
        inputMode="decimal"
        onChange={(event) => {
          onChange({ unitPrice: event.target.value });
        }}
      />
      {onRemove !== undefined && (
        <Button type="button" variant="ghost" onClick={onRemove}>
          {strings.procurement.removeLine}
        </Button>
      )}
    </div>
  );
}

/** Returns the request lines, or the sentence explaining why it cannot be sent.
 *
 * Split out of the component so it stays under the complexity limit and so it can be reasoned
 * about on its own: every branch here is a message a person reads, and there are five of them. */
function validate(
  supplierId: string,
  lines: Draft[],
): { stock_item_id: string; quantity_ordered: string; unit_price: string }[] | string {
  if (supplierId === '') {
    return strings.procurement.needsSupplier;
  }
  const filled = lines.filter((line) => line.stockItemId !== '');
  if (filled.length === 0) {
    return strings.procurement.needsLines;
  }
  if (new Set(filled.map((line) => line.stockItemId)).size !== filled.length) {
    return strings.procurement.duplicateItem;
  }
  const out: { stock_item_id: string; quantity_ordered: string; unit_price: string }[] = [];
  for (const line of filled) {
    // `parseAmount` rather than `Number(...)`: it refuses "1e3", "0x10" and " 12 " instead of
    // turning a typo into a price, and it pads without a float in the middle.
    const quantity = parseAmount(line.quantity);
    if (quantity === null || quantity === '0.00') {
      return strings.procurement.badQuantity;
    }
    const price = parseAmount(line.unitPrice);
    if (price === null) {
      return strings.procurement.badPrice;
    }
    out.push({
      stock_item_id: line.stockItemId,
      quantity_ordered: quantity,
      unit_price: price,
    });
  }
  return out;
}
