/// <reference types="vite/client" />
// The reference above is what types the CSS side-effect import below: tsconfig lists `types`
// explicitly, so vite/client's ambient module declarations are not picked up automatically.

import { QueryClientProvider } from '@tanstack/react-query';
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';

// Self-hosted, not a CDN: restaurant WiFi is unreliable, a third-party font host is a privacy
// and CSP question (docs/security.md A05), and a blocked font request means a blank first paint.
// Plex carries Devanagari as a designed companion, which is what makes Hindi and Marathi a data
// change later rather than a redesign.
import '@fontsource-variable/ibm-plex-sans';
import '@fontsource/ibm-plex-mono';
import '@shared/index.css';
import { queryClient } from '@shared/queryClient';
import { initialiseTheme } from '@shared/theme/theme';
import { AuthProvider } from '@staff/auth/AuthProvider';

import App from './App';

// The surface decides target size, density and type scale (tokens.css). Set here rather than
// per screen, so one component is correct on a laptop, a phone and a wall tablet. M07 sets
// `waiter` and M08 sets `kds` on their own entry points.
document.body.dataset.surface = 'manager';

// Before React mounts, so the first paint is already the right theme. Applied late, a light flash
// followed by a dark repaint is the thing people notice most about theming.
initialiseTheme();

const rootElement = document.getElementById('root');
if (rootElement === null) {
  // Fail loudly: a silent blank page is the hardest kind of frontend bug to diagnose on a tablet
  // mounted on a kitchen wall.
  throw new Error('Mount point #root is missing from index.html.');
}

createRoot(rootElement).render(
  <StrictMode>
    {/* QueryClientProvider wraps AuthProvider, not the other way round: the provider clears the
        query cache on sign-in and sign-out, so it needs a client above it. */}
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
