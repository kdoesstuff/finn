import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import globals from 'globals'
import tseslint from 'typescript-eslint'

// Text from filings is rendered as text, always. These rules make the alternatives fail the build.
const noHtmlInjection = [
  {
    selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
    message: 'No dangerouslySetInnerHTML: render text as text.',
  },
  {
    selector: "AssignmentExpression > MemberExpression[property.name=/^(innerHTML|outerHTML)$/]",
    message: 'No innerHTML or outerHTML: build elements, or render text as text.',
  },
  {
    selector: "CallExpression[callee.property.name='insertAdjacentHTML']",
    message: 'No insertAdjacentHTML.',
  },
  {
    selector: "CallExpression[callee.object.name='document'][callee.property.name=/^(write|writeln)$/]",
    message: 'No document.write.',
  },
  {
    selector: "CallExpression[callee.property.name='createContextualFragment']",
    message: 'No createContextualFragment: it parses HTML.',
  },
  {
    selector: "NewExpression[callee.name='DOMParser']",
    message: 'No DOMParser: nothing in FINN should parse HTML.',
  },
  {
    // The CSP allows no inline styles; style attributes would also be blocked in markup.
    selector: "JSXAttribute[name.name='style']",
    message: 'No inline styles: use a class and tokens.css (the CSP allows stylesheets from the app only).',
  },
  {
    selector: "CallExpression[callee.name='eval'], NewExpression[callee.name='Function']",
    message: 'No eval or new Function (the CSP forbids them too).',
  },
]

export default tseslint.config(
  { ignores: ['dist', 'dev-dist', 'node_modules', 'playwright-report', 'test-results', 'coverage'] },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [js.configs.recommended, ...tseslint.configs.strictTypeChecked],
    languageOptions: {
      ecmaVersion: 2023,
      globals: { ...globals.browser },
      parserOptions: {
        project: ['./tsconfig.json', './tsconfig.node.json'],
        tsconfigRootDir: import.meta.dirname,
      },
    },
    plugins: { 'react-hooks': reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      'no-restricted-syntax': ['error', ...noHtmlInjection],
      'no-restricted-properties': [
        'error',
        { object: 'window', property: 'eval', message: 'No eval.' },
        { object: 'localStorage', message: 'The session token stays in memory; nothing goes to storage.' },
        { object: 'sessionStorage', message: 'The session token stays in memory; nothing goes to storage.' },
      ],
      'no-restricted-globals': [
        'error',
        { name: 'localStorage', message: 'The session token stays in memory; nothing goes to storage.' },
        { name: 'sessionStorage', message: 'The session token stays in memory; nothing goes to storage.' },
      ],
      '@typescript-eslint/restrict-template-expressions': ['error', { allowNumber: true }],
      // `onClick={() => setOpen(true)}` is idiomatic React; braces would add nothing.
      '@typescript-eslint/no-confusing-void-expression': ['error', { ignoreArrowShorthand: true }],
    },
  },
  {
    files: ['build/**/*.ts', 'e2e/**/*.ts', 'vite.config.ts', 'playwright.config.ts'],
    languageOptions: { globals: { ...globals.node } },
  },
  {
    files: ['**/*.test.{ts,tsx}', 'src/test/**/*.{ts,tsx}', 'e2e/**/*.ts'],
    rules: {
      // Tests read fixtures and assert on DOM nodes known to exist.
      '@typescript-eslint/no-non-null-assertion': 'off',
    },
  },
  {
    files: ['scripts/**/*.mjs', 'eslint.config.js'],
    extends: [js.configs.recommended],
    languageOptions: { globals: { ...globals.node } },
  },
)
