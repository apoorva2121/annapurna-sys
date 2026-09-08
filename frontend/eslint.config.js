import js from '@eslint/js';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist', 'node_modules', 'coverage'] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.strictTypeChecked],
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
      parserOptions: { project: ['./tsconfig.json'], tsconfigRootDir: import.meta.dirname },
    },
    plugins: { 'react-hooks': reactHooks, 'react-refresh': reactRefresh },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
      // docs/engineering-standards.md §2 — same complexity budget as the backend.
      complexity: ['error', 10],
      // docs/engineering-standards.md §5 — TanStack Query only; no fetch in a component.
      'no-restricted-globals': [
        'error',
        { name: 'fetch', message: 'Use the API client in @shared/api via TanStack Query.' },
      ],
    },
  },
  {
    // The API client is the one place allowed to call fetch — it is what everything else uses.
    files: ['src/shared/api.ts'],
    rules: { 'no-restricted-globals': 'off' },
  },
);
