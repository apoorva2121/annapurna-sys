import { type FormEvent, type ReactElement, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Button } from '@shared/ui/button';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { errorProps } from '@staff/components/errorProps';
import { QueryState } from '@staff/components/QueryState';
import { strings } from '@staff/strings';
import { useReceiveStock } from '@staff/api/inventory';
import { useStockItems } from '@staff/api/stock';

/**
 * Record a delivery. One primary action, and it is the most important write in the product.
 *
 * **Receipts are the anchor.** Every variance figure M13 will ever compute is
 * `opening + receipts − closing` against what the recipes say was used, so a delivery nobody
 * recorded does not merely go missing — it reappears weeks later as a position below zero that
 * somebody has to explain. The intro says that in a sentence, because the person typing this is
 * the person who decides whether it gets typed at all.
 *
 * **The expiry hint explains the consequence, not the field.** "Optional" alone tells somebody they
 * may skip it; saying that undated stock waits behind everything dated tells them what skipping it
 * *does*, which is what makes them fill it in for the paneer.
 *
 * Quantities and costs are held as **strings** all the way to the API. Nothing is parsed to a
 * number anywhere on this path (CLAUDE.md invariant 3).
 */
export default function StockReceiveScreen(): ReactElement {
  const navigate = useNavigate();
  const receive = useReceiveStock();
  const items = useStockItems('ingredient');

  const [stockItemId, setStockItemId] = useState('');
  const [quantity, setQuantity] = useState('');
  const [unitCost, setUnitCost] = useState('');
  const [expiryDate, setExpiryDate] = useState('');
  const [storage, setStorage] = useState('');

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    receive.mutate(
      {
        stock_item_id: stockItemId,
        quantity,
        unit_cost: unitCost,
        expiry_date: expiryDate === '' ? null : expiryDate,
        storage_location: storage === '' ? null : storage,
      },
      {
        onSuccess: () => {
          void navigate('/stock/on-hand');
        },
      },
    );
  }

  return (
    <form onSubmit={onSubmit} className="flex max-w-md flex-col gap-4" noValidate>
      <h1 className="text-2xl font-semibold">{strings.stockLedger.receiveTitle}</h1>
      <p className="text-sm text-muted-foreground">{strings.stockLedger.receiveIntro}</p>

      {receive.isError && (
        // `errorProps` carries the server's own sentence, which is more specific than ours;
        // spreading it last is what lets it win rather than be overwritten by a generic title.
        <Notice tone="critical" {...errorProps(receive.error)} />
      )}

      <QueryState
        isPending={items.isPending}
        error={items.error}
        pendingLabel={strings.stockLedger.pickItem}
      >
        <label className="flex flex-col gap-1 text-sm">
          {strings.stockLedger.item}
          <select
            id="receive-item"
            value={stockItemId}
            onChange={(event) => {
              setStockItemId(event.target.value);
            }}
            required
            className="min-h-target rounded border border-input bg-background px-3"
          >
            <option value="">{strings.stockLedger.pickItem}</option>
            {(items.data?.items ?? []).map((item) => (
              <option key={item.id} value={item.id}>
                {item.name} ({item.base_unit})
              </option>
            ))}
          </select>
        </label>
      </QueryState>

      <Field
        label={strings.stockLedger.quantityIn}
        value={quantity}
        onChange={(event) => {
          setQuantity(event.target.value);
        }}
        inputMode="decimal"
        required
      />
      <Field
        label={strings.stockLedger.unitCost}
        value={unitCost}
        onChange={(event) => {
          setUnitCost(event.target.value);
        }}
        inputMode="decimal"
        required
      />
      <Field
        label={strings.stockLedger.expiryDate}
        hint={strings.stockLedger.expiryHint}
        type="date"
        value={expiryDate}
        onChange={(event) => {
          setExpiryDate(event.target.value);
        }}
      />
      <Field
        label={strings.stockLedger.storage}
        value={storage}
        onChange={(event) => {
          setStorage(event.target.value);
        }}
      />

      <Button type="submit" disabled={receive.isPending}>
        {strings.stockLedger.record}
      </Button>
    </form>
  );
}
