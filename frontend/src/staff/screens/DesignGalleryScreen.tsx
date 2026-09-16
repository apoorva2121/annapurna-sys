import { type ReactElement, useState } from 'react';

import { formatDelta, formatINR } from '@shared/money';
import { Button } from '@shared/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@shared/ui/dialog';
import { Label } from '@shared/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@shared/ui/select';
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@shared/ui/sheet';
import { Switch } from '@shared/ui/switch';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@shared/ui/table';
import { Field } from '@staff/components/Field';
import { Notice } from '@staff/components/Notice';
import { QuantityStepper } from '@staff/components/QuantityStepper';
import { QueryState } from '@staff/components/QueryState';
import { WaiterSurface } from '@staff/components/WaiterSurface';
import { strings } from '@staff/strings';

/**
 * The `/design` gallery (backlog-issues B11b, decision D4): every component in
 * `docs/ui/design-system.md` §4 and every waiter pattern, each in its resting state, on one page.
 *
 * **It exists to be photographed.** `DesignGalleryScreen.visual.test.tsx` screenshots each
 * `<Specimen>` in a pinned Linux browser and compares it with the baseline in `__screenshots__/`,
 * so a token change that moves a button by a pixel is a diff somebody reads, not a surprise on a
 * waiter's phone. Each specimen is wrapped in `data-specimen`, which is what the test aims at.
 *
 * **It shows real components, never copies.** A gallery that re-drew a Button would drift from the
 * one screens use and certify the wrong thing; the gallery imports what the screens import.
 *
 * **Static.** Nothing here reads the API — a query would make the screenshot depend on the network.
 * The one `QueryState` specimen is shown in its pending state on purpose, because that skeleton is
 * the state most screens spend their first second in and the one least often looked at.
 */
export default function DesignGalleryScreen(): ReactElement {
  return (
    <div className="max-w-3xl space-y-page">
      <h1 className="text-2xl font-semibold">{strings.gallery.title}</h1>
      <p className="text-sm text-muted-foreground">{strings.gallery.intro}</p>

      <Section title={strings.gallery.components}>
        <Specimen name="button">
          <div className="flex flex-wrap gap-2">
            <Button>Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="brand">Brand</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="destructive">Destructive</Button>
            <Button variant="link">Link</Button>
            <Button disabled>Disabled</Button>
            <Button size="lg">Large</Button>
            <Button size="icon" aria-label="One more">
              +
            </Button>
          </div>
        </Specimen>

        <Specimen name="select">
          <div className="flex flex-col gap-1 text-sm">
            <span>Station</span>
            <Select defaultValue="tandoor">
              <SelectTrigger aria-label="Station">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="tandoor">Tandoor</SelectItem>
                <SelectItem value="curry">Curry</SelectItem>
                <SelectItem value="chinese">Chinese</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </Specimen>

        <Specimen name="dialog">
          <Dialog>
            <DialogTrigger asChild>
              <Button variant="secondary">Open a dialog</Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Close the till?</DialogTitle>
                <DialogDescription>
                  The count is final once it is saved. Payouts after this go into the next till.
                </DialogDescription>
              </DialogHeader>
              <Button>Yes, close it</Button>
            </DialogContent>
          </Dialog>
        </Specimen>

        <Specimen name="sheet">
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="secondary">Open a sheet</Button>
            </SheetTrigger>
            <SheetContent side="bottom">
              <SheetHeader>
                <SheetTitle>Dal Makhani</SheetTitle>
                <SheetDescription>Choose a portion, then any extras.</SheetDescription>
              </SheetHeader>
              <Button disabled>Add</Button>
            </SheetContent>
          </Sheet>
        </Specimen>

        <Specimen name="switch">
          <SwitchSpecimen />
        </Specimen>

        <Specimen name="table">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Dish</TableHead>
                <TableHead className="text-right">Price</TableHead>
                <TableHead className="text-right">Food cost</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              <TableRow>
                <TableCell>Chilli Paneer</TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {formatINR('270.00')}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">46%</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Butter Chicken</TableCell>
                <TableCell className="text-right font-mono tabular-nums">
                  {formatINR('470.00')}
                </TableCell>
                <TableCell className="text-right font-mono tabular-nums">27%</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Specimen>

        <Specimen name="field">
          <div className="flex flex-col gap-4">
            <Field label="Name" defaultValue="Butter Chicken" readOnly />
            <Field
              label="Expiry"
              hint="Optional. Undated stock waits behind everything that has a date."
              defaultValue=""
              readOnly
            />
            <Field
              label="GSTIN"
              defaultValue="27AAAAA"
              error="Use the 15-character GSTIN."
              readOnly
            />
          </div>
        </Specimen>

        <Specimen name="notice">
          <div className="flex flex-col gap-3">
            <Notice tone="critical" title="Not enough cash in the till." issue={1012}>
              Only ₹12,000.00 is available.
            </Notice>
            <Notice tone="success" title="Saved." />
            <Notice tone="info" title="Nobody has checked this recipe yet.">
              It came from the library.
            </Notice>
          </div>
        </Specimen>

        <Specimen name="query-state">
          <QueryState isPending error={null} pendingLabel="Loading">
            <></>
          </QueryState>
        </Specimen>
      </Section>

      <Section title={strings.gallery.waiterPatterns}>
        <WaiterSurface>
          <Specimen name="table-map-cell">
            <div className="grid grid-cols-3 gap-3">
              <button type="button" className={`${CELL} border-border`}>
                <span className="text-lg font-semibold">T4</span>
                <span>Free</span>
                <span className="text-sm text-muted-foreground">4 seats</span>
              </button>
              <div className={`${CELL} border-primary`}>
                <span className="text-lg font-semibold">T7</span>
                <span>Occupied</span>
                <span className="text-sm">Order 41</span>
                <span className="font-mono tabular-nums">{formatINR('1240.00')}</span>
                <span className="font-semibold">Bill asked for</span>
              </div>
              <button
                type="button"
                className={`${CELL} border-border disabled:opacity-60`}
                disabled
              >
                <span className="text-lg font-semibold">T9</span>
                <span>Out of service</span>
              </button>
            </div>
          </Specimen>

          <Specimen name="order-line-row">
            <ul>
              <li className="flex flex-col gap-2 border-b border-border py-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="font-medium">2 × Dal Makhani</p>
                    <p className="text-sm text-muted-foreground">Less spicy, Extra butter</p>
                    <p className="text-sm">Not sent yet</p>
                  </div>
                  <div className="flex flex-col items-end gap-1">
                    <span className="font-mono tabular-nums">{formatINR('580.00')}</span>
                    <Button variant="ghost">Take off</Button>
                  </div>
                </div>
                <StepperSpecimen />
              </li>
              <li className="flex flex-col gap-2 border-b border-border py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="text-muted-foreground line-through">
                    <p className="font-medium">1 × Garlic Naan</p>
                    <p className="text-sm">Cancelled</p>
                  </div>
                  <span className="font-mono tabular-nums">{formatINR('60.00')}</span>
                </div>
              </li>
            </ul>
          </Specimen>

          <Specimen name="money">
            <dl className="grid grid-cols-[1fr_auto] gap-x-6 gap-y-1">
              <dt>Subtotal</dt>
              <dd className="text-right font-mono tabular-nums">{formatINR('1240.00')}</dd>
              <dt>Discount</dt>
              <dd className="text-right font-mono tabular-nums">{formatDelta('-124.00')}</dd>
              <dt>GST 5%</dt>
              <dd className="text-right font-mono tabular-nums">{formatINR('55.80')}</dd>
              <dt className="font-semibold">Total</dt>
              <dd className="text-right font-mono font-semibold tabular-nums">
                {formatINR('1171.80')}
              </dd>
            </dl>
          </Specimen>
        </WaiterSurface>
      </Section>
    </div>
  );
}

/** The table-map cell's classes, as `TableMapScreen` composes them. */
const CELL =
  'flex min-h-target w-full flex-col items-start gap-1 rounded-lg border bg-card p-3 text-left';

function Section({
  title,
  children,
}: {
  title: string;
  children: ReactElement | ReactElement[];
}): ReactElement {
  return (
    <section className="space-y-6">
      <h2 className="text-lg font-semibold">{title}</h2>
      {children}
    </section>
  );
}

/** One thing to photograph. `data-specimen` is the handle the visual test aims at. */
function Specimen({ name, children }: { name: string; children: ReactElement }): ReactElement {
  return (
    <div data-specimen={name} className="space-y-2">
      <p className="font-mono text-xs text-muted-foreground">{name}</p>
      <div className="rounded-md border border-border bg-background p-4">{children}</div>
    </div>
  );
}

function SwitchSpecimen(): ReactElement {
  const [on, setOn] = useState(true);
  return (
    <div className="flex items-center gap-3">
      <Switch id="gallery-switch" checked={on} onCheckedChange={setOn} />
      <Label htmlFor="gallery-switch">Busy mode</Label>
    </div>
  );
}

function StepperSpecimen(): ReactElement {
  const [count, setCount] = useState(2);
  return (
    <QuantityStepper value={count} min={1} max={20} label="Dal Makhani" onChange={setCount} />
  );
}
