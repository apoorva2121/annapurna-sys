// The gallery, photographed (backlog-issues B11b, decision D4).
//
// Every `data-specimen` block on `/design` is screenshotted in a pinned Linux Chromium and compared
// with the baseline committed in `__screenshots__/`. A token change that moves a button by a pixel
// becomes a diff a reviewer reads, rather than a surprise on a waiter's phone.
//
// Runs only under `npm run test:visual` (vitest.visual.config.ts), never under `make check`: it
// needs a real browser, and the baselines are Linux pixels — a Windows or macOS run would differ in
// font hinting alone. Regenerate with `make visual-update`, which runs it inside the same Playwright
// image CI uses, then commit the pictures with the change that moved them.

import { render } from 'vitest-browser-react';
import { page } from 'vitest/browser';
import { describe, expect, it } from 'vitest';

import { MemoryRouter } from 'react-router-dom';

import DesignGalleryScreen from './DesignGalleryScreen';

// What main.tsx loads: the two Plex faces and the tokens. Without them the browser photographs a
// system font on a white page, and the baseline certifies nothing the app ever shows.
import '@fontsource-variable/ibm-plex-sans';
import '@fontsource/ibm-plex-mono';
import '@shared/index.css';

const SPECIMENS = [
  'button',
  'select',
  'dialog',
  'sheet',
  'switch',
  'table',
  'field',
  'notice',
  'query-state',
  'table-map-cell',
  'order-line-row',
  'money',
] as const;

describe('the design gallery', () => {
  for (const name of SPECIMENS) {
    it(`still looks like the baseline: ${name}`, async () => {
      // `render` is async in vitest-browser-react: it resolves once the component is on the page.
      const screen = await render(
        <MemoryRouter>
          <DesignGalleryScreen />
        </MemoryRouter>,
      );
      const specimen = screen.container.querySelector(`[data-specimen="${name}"]`);
      expect(specimen).not.toBeNull();

      await expect(page.elementLocator(specimen as Element)).toMatchScreenshot(name, {
        comparatorName: 'pixelmatch',
        // Anti-aliasing differs run to run even on one image; a real change is many pixels.
        comparatorOptions: { threshold: 0.2, allowedMismatchedPixelRatio: 0.002 },
      });
    });
  }
});
