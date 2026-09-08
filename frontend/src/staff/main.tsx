/// <reference types="vite/client" />
// The reference above is what types the CSS side-effect import below: tsconfig lists `types`
// explicitly, so vite/client's ambient module declarations are not picked up automatically.

import { QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import '@shared/index.css';
import { queryClient } from '@shared/queryClient';

import App from './App';

const rootElement = document.getElementById('root');
if (rootElement === null) {
  // Fail loudly: a silent blank page is the hardest kind of frontend bug to diagnose on a tablet
  // mounted on a kitchen wall.
  throw new Error('Mount point #root is missing from index.html.');
}

createRoot(rootElement).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
