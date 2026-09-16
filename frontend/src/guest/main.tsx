/// <reference types="vite/client" />
// The guest bundle's entry point — ADR 0009's second Rollup input, held open since M00.
//
// **It ships none of the staff code.** No router (the whole session is one URL), no auth provider
// (a QR code is the authentication), no query client (three requests, each made once), no theme
// picker. What it does share is `src/shared/`: the tokens, the money formatter and the fonts, all
// persona-neutral.
//
// Every kilobyte here is a guest who did not wait, on their own phone, on a network nobody
// controls.

import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';

import '@fontsource-variable/ibm-plex-sans';
import '@shared/index.css';

import App from './App';

const root = document.getElementById('root');
if (root !== null) {
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  );
}
