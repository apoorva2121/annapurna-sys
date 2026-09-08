/// <reference types="vitest" />
import path from 'node:path';

import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// ADR 0009 — staff and guest are two applications, not two roles. They are separate Rollup entry
// points so the guest bundle can never contain staff code: no admin routes to discover, no
// permission strings to enumerate. The guest entry arrives in M10 and is one line here, by design.
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
    proxy: { '/api': { target: 'http://localhost:8000', changeOrigin: true } },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/shared/test-setup.ts',
  },
});
