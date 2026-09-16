import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { QuantityStepper } from './QuantityStepper';

describe('QuantityStepper', () => {
  it('names what each button changes, and steps by one', async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    render(<QuantityStepper value={2} min={1} max={5} label="Dal Makhani" onChange={onChange} />);

    await user.click(screen.getByRole('button', { name: 'One more Dal Makhani' }));
    await user.click(screen.getByRole('button', { name: 'One fewer Dal Makhani' }));

    expect(onChange.mock.calls).toEqual([[3], [1]]);
  });

  it('disables a button at its limit instead of hiding it, so the row does not move', () => {
    render(<QuantityStepper value={1} min={1} max={1} label="Naan" onChange={vi.fn()} />);

    expect(screen.getByRole('button', { name: 'One fewer Naan' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'One more Naan' })).toBeDisabled();
  });
});
