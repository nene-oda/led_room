import js from '@eslint/js'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import globals from 'globals'
import tseslint from 'typescript-eslint'

// Las reglas arquitectonicas van aqui, no en un documento: una convencion que
// no rompe el build se erosiona (NEXT_STEPS 5.6).
const TRANSPORT_MESSAGE =
  'El transporte vive en src/api/**. Fuera de esa carpeta no se habla HTTP ni WebSocket directamente (ARCHITECTURE.md 4).'

const API_IMPORT_MESSAGE =
  'components/** no importa src/api/**: los datos entran por props o por hooks, y los DTO no se filtran a la UI (NEXT_STEPS 5.1 y 5.2).'

export default tseslint.config(
  { ignores: ['dist', 'coverage', 'node_modules'] },
  js.configs.recommended,
  tseslint.configs.recommended,
  // OJO: en eslint-plugin-react-hooks 7 hay que usar configs.flat.recommended.
  // configs['recommended-latest'] sigue siendo formato eslintrc y ESLint 10
  // aborta con "A config object has a plugins key defined as an array".
  reactHooks.configs.flat.recommended,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: { 'react-refresh': reactRefresh },
    rules: {
      'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    },
  },
  {
    files: ['src/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-globals': [
        'error',
        { name: 'fetch', message: TRANSPORT_MESSAGE },
        { name: 'WebSocket', message: TRANSPORT_MESSAGE },
      ],
    },
  },
  {
    // La capa de transporte es justamente la que puede usarlos.
    files: ['src/api/**/*.{ts,tsx}'],
    rules: { 'no-restricted-globals': 'off' },
  },
  {
    files: ['src/components/**/*.{ts,tsx}'],
    rules: {
      'no-restricted-imports': [
        'error',
        {
          patterns: [
            { group: ['**/api', '**/api/*', '**/api/**'], message: API_IMPORT_MESSAGE },
          ],
        },
      ],
    },
  },
  {
    files: ['vite.config.ts', 'eslint.config.js'],
    languageOptions: { globals: globals.node },
  },
)
