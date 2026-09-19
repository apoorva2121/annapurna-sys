// The vendored components, tested only where this product departed from the generated source.
//
// Radix's own behaviour — focus capture, typeahead, ARIA wiring — is Radix's to test and is the
// reason rule 4 forbids hand-rolling these. What is worth asserting here is the handful of claims
// *we* make on top of it, because those are the ones that can quietly stop being true: the next
// `npx shadcn@latest add` overwrites these files, and an adaptation nobody tested comes back as the
// generated default with nothing to say so.
//
// The switch test exists because its docstring makes a promise about the hit area. A `<label for>`
// does not natively activate a `<button>`, and Radix Switch renders a button — so the promise is
// either true because Radix implements it, or it is a comment describing behaviour the code does
// not have. This file is which.

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createRef, useState } from 'react';
import { describe, expect, it } from 'vitest';

import { Button } from '@shared/ui/button';
import { Dialog, DialogContent, DialogTitle, DialogTrigger } from '@shared/ui/dialog';
import { Label } from '@shared/ui/label';
import { Switch } from '@shared/ui/switch';

function SwitchWithLabel() {
  const [on, setOn] = useState(false);
  return (
    <div>
      <Switch id="accept-orders" checked={on} onCheckedChange={setOn} />
      <Label htmlFor="accept-orders">Accepting orders</Label>
      <span data-testid="state">{on ? 'on' : 'off'}</span>
    </div>
  );
}

describe('Switch', () => {
  it('toggles when the switch itself is pressed', async () => {
    const user = userEvent.setup();
    render(<SwitchWithLabel />);

    await user.click(screen.getByRole('switch'));

    expect(screen.getByTestId('state')).toHaveTextContent('on');
  });

  it('toggles when its label is clicked, which is what makes the hit area usable', async () => {
    // The control is 24px tall — under `--target-min` on every surface. The label is the rest of
    // the target, so a waiter taps the words rather than the toggle. If this ever fails, the
    // docstring in switch.tsx is lying and the switch needs its own padded hit area instead.
    const user = userEvent.setup();
    render(<SwitchWithLabel />);

    await user.click(screen.getByText('Accepting orders'));

    expect(screen.getByTestId('state')).toHaveTextContent('on');
  });

  it('reports its state to assistive technology', async () => {
    const user = userEvent.setup();
    render(<SwitchWithLabel />);
    const toggle = screen.getByRole('switch');

    expect(toggle).toHaveAttribute('aria-checked', 'false');
    await user.click(toggle);

    expect(toggle).toHaveAttribute('aria-checked', 'true');
  });
});

describe('Button', () => {
  // Found on 2026-09-19 by opening the design gallery and reading the console: `Button` was the
  // only component in this folder not wrapped in `forwardRef`, and React had been warning
  // "Function components cannot be given refs" on every page carrying a Dialog or Sheet trigger.
  //
  // Nothing looked broken, because a click rides on event delegation and still worked. What did
  // not work is the ref Radix uses to put focus back on the trigger when an overlay closes.
  it('forwards its ref, which is how Radix returns focus to a trigger', () => {
    const ref = createRef<HTMLButtonElement>();
    render(<Button ref={ref}>Send to kitchen</Button>);

    expect(ref.current, 'Button dropped its ref — Radix focus management will fail').not.toBeNull();
    expect(ref.current?.tagName).toBe('BUTTON');
  });

  it('returns focus to the trigger when a dialog closes', async () => {
    const user = userEvent.setup();
    render(
      <Dialog>
        <DialogTrigger asChild>
          <Button>Close the till?</Button>
        </DialogTrigger>
        <DialogContent>
          <DialogTitle>Close the till?</DialogTitle>
        </DialogContent>
      </Dialog>,
    );

    const trigger = screen.getByRole('button', { name: 'Close the till?' });
    await user.click(trigger);
    await user.keyboard('{Escape}');

    // The keyboard contract: whoever opened it is where the cursor comes back to.
    expect(document.activeElement).toBe(trigger);
  });
});

describe('Dialog', () => {
  it('closes on Escape, which is the behaviour we are not hand-rolling', async () => {
    const user = userEvent.setup();
    render(
      <Dialog>
        <DialogTrigger>Open</DialogTrigger>
        <DialogContent>
          <DialogTitle>Change the business day start</DialogTitle>
        </DialogContent>
      </Dialog>,
    );

    await user.click(screen.getByText('Open'));
    expect(screen.getByRole('dialog')).toBeInTheDocument();

    await user.keyboard('{Escape}');

    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('moves focus into the dialog rather than leaving it on the page behind', async () => {
    const user = userEvent.setup();
    render(
      <Dialog>
        <DialogTrigger>Open</DialogTrigger>
        <DialogContent>
          <DialogTitle>Change the business day start</DialogTitle>
          <button type="button">Save</button>
        </DialogContent>
      </Dialog>,
    );

    await user.click(screen.getByText('Open'));

    expect(screen.getByRole('dialog').contains(document.activeElement)).toBe(true);
  });
});
