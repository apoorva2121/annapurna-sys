/**
 * shadcn/ui's Switch (Radix), adapted to this product's tokens.
 *
 * 1. **Bigger: `h-6 w-11` with an `h-5 w-5` thumb**, up from `h-5 w-9`/`h-4 w-4`. The generated
 *    size is a 20px-tall control, which is not aimable with a thumb and nowhere near aimable with
 *    a glove. It still falls short of `--target-min`, so **the label is part of the hit area** —
 *    pair it with `Label htmlFor`, which Radix wires to the input, rather than leaving the switch
 *    to be hit on its own.
 * 2. **No shadows.**
 *
 * A switch means "this takes effect now". For anything that needs saving, use a checkbox and a
 * submit button — a switch that silently does nothing until a later Save teaches people that the
 * control is a lie.
 */
import * as React from 'react';
import * as SwitchPrimitives from '@radix-ui/react-switch';

import { cn } from '@shared/cn';

const Switch = React.forwardRef<
  React.ElementRef<typeof SwitchPrimitives.Root>,
  React.ComponentPropsWithoutRef<typeof SwitchPrimitives.Root>
>(({ className, ...props }, ref) => (
  <SwitchPrimitives.Root
    className={cn(
      'peer inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border-2 border-transparent transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:cursor-not-allowed disabled:opacity-50 data-[state=checked]:bg-primary data-[state=unchecked]:bg-input',
      className,
    )}
    {...props}
    ref={ref}
  >
    <SwitchPrimitives.Thumb
      className={cn(
        'pointer-events-none block h-5 w-5 rounded-full bg-background ring-0 transition-transform data-[state=checked]:translate-x-5 data-[state=unchecked]:translate-x-0',
      )}
    />
  </SwitchPrimitives.Root>
));
Switch.displayName = SwitchPrimitives.Root.displayName;

export { Switch };
