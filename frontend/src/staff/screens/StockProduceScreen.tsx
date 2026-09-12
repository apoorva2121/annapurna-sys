import { type FormEvent, type ReactElement, useState } from 'react';

import { formatINR } from '@shared/money';
import { Button } from '@shared/ui/button';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { errorProps } from '@staff/components/errorProps';
import { QueryState } from '@staff/components/QueryState';
import { strings } from '@staff/strings';
import { useProduceBatch } from '@staff/api/inventory';
import { useStockItems } from '@staff/api/stock';

/**
 * Make a preparation batch. Consumes the recipe's inputs and creates the output, atomically.
 *
 * **The result says what the batch cost**, because that is the number the kitchen cannot get any
 * other way and the reason this screen is worth opening rather than writing it on a whiteboard.
 * The cost is what the ingredients *actually* cost — onions bought cheap last week make cheap
 * gravy today — and it is computed by the server from the batches consumed, not from any price on
 * this screen.
 *
 * **Producing without stock is allowed and says so.** A kitchen does not stop cooking because the
 * storeroom paperwork is behind (M05 spec decision 2). When inputs were short, the confirmation
 * says which quantity went unrecorded and what to do about it — it does not present the batch as
 * if nothing had happened, and it does not refuse the batch either.
 */
export default function StockProduceScreen(): ReactElement {
  const produce = useProduceBatch();
  const preparations = useStockItems('preparation');

  const [stockItemId, setStockItemId] = useState('');
  const [quantity, setQuantity] = useState('');

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    produce.mutate({ stock_item_id: stockItemId, quantity });
  }

  return (
    <form onSubmit={onSubmit} className="flex max-w-md flex-col gap-4" noValidate>
      <h1 className="text-2xl font-semibold">{strings.stockLedger.produceTitle}</h1>
      <p className="text-sm text-muted-foreground">{strings.stockLedger.produceIntro}</p>

      {produce.isError && <Notice tone="critical" {...errorProps(produce.error)} />}
      {produce.isSuccess && (
        <Notice
          tone="success"
          title={strings.stockLedger.made(
            produce.data.quantity_received,
            formatINR(produce.data.unit_cost),
          )}
        />
      )}

      <QueryState
        isPending={preparations.isPending}
        error={preparations.error}
        pendingLabel={strings.stockLedger.pickItem}
      >
        <label className="flex flex-col gap-1 text-sm">
          {strings.stockLedger.item}
          <select
            id="produce-item"
            value={stockItemId}
            onChange={(event) => {
              setStockItemId(event.target.value);
            }}
            required
            className="min-h-target rounded border border-input bg-background px-3"
          >
            <option value="">{strings.stockLedger.pickItem}</option>
            {(preparations.data?.items ?? []).map((item) => (
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

      <Button type="submit" disabled={produce.isPending}>
        {strings.stockLedger.make}
      </Button>
    </form>
  );
}
