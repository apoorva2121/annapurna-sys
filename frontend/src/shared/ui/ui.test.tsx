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
import { useState } from 'react';
import { describe, expect, it } from 'vitest';

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
