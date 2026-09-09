import path from 'node:path';
import process from 'node:process';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

// ADR 0009 — staff and guest are two applications, not two roles. They are separate Rollup entry
// points so the guest bundle can never contain staff code: no admin routes to discover, no
// permission strings to enumerate. The guest entry arrives in M10 and is one line here, by design.
const API_PROXY_TARGET = process.env.VITE_API_PROXY_TARGET ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@shared': path.resolve(__dirname, 'src/shared'),
      '@staff': path.resolve(__dirname, 'src/staff'),
    },
  },
  build: {
    rollupOptions: {
      input: {
        staff: path.resolve(__dirname, 'index.html'),
        // guest: path.resolve(__dirname, 'guest.html'),  ← M10, ADR 0009
      },
    },
  },
  server: {
    port: 5173,
    host: true,
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
  },
});
