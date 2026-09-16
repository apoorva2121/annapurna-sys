import path from 'node:path';

import react from '@vitejs/plugin-react';
import { playwright } from '@vitest/browser-playwright';
import { defineConfig } from 'vitest/config';

/**
 * The visual-regression run (backlog-issues B11b, decision D4): only `*.visual.test.tsx`, in a
 * headless Chromium that Playwright pins, at a fixed viewport.
 *
 * Separate from vite.config.ts on purpose. `make check` runs the jsdom suite and must stay
 * runnable on a laptop with nothing installed but Node; this needs a browser and produces Linux
 * pixels, so it runs in CI's Playwright container and, locally, through `make visual` in the same
 * image. The two configs share nothing but the aliases, which is why those are repeated here
 * rather than imported — a shared base would pull jsdom's setup file into the browser.
 */
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@shared': path.resolve(__dirname, 'src/shared'),
      '@staff': path.resolve(__dirname, 'src/staff'),
    },
  },
  test: {
    include: ['src/**/*.visual.test.tsx'],
    browser: {
      enabled: true,
      headless: true,
      provider: playwright(),
      instances: [{ browser: 'chromium', viewport: { width: 800, height: 900 } }],
    },
  },
});
