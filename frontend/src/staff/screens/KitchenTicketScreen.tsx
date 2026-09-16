import { type FormEvent, type ReactElement, useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { KotLineStatus } from '@shared/enums';
import { Button } from '@shared/ui/button';
import { Field } from '@staff/components/Field';
import { KdsSurface } from '@staff/components/KdsSurface';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import {
  type KotLine,
  type KotTicket,
  useAdvanceLine,
  useRequestRemake,
  useTicket,
} from '@staff/api/kitchen';

/**
 * One ticket, dish by dish: mark a single dish ready, or send one back to be remade.
 *
 * **A route rather than a modal**, which `docs/ui/conventions.md` requires for this surface: a chef
 * cannot dismiss a dialog with wet hands. It is reached by an id, so it carries a Back link (brand
 * guide §8.7) — the defect the owner reported was a screen they had to close a browser tab to
 * leave.
 *
 * **The remake reason is free text and required.** A dropdown of five options is how a kitchen
 * stops writing down why food comes back, and the reason is the entire value of recording a remake
 * at all.
 *
 * **Asking for a remake is not logging waste.** The dish may be going back to be reheated rather
 * than binned. M09 offers the link, and a person decides — a system that quietly booked waste on
 * the kitchen's behalf would teach people to stop remaking food (M08 spec decision 8).
 */
export default function KitchenTicketScreen(): ReactElement {
  const { ticketId = '' } = useParams();
  const ticket = useTicket(ticketId);

  return (
    <KdsSurface>
      <div className="flex flex-col gap-page p-page">
        <Button variant="secondary" asChild data-back>
          <Link to="/kitchen">{strings.kitchen.ticket.back}</Link>
        </Button>

        <QueryState
          isPending={ticket.isPending}
          error={ticket.error}
          pendingLabel={strings.kitchen.loading}
        >
          {ticket.data === undefined ? null : <Detail ticket={ticket.data} />}
        </QueryState>
      </div>
    </KdsSurface>
  );
}

function Detail({ ticket }: { ticket: KotTicket }): ReactElement {
  return (
    <article className="flex flex-col gap-page">
      <header className="flex flex-wrap items-baseline justify-between gap-3">
        <h1 className="text-[2.5rem] font-bold leading-none tabular-nums">
          {ticket.order_number}
        </h1>
        <p className="text-xl">
          {ticket.table_codes.length === 0
            ? strings.kitchen.takeaway
            : ticket.table_codes.join(', ')}
        </p>
      </header>

      <ul className="flex flex-col gap-page">
        {ticket.lines.map((line) => (
          <li key={line.id}>
            <Dish ticketId={ticket.id} line={line} />
          </li>
        ))}
      </ul>
    </article>
  );
}

function Dish({ ticketId, line }: { ticketId: string; line: KotLine }): ReactElement {
  const advance = useAdvanceLine();
  const [remaking, setRemaking] = useState(false);

  return (
    <section className="flex flex-col gap-3 rounded-lg border-4 border-border bg-card p-page">
      <h2 className="text-2xl font-semibold">
        {line.quantity} × {line.item_name} ({line.variant_name})
      </h2>
      {line.modifier_summary === null ? null : (
        <p className="text-xl text-warning">{line.modifier_summary}</p>
      )}
      {line.special_instructions === null ? null : (
        <p className="text-xl font-bold text-warning">{line.special_instructions}</p>
      )}
      {line.remake_reason === null ? null : (
        <p className="text-xl font-bold text-critical">
          {strings.kitchen.ticket.remade(line.remake_reason)}
        </p>
      )}

      <DishActions
        ticketId={ticketId}
        line={line}
        advance={advance}
        onToggleRemake={() => {
          setRemaking((open) => !open);
        }}
      />

      {advance.error === null ? null : (
        <Notice tone="critical" {...errorProps(advance.error)} />
      )}

      {remaking ? (
        <RemakeForm ticketId={ticketId} lineId={line.id} onDone={() => { setRemaking(false); }} />
      ) : null}
    </section>
  );
}

/**
 * The buttons for one dish. Split out of `Dish` because that function crossed the complexity
 * ceiling of 10 the Definition of Done sets, and because "what can be done to this dish" is a
 * genuinely separate question from "what does this dish say".
 */
function DishActions({
  ticketId,
  line,
  advance,
  onToggleRemake,
}: {
  ticketId: string;
  line: KotLine;
  advance: ReturnType<typeof useAdvanceLine>;
  onToggleRemake: () => void;
}): ReactElement {
  const finished = line.status === KotLineStatus.REMAKE || line.status === KotLineStatus.CANCELLED;
  const cooking = line.status === KotLineStatus.PENDING || line.status === KotLineStatus.PREPARING;

  return (
    <div className="flex flex-wrap gap-3">
      {line.status === KotLineStatus.PENDING ? (
        <Button
          onClick={() => {
            advance.mutate({ ticketId, lineId: line.id, status: KotLineStatus.PREPARING });
          }}
          disabled={advance.isPending}
        >
          {strings.kitchen.ticket.lineStart}
        </Button>
      ) : null}
      {cooking ? (
        <Button
          onClick={() => {
            advance.mutate({ ticketId, lineId: line.id, status: KotLineStatus.READY });
          }}
          disabled={advance.isPending}
        >
          {strings.kitchen.ticket.lineReady}
        </Button>
      ) : null}
      {finished ? null : (
        <Button variant="secondary" onClick={onToggleRemake}>
          {strings.kitchen.ticket.remakeTitle}
        </Button>
      )}
    </div>
  );
}

function RemakeForm({
  ticketId,
  lineId,
  onDone,
}: {
  ticketId: string;
  lineId: string;
  onDone: () => void;
}): ReactElement {
  const remake = useRequestRemake();
  const [reason, setReason] = useState('');

  const submit = (event: FormEvent): void => {
    event.preventDefault();
    remake.mutate({ ticketId, lineId, reason }, { onSuccess: onDone });
  };

  return (
    <form className="flex flex-col gap-3" onSubmit={submit}>
      <Field
        label={strings.kitchen.ticket.remakeReason}
        hint={strings.kitchen.ticket.remakeHint}
        value={reason}
        onChange={(event) => { setReason(event.target.value); }}
        maxLength={280}
      />
      <Button type="submit" disabled={reason.trim() === '' || remake.isPending}>
        {strings.kitchen.ticket.remakeSubmit}
      </Button>
      {remake.error === null ? null : (
        <Notice tone="critical" {...errorProps(remake.error)} />
      )}
    </form>
  );
}
