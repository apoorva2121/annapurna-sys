import { type FormEvent, type ReactElement, useState } from 'react';
import { Link } from 'react-router-dom';

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
  type Supplier,
  type SupplierInput,
  useCreateSupplier,
  useSuppliers,
  useUpdateSupplier,
} from '@staff/api/procurement';

/**
 * Who the restaurant buys from. Manager and store surface, so a table rather than cards.
 *
 * **One row per business, and the hint says why.** Two spellings of "Sharma Traders" are two rows
 * whose deliveries cannot be summed, and a variance report split across both understates the leak
 * by exactly the amount that would have made somebody pick up the phone. The server refuses the
 * duplicate; this explains the refusal before it happens.
 *
 * **Nothing is deleted.** A supplier is retired with `is_active`, because every historical receipt
 * points at this row for ever and last quarter still has to add up. The button says "stop using"
 * rather than "delete" for that reason.
 *
 * **Each row links to its delivery record**, which is the module's actual product. A supplier list
 * that did not lead anywhere would be an address book.
 */
export default function SuppliersScreen(): ReactElement {
  const { can } = useAuth();
  const suppliers = useSuppliers();
  const [editing, setEditing] = useState<Supplier | 'new' | null>(null);
  const mayManage = can(Permission.SUPPLIER_MANAGE);

  const rows = suppliers.data?.suppliers ?? [];

  return (
    <div className="space-y-page">
      <h1 className="text-2xl font-semibold">{strings.procurement.suppliersTitle}</h1>
      <p className="text-sm text-muted-foreground">{strings.procurement.suppliersIntro}</p>

      {mayManage && editing === null && (
        <Button
          onClick={() => {
            setEditing('new');
          }}
        >
          {strings.procurement.addSupplier}
        </Button>
      )}

      {editing !== null && (
        <SupplierForm
          supplier={editing === 'new' ? null : editing}
          onDone={() => {
            setEditing(null);
          }}
        />
      )}

      <QueryState
        isPending={suppliers.isPending}
        error={suppliers.error}
        pendingLabel={strings.procurement.suppliersTitle}
      >
        {rows.length === 0 ? (
          <p className="text-muted-foreground">{strings.procurement.suppliersEmpty}</p>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{strings.procurement.supplierName}</TableHead>
                <TableHead>{strings.procurement.contactPerson}</TableHead>
                <TableHead className="text-right">{strings.procurement.paymentTerms}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((supplier) => (
                <SupplierRow
                  key={supplier.id}
                  supplier={supplier}
                  mayManage={mayManage}
                  onEdit={() => {
                    setEditing(supplier);
                  }}
                />
              ))}
            </TableBody>
          </Table>
        )}
      </QueryState>
    </div>
  );
}

function SupplierRow({
  supplier,
  mayManage,
  onEdit,
}: {
  supplier: Supplier;
  mayManage: boolean;
  onEdit: () => void;
}): ReactElement {
  const update = useUpdateSupplier();

  return (
    <TableRow>
      <TableCell>
        <span className="font-medium">{supplier.name}</span>
        {!supplier.is_active && (
          // The word, not only a faded row. Colour never carries meaning alone.
          <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-xs text-muted-foreground">
            {strings.procurement.inactive}
          </span>
        )}
      </TableCell>
      <TableCell className="text-muted-foreground">{supplier.contact_person ?? ''}</TableCell>
      <TableCell className="text-right font-mono">
        {supplier.payment_terms_days === null ? '' : supplier.payment_terms_days}
      </TableCell>
      <TableCell className="space-x-3 text-right">
        <Link
          to={`/purchasing/suppliers/${supplier.id}/variance`}
          className="text-sm underline underline-offset-4"
        >
          {strings.procurement.variance}
        </Link>
        {mayManage && (
          <>
            <button type="button" onClick={onEdit} className="text-sm underline underline-offset-4">
              {strings.procurement.editSupplier}
            </button>
            <button
              type="button"
              disabled={update.isPending}
              onClick={() => {
                update.mutate({
                  supplierId: supplier.id,
                  changes: { is_active: !supplier.is_active },
                });
              }}
              className="text-sm underline underline-offset-4 disabled:opacity-60"
            >
              {supplier.is_active
                ? strings.procurement.deactivate
                : strings.procurement.reactivate}
            </button>
          </>
        )}
      </TableCell>
    </TableRow>
  );
}

type Draft = {
  name: string;
  contact: string;
  phone: string;
  gstin: string;
  terms: string;
};

/** A nullable column as an input's value. One helper rather than a `??` per field, which is five
 *  branches in a function that makes no decisions. */
function text(value: string | number | null | undefined): string {
  return value === null || value === undefined ? '' : String(value);
}

/** The form's initial state, extracted so `SupplierForm` stays under the complexity limit.
 *
 * Every field is a string even where the column is an integer: an input's value is a string, and
 * converting on the way in and out twice is how an empty box becomes `NaN`. */
function draftOf(supplier: Supplier | null): Draft {
  return {
    name: text(supplier?.name),
    contact: text(supplier?.contact_person),
    phone: text(supplier?.phone),
    gstin: text(supplier?.gstin),
    terms: text(supplier?.payment_terms_days),
  };
}

/** What gets sent. Empty strings become `null` so a cleared box clears the column rather than
 *  storing "". */
function bodyOf(draft: Draft): SupplierInput {
  return {
    name: draft.name,
    contact_person: draft.contact === '' ? null : draft.contact,
    phone: draft.phone === '' ? null : draft.phone,
    gstin: draft.gstin === '' ? null : draft.gstin,
    // Days, an integer count rather than an amount — the one number on this screen that is
    // genuinely a number and not money.
    payment_terms_days: draft.terms === '' ? null : Number(draft.terms),
  };
}

/** Add or edit. One form for both, because the fields are identical and two would drift. */
function SupplierForm({
  supplier,
  onDone,
}: {
  supplier: Supplier | null;
  onDone: () => void;
}): ReactElement {
  const create = useCreateSupplier();
  const update = useUpdateSupplier();
  const [draft, setDraft] = useState(() => draftOf(supplier));
  const pending = create.isPending || update.isPending;
  const failure = create.error ?? update.error;

  function set(patch: Partial<Draft>): void {
    setDraft((current) => ({ ...current, ...patch }));
  }

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    const body = bodyOf(draft);
    if (supplier === null) {
      create.mutate(body, { onSuccess: onDone });
    } else {
      update.mutate({ supplierId: supplier.id, changes: body }, { onSuccess: onDone });
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex max-w-md flex-col gap-4 rounded border p-4" noValidate>
      {failure !== null && <Notice tone="critical" {...errorProps(failure)} />}
      <Field
        label={strings.procurement.supplierName}
        hint={strings.procurement.supplierNameHint}
        value={draft.name}
        onChange={(event) => {
          set({ name: event.target.value });
        }}
        required
      />
      <Field
        label={strings.procurement.contactPerson}
        value={draft.contact}
        onChange={(event) => {
          set({ contact: event.target.value });
        }}
      />
      <Field
        label={strings.procurement.phone}
        value={draft.phone}
        inputMode="tel"
        onChange={(event) => {
          set({ phone: event.target.value });
        }}
      />
      <Field
        label={strings.procurement.gstin}
        hint={strings.procurement.gstinHint}
        value={draft.gstin}
        onChange={(event) => {
          set({ gstin: event.target.value.toUpperCase() });
        }}
      />
      <Field
        label={strings.procurement.paymentTerms}
        value={draft.terms}
        inputMode="numeric"
        onChange={(event) => {
          set({ terms: event.target.value });
        }}
      />
      <div className="flex gap-3">
        <Button type="submit" disabled={pending}>
          {pending ? strings.procurement.saving : strings.procurement.save}
        </Button>
        <Button type="button" variant="secondary" onClick={onDone}>
          {strings.procurement.cancel}
        </Button>
      </div>
    </form>
  );
}
