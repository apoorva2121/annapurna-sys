import path from 'node:path';
import process from 'node:process';

import react from '@vitejs/plugin-react';
import { configDefaults, defineConfig } from 'vitest/config';

// ADR 0009 — staff and guest are two applications, not two roles. They are separate Rollup entry
// points so the guest bundle can never contain staff code: no admin routes to discover, no
// permission strings to enumerate. The guest entry arrived in M10 and was one line here, as
// designed — the boundary itself is an eslint rule, because a build that merely *can* keep the two
// apart is not the same as one that refuses to put them together.
const API_PROXY_TARGET = process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@shared': path.resolve(__dirname, 'src/shared'),
      '@staff': path.resolve(__dirname, 'src/staff'),
      '@guest': path.resolve(__dirname, 'src/guest'),
    },
  },
  build: {
    rollupOptions: {
      input: {
        staff: path.resolve(__dirname, 'index.html'),
        // M10. The one line this seam was held open for since M00.
        guest: path.resolve(__dirname, 'guest.html'),
      },
    },
  },
  server: {
    port: 5173,
    host: true,
    // WINDOWS TRAP 4 — the same inotify problem docker-compose.yml documents for the API, and
    // Vite has its own watcher so WATCHFILES_FORCE_POLLING does not cover it. Without polling,
    // edits made on the Windows host never reach the container's watcher: the dev server keeps
    // serving the previous version of a file, HMR stays silent, and the only symptom is a browser
    // that disagrees with the editor. Costly to diagnose, one line to prevent.
    //
    // Opt-in via the environment so a native (non-container) `npm run dev` keeps inotify and does
    // not burn a core polling the filesystem.
    ...(process.env.VITE_FORCE_POLLING === 'true'
      ? { watch: { usePolling: true, interval: 300 } }
      : {}),
    // The API is same-origin in production; the proxy keeps it same-origin in dev too, so no
    // CORS-only code path exists that production never exercises.
    //
    // The target must be configurable, not hardcoded: when vite runs on the host the API is on
    // localhost, but inside the compose network the dev server is its own host and `localhost` is
    // the web container, where nothing listens. Compose sets this to http://api:8000 — the same
    // reasoning docker-compose.yml already applies to DATABASE_URL's `db` host.
    proxy: { '/api': { target: API_PROXY_TARGET, changeOrigin: true } },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/shared/test-setup.ts',
    // The visual-regression specs need a real browser and Linux pixels, so they run from
    // vitest.visual.config.ts instead (backlog-issues B11b, decision D4). Excluded here because
    // `make check` must stay runnable on a machine with nothing installed but Node.
    exclude: [...configDefaults.exclude, '**/*.visual.test.tsx'],
  },
});
