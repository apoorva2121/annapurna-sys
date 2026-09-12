import { type ReactElement, useState } from 'react';
import { Link } from 'react-router-dom';

import { formatINR } from '@shared/money';
import { Permission } from '@shared/permissions';
import { Button } from '@shared/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@shared/ui/table';
import { useAuth } from '@staff/auth/AuthContext';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import {
  type PurchaseOrder,
  useCancelOrder,
  usePurchaseOrders,
  useSendOrder,
  useSuppliers,
} from '@staff/api/procurement';

/**
 * What was ordered, and what is still open. The store manager's list screen.
 *
 * **Status is a word, never a colour alone** — `Part delivered` is the one that matters, because a
 * supplier delivering 30 of 50 sacks is the ordinary case and the 20 still owed is the number
 * somebody has to chase.
 *
 * **The receive button is gated on `stock.receive`, not on `purchase.manage`.** Posting a delivery
 * writes the stock ledger, so it keeps the ledger's permission — which means an accountant sees
 * their own orders here and no way to sign for them. That is the design's separation of duties,
 * not an oversight.
 */
export default function PurchaseOrdersScreen(): ReactElement {
  const { can } = useAuth();
  const orders = usePurchaseOrders();
  const suppliers = useSuppliers();

  const names = new Map((suppliers.data?.suppliers ?? []).map((s) => [s.id, s.name]));
  const rows = orders.data?.orders ?? [];

  return (
    <div className="space-y-page">
      <h1 className="text-2xl font-semibold">{strings.procurement.ordersTitle}</h1>
      <p className="text-sm text-muted-foreground">{strings.procurement.ordersIntro}</p>

      {can(Permission.PURCHASE_MANAGE) && (
        <Button asChild>
          <Link to="/purchasing/orders/new">{strings.procurement.newOrder}</Link>
        </Button>
      )}

      <QueryState
        isPending={orders.isPending}
        error={orders.error}
        pendingLabel={strings.procurement.ordersTitle}
      >
        {rows.length === 0 ? (
          <p className="text-muted-foreground">{strings.procurement.ordersEmpty}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{strings.procurement.orderNumber}</TableHead>
                <TableHead>{strings.procurement.supplier}</TableHead>
                <TableHead>{strings.procurement.status}</TableHead>
                <TableHead className="text-right">{strings.procurement.total}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((order) => (
                <OrderRow
                  key={order.id}
                  order={order}
                  supplierName={names.get(order.supplier_id) ?? ''}
                />
              ))}
            </TableBody>
          </Table>
        )}
      </QueryState>
    </div>
  );
}

function OrderRow({
  order,
  supplierName,
}: {
  order: PurchaseOrder;
  supplierName: string;
}): ReactElement {
  const { can } = useAuth();
  const [cancelling, setCancelling] = useState(false);

  return (
    <>
      <TableRow>
        <TableCell className="font-mono">{order.po_number}</TableCell>
        <TableCell>{supplierName}</TableCell>
        <TableCell>{strings.procurement.statuses[order.status] ?? order.status}</TableCell>
        <TableCell className="text-right font-mono">{formatINR(order.total_amount)}</TableCell>
        <TableCell className="space-x-3 text-right">
          <OrderActions
            order={order}
            onCancel={() => {
              setCancelling(true);
            }}
          />
          {order.status === 'received' && can(Permission.SUPPLIER_VIEW) && (
            <Link
              to={`/purchasing/suppliers/${order.supplier_id}/variance`}
              className="text-sm underline underline-offset-4"
            >
              {strings.procurement.variance}
            </Link>
          )}
        </TableCell>
      </TableRow>
      {cancelling && (
        <TableRow>
          <TableCell colSpan={5} className="bg-muted/40">
            <CancelForm
              order={order}
              onDone={() => {
                setCancelling(false);
              }}
            />
          </TableCell>
        </TableRow>
      )}
      {order.cancel_reason !== null && (
        <TableRow>
          <TableCell colSpan={5} className="text-sm text-muted-foreground">
            {order.cancel_reason}
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

function OrderActions({
  order,
  onCancel,
}: {
  order: PurchaseOrder;
  onCancel: () => void;
}): ReactElement {
  const { can } = useAuth();
  const mayPurchase = can(Permission.PURCHASE_MANAGE);
  // Open for delivery. `draft` is not: nothing can have arrived against an order nobody sent, and
  // the server refuses it with that sentence.
  const open = order.status === 'sent' || order.status === 'partial';
  // Cancellable until something has been delivered against it. After that the stock is on the
  // shelf, and a cancellation would leave it there unexplained.
  const cancellable = order.status === 'draft' || order.status === 'sent';

  return (
    <>
      {order.status === 'draft' && mayPurchase && <SendButton order={order} />}
      {/* Gated on the *ledger's* permission, because booking in a delivery writes stock. */}
      {open && can(Permission.STOCK_RECEIVE) && (
        <Link
          to={`/purchasing/orders/${order.id}/receive`}
          className="text-sm underline underline-offset-4"
        >
          {strings.procurement.receiveTitle}
        </Link>
      )}
      {cancellable && mayPurchase && <CancelButton onCancel={onCancel} />}
    </>
  );
}

/** Its own component so the mutation's pending and error states live beside the button that
 *  started them, rather than in a parent that renders four other things. */
function SendButton({ order }: { order: PurchaseOrder }): ReactElement {
  const send = useSendOrder();

  return (
    <>
      <button
        type="button"
        disabled={send.isPending}
        onClick={() => {
          send.mutate(order.id);
        }}
        className="text-sm underline underline-offset-4 disabled:opacity-60"
        title={strings.procurement.sentHint}
      >
        {send.isPending ? strings.procurement.sending : strings.procurement.sendOrder}
      </button>
      {send.isError && <Notice tone="critical" {...errorProps(send.error)} />}
    </>
  );
}

function CancelButton({ onCancel }: { onCancel: () => void }): ReactElement {
  return (
    <button type="button" onClick={onCancel} className="text-sm underline underline-offset-4">
      {strings.procurement.cancelOrder}
    </button>
  );
}

/** Cancelling always asks why, and the hint says where the answer goes.
 *
 * A cancellation nobody has to explain is exactly the one somebody would use to make an
 * over-order disappear, so the reason is mandatory on the server too and a CHECK constraint pairs
 * it with `cancelled_at`. */
function CancelForm({
  order,
  onDone,
}: {
  order: PurchaseOrder;
  onDone: () => void;
}): ReactElement {
  const cancel = useCancelOrder();
  const [reason, setReason] = useState('');

  return (
    <div className="flex max-w-md flex-col gap-3">
      {cancel.isError && <Notice tone="critical" {...errorProps(cancel.error)} />}
      <Field
        label={strings.procurement.cancelReason}
        hint={strings.procurement.cancelReasonHint}
        value={reason}
        onChange={(event) => {
          setReason(event.target.value);
        }}
      />
      <div className="flex gap-3">
        <Button
          variant="destructive"
          disabled={cancel.isPending || reason.trim() === ''}
          onClick={() => {
            cancel.mutate({ orderId: order.id, reason }, { onSuccess: onDone });
          }}
        >
          {cancel.isPending ? strings.procurement.cancelling : strings.procurement.confirmCancel}
        </Button>
        <Button variant="secondary" onClick={onDone}>
          {strings.procurement.cancel}
        </Button>
      </div>
    </div>
  );
}
