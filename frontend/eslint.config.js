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
      // The design system's one mechanical contract. A colour written into a component cannot be
      // themed, cannot be checked for contrast, and is invisible to anyone reading tokens.css — so
      // it is an error rather than a review comment. If a token is missing, add it to
      // src/shared/theme/tokens.css in the same change.
      'no-restricted-syntax': [
        'error',
        {
          selector:
            "JSXAttribute[name.name='className'] Literal[value=/#[0-9a-fA-F]{3,8}\\b|\\b(rgb|hsl)a?\\(/]",
          message:
            'Colours come from tokens (bg-primary, text-critical, …), never a literal. Add a token to src/shared/theme/tokens.css if one is missing.',
        },
        {
          selector: "JSXAttribute[name.name='style']",
          message:
            'Inline styles bypass the token system and the theme. Use a Tailwind class backed by a token.',
        },
      ],
    },
  },
  {
    // The API client is the one place allowed to call fetch — it is what everything else uses.
    files: ['src/shared/api.ts'],
    rules: { 'no-restricted-globals': 'off' },
  },
  {
    // Vendored shadcn/ui components. They are copied into this repository rather than installed,
    // and they export their `cva` variants beside the component by convention. Editing that out of
    // every component on arrival — and again on every upstream update — is precisely the fork we
    // adopted shadcn to avoid, so the rule is relaxed here and nowhere else.
    files: ['src/shared/ui/**/*.tsx'],
    rules: { 'react-refresh/only-export-components': 'off' },
  },
);
