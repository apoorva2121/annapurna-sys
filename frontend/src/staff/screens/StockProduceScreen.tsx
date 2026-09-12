import { type FormEvent, type ReactElement, useState } from 'react';

import { formatINR } from '@shared/money';
import { Button } from '@shared/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@shared/ui/select';
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
              {(preparations.data?.items ?? []).map((item) => (
                <SelectItem key={item.id} value={item.id}>
                  {item.name} ({item.base_unit})
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
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
