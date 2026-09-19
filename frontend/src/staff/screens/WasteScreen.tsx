import { type ReactElement, type ReactNode, useState } from 'react';

import { formatINR } from '@shared/money';
import { Button } from '@shared/ui/button';
import { useIdempotencyKey } from '@shared/useIdempotencyKey';
import { AttachmentControl } from '@staff/components/AttachmentControl';
import { Notice } from '@staff/components/Notice';
import { QueryState } from '@staff/components/QueryState';
import { WaiterSurface } from '@staff/components/WaiterSurface';
import { errorProps } from '@staff/components/errorProps';
import { strings } from '@staff/strings';
import {
  type WastageEvent,
  type WastageReason,
  useLogWastage,
  useWastageReasons,
} from '@staff/api/waste';
import { type StockItem, useStockItems } from '@staff/api/stock';
import { PRESETS, isPerPurchaseUnit, presetLabel, unitFor } from '@staff/screens/wastePresets';

/**
 * Log waste in under ten seconds: item → quantity → reason → done.
 *
 * **The ten seconds is the module.** `docs/waste-model.md` is blunt about it — "if logging waste is
 * slow, it doesn't get logged, and the whole module is fiction" — so every decision on this screen
 * serves that and nothing else.
 *
 * **No cost appears anywhere before Log is pressed.** Same rule as the blind cash count in M07 and
 * the blind goods-receipt weight in M06: a figure shown while somebody is deciding what to record
 * is a figure some people record towards. The rupee value arrives *after*, because then it teaches
 * — a cook who learns the tray they binned was ₹340 bins less next week.
 *
 * **Preset buttons, not a number pad.** ¼, ½, 1, 2 of whatever the item is bought in. Typing a
 * quantity one-handed in a kitchen is slow and is where a decimal point goes missing; the presets
 * are also why the screen never converts a unit — it sends what was tapped and the flag that says
 * what it means, and the server does the arithmetic (backlog-issues B12e).
 *
 * **Waiter surface**: 48 px targets, one hand, a person standing at a bin.
 */
export default function WasteScreen(): ReactElement {
  const items = useStockItems('ingredient');
  const reasons = useWastageReasons();

  return (
    <WaiterSurface>
      <div className="flex flex-col gap-page p-page">
        <h1 className="text-2xl font-semibold">{strings.waste.title}</h1>
        <QueryState
          isPending={items.isPending || reasons.isPending}
          error={items.error ?? reasons.error}
          pendingLabel={strings.waste.loading}
        >
          <LogForm
            items={items.data?.items ?? []}
            reasons={(reasons.data?.items ?? []).filter((reason) => reason.is_active)}
          />
        </QueryState>
      </div>
    </WaiterSurface>
  );
}

function LogForm({
  items,
  reasons,
}: {
  items: StockItem[];
  reasons: WastageReason[];
}): ReactElement {
  const [itemId, setItemId] = useState<string | null>(null);
  const [quantity, setQuantity] = useState<string | null>(null);
  const [logged, setLogged] = useState<WastageEvent | null>(null);
  // Which reason it was logged against, so the photo nudge knows whether to ask. The event does
  // not carry the flag and should not: `requires_photo` is policy on the reason, not a fact about
  // the waste.
  const [loggedReason, setLoggedReason] = useState<WastageReason | null>(null);
  const log = useLogWastage();
  const { key, renew } = useIdempotencyKey();

  const item = items.find((candidate) => candidate.id === itemId) ?? null;

  const submit = (reason: WastageReason): void => {
    if (item === null || quantity === null) {
      return;
    }
    log.mutate(
      {
        stockItemId: item.id,
        wastageReasonId: reason.id,
        quantity,
        // The screen does no arithmetic. It says which unit the number is in and the server
        // converts — the rule that exists because a delivery typed against the wrong unit once
        // repriced cabbage to ₹40 a gram.
        perPurchaseUnit: isPerPurchaseUnit(item),
        idempotencyKey: key,
      },
      {
        onSuccess: (event) => {
          setLogged(event);
          setLoggedReason(reason);
          setItemId(null);
          setQuantity(null);
          renew();
        },
      },
    );
  };

  if (logged !== null) {
    return (
      <Logged
        event={logged}
        wantsPhoto={loggedReason?.requires_photo ?? false}
        onAgain={() => {
          setLogged(null);
          setLoggedReason(null);
        }}
      />
    );
  }

  return (
    <div className="flex flex-col gap-page">
      <Step number={1} label={strings.waste.pickItem}>
        <div className="flex flex-wrap gap-2">
          {items.map((candidate) => (
            <Button
              key={candidate.id}
              variant={itemId === candidate.id ? 'primary' : 'secondary'}
              onClick={() => {
                setItemId(candidate.id);
                setQuantity(null);
              }}
            >
              {candidate.name}
            </Button>
          ))}
        </div>
      </Step>

      {item === null ? null : (
        <Step number={2} label={strings.waste.howMuch(unitFor(item))}>
          <div className="flex flex-wrap gap-2">
            {PRESETS.map((preset) => (
              <Button
                key={preset}
                variant={quantity === preset ? 'primary' : 'secondary'}
                onClick={() => { setQuantity(preset); }}
              >
                {presetLabel(preset, unitFor(item))}
              </Button>
            ))}
          </div>
        </Step>
      )}

      {item === null || quantity === null ? null : (
        <Step number={3} label={strings.waste.why}>
          {/* Grouped by stage, because a reason's stage is what the whole report turns on and a
              person picking at speed should find them in the same place every time. */}
          {(['receiving', 'storage', 'prep', 'service'] as const).map((stage) => {
            const forStage = reasons.filter((reason) => reason.stage === stage);
            if (forStage.length === 0) {
              return null;
            }
            return (
              <div key={stage} className="flex flex-col gap-2">
                <h3 className="text-sm font-medium text-muted-foreground">
                  {strings.waste.stage[stage]}
                </h3>
                <div className="flex flex-wrap gap-2">
                  {forStage.map((reason) => (
                    <Button
                      key={reason.id}
                      variant="secondary"
                      onClick={() => { submit(reason); }}
                      disabled={log.isPending}
                    >
                      {reason.name}
                    </Button>
                  ))}
                </div>
              </div>
            );
          })}
        </Step>
      )}

      {log.error === null ? null : <Notice tone="critical" {...errorProps(log.error)} />}
    </div>
  );
}

function Step({
  number,
  label,
  children,
}: {
  number: number;
  label: string;
  children: ReactNode;
}): ReactElement {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-lg font-medium">
        {number}. {label}
      </h2>
      {children}
    </section>
  );
}

/**
 * What it cost, shown only now.
 *
 * This is the teaching half of `docs/waste-model.md`'s rule, and the reason the figure is large
 * rather than a footnote. It is also why there is no undo: the waste happened, and a screen that
 * offered to unmake the record would be offering to unmake the number.
 */
function Logged({
  event,
  wantsPhoto,
  onAgain,
}: {
  event: WastageEvent;
  wantsPhoto: boolean;
  onAgain: () => void;
}): ReactElement {
  return (
    <div className="flex flex-col gap-page">
      <Notice tone="success" title={strings.waste.logged(event.reason_name)} />
      <p className="text-3xl font-semibold tabular-nums">{formatINR(event.cost_value)}</p>
      <p className="text-muted-foreground">{strings.waste.costHint}</p>
      {event.awaiting_approval ? (
        <Notice tone="info" title={strings.waste.awaitingApproval} />
      ) : null}

      {/* **The nudge, and it is only ever a nudge** (owner's decision, 2026-09-18). It appears
          after the log is saved, when the cook is no longer holding a tray, and *Log something
          else* is right beside it — because `docs/waste-model.md`'s rule is that anything making
          honest reporting harder gets you less honest reporting, not more photographs. */}
      {wantsPhoto ? (
        <section className="flex flex-col gap-2 rounded-md bg-caution-soft p-4 text-caution">
          <h2 className="font-medium text-caution">{strings.waste.photoWanted}</h2>
          <p className="text-sm">{strings.waste.photoWantedHint}</p>
          <AttachmentControl
            ownerType="wastage_event"
            ownerId={event.id}
            attachments={[]}
          />
        </section>
      ) : null}

      <Button onClick={onAgain}>{strings.waste.logAnother}</Button>
    </div>
  );
}
