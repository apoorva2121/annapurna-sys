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
    // The two API clients are the only places allowed to call fetch.
    //
    // `shared/api.ts` is the staff one. `guest/api.ts` is the second, and it is a second rather
    // than a reuse because ADR 0009 ships the guest bundle without the staff session: no refresh
    // cookie, no cross-tab lock, no single-flight refresh, no idempotency allow-list. A guest token
    // comes from a QR code and, when it dies, the answer is to scan again.
    files: ['src/shared/api.ts', 'src/guest/api.ts'],
    rules: { 'no-restricted-globals': 'off' },
  },
  {
    // ADR 0009's boundary, as a build failure rather than a promise.
    //
    // `src/guest/README.md` has carried this rule since M00: "No staff code may ever be imported
    // into `guest/`. Not a component, not a hook, not a type, not a constant." If the guest bundle
    // contains staff code, it ships admin routes to discover and permission strings to enumerate to
    // thousands of strangers on a hostile network — precisely the failure ADR 0009 exists to
    // prevent. Shared, persona-neutral code lives in `src/shared/`; anything that knows about staff
    // stays in `src/staff/`.
    //
    // The mirror rule is deliberately absent: staff importing from `guest/` would be odd and
    // harmless, and a rule nobody can violate is a rule nobody reads.
    files: ['src/guest/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            {
              group: ['@staff/*', '**/staff/*'],
              message:
                'ADR 0009: the guest bundle ships none of the staff code. Persona-neutral code ' +
                'lives in src/shared/; anything that knows about staff stays in src/staff/. The ' +
                'duplication between the two personas is the feature, not a smell.',
            },
          ],
        },
      ],
    },
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
