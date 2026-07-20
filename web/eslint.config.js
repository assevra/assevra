import js from '@eslint/js';
import astro from 'eslint-plugin-astro';
import tsParser from '@typescript-eslint/parser';

const browserGlobals = {
  console: 'readonly',
  process: 'readonly',
  document: 'readonly',
  window: 'readonly',
  localStorage: 'readonly',
  navigator: 'readonly',
  matchMedia: 'readonly',
  MediaQueryListEvent: 'readonly',
};

export default [
  {
    ignores: ['dist/', '.astro/', 'node_modules/', 'playwright-report/', 'test-results/'],
  },
  js.configs.recommended,
  ...astro.configs.recommended,
  {
    files: ['**/*.ts'],
    languageOptions: {
      parser: tsParser,
      parserOptions: {
        ecmaVersion: 'latest',
        sourceType: 'module',
      },
      globals: browserGlobals,
    },
    rules: {
      // TypeScript-specific globals/types are validated by `astro check`;
      // keep base no-undef off for TS to avoid false positives on types.
      'no-undef': 'off',
    },
  },
  {
    files: ['**/*.astro'],
    rules: {
      'no-unused-vars': ['error', { caughtErrors: 'none' }],
    },
    languageOptions: {
      globals: browserGlobals,
    },
  },
  {
    files: ['**/*.js', '**/*.mjs'],
    languageOptions: {
      globals: browserGlobals,
    },
  },
];
