import { type FormEvent, type ReactElement, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { ApiClientError } from '@shared/api';
import { Button } from '@shared/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@shared/ui/select';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { errorProps } from '@staff/components/errorProps';
import { QueryState } from '@staff/components/QueryState';
import { strings } from '@staff/strings';
import { useReceiveStock } from '@staff/api/inventory';
import { useStockItems } from '@staff/api/stock';
import { priceLabel, quantityLabel, typedIn } from '@staff/purchaseUnits';

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
  // What the boxes are labelled in, and whether the server must convert (backlog-issues B12e).
  const { unit, perPurchaseUnit } = typedIn(items.data?.items ?? [], stockItemId);
  const [quantity, setQuantity] = useState('');
  const [unitCost, setUnitCost] = useState('');
  const [expiryDate, setExpiryDate] = useState('');
  const [storage, setStorage] = useState('');

  // A delivery is sent twice at most: once as typed, and once more when the person has read the
  // sanity check and meant the price after all (backlog-issues B12e).
  function send(confirmPrice: boolean): void {
    receive.mutate(
      {
        stock_item_id: stockItemId,
        quantity,
        unit_cost: unitCost,
        expiry_date: expiryDate === '' ? null : expiryDate,
        storage_location: storage === '' ? null : storage,
        per_purchase_unit: perPurchaseUnit,
        // Only ever true on the second attempt, after the sentence below has been read.
        confirm_unusual_price: confirmPrice,
      },
      {
        onSuccess: () => {
          void navigate('/stock/on-hand');
        },
      },
    );
  }

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    send(false);
  }

  const unusualPrice =
    receive.error instanceof ApiClientError &&
    receive.error.code === 'stock_receipt.unusual_price';

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
        <div className="flex flex-col gap-1 text-sm">
          <span>{strings.stockLedger.item}</span>
          {/* Radix rather than a bare `<select>`: restaurant-ui rule 4, and the reason
              `shared/ui/select.tsx` exists — a hand-rolled select gets the appearance right and
              the keyboard wrong, and this one is aimed at with a glove on. */}
          <Select value={stockItemId} onValueChange={setStockItemId}>
            <SelectTrigger aria-label={strings.stockLedger.item}>
              <SelectValue placeholder={strings.stockLedger.pickItem} />
            </SelectTrigger>
            <SelectContent>
              {(items.data?.items ?? []).map((item) => (
                <SelectItem key={item.id} value={item.id}>
                  {item.name} ({item.base_unit})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </QueryState>

      <Field
        label={quantityLabel(unit)}
        value={quantity}
        onChange={(event) => {
          setQuantity(event.target.value);
        }}
        inputMode="decimal"
        required
      />
      <Field
        label={priceLabel(unit)}
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
      {/* The guard is a question, not a refusal: a price really can move that far, and the person
          at the gate is holding the invoice that says so. */}
      {unusualPrice && (
        <Button
          type="button"
          variant="secondary"
          disabled={receive.isPending}
          onClick={() => {
            send(true);
          }}
        >
          {strings.units.recordAnyway}
        </Button>
      )}
    </form>
  );
}
