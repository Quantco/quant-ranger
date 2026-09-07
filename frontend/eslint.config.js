import js from '@eslint/js'
const javascriptConfigs = js.configs
import { configs as typescriptConfigs } from 'typescript-eslint'
import { defineConfig, globalIgnores } from 'eslint/config'
import reactHooks from 'eslint-plugin-react-hooks'
import globals from 'globals'
import pluginTailwind from 'eslint-plugin-better-tailwindcss'

const typescriptFiles = ['**/*.{ts,tsx}']

export default defineConfig(
  globalIgnores(['node_modules/**', 'pnpm-lock.yaml']),
  {
    files: ['**/*.{js,mjs,cjs}'],
    extends: [javascriptConfigs.recommended],
    languageOptions: {
      ecmaVersion: 'latest',
      globals: globals.node,
      sourceType: 'module'
    }
  },
  {
    files: typescriptFiles,
    extends: [
      javascriptConfigs.recommended,
      ...typescriptConfigs.strictTypeChecked,
      typescriptConfigs.stylisticTypeChecked
    ],
    languageOptions: {
      ecmaVersion: 'latest',
      globals: globals.browser,
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname
      },
      sourceType: 'module'
    },
    rules: {
      '@typescript-eslint/consistent-type-exports': 'error',
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-confusing-void-expression': ['error', { ignoreArrowShorthand: true }],
      '@typescript-eslint/no-import-type-side-effects': 'error',
      '@typescript-eslint/no-unsafe-type-assertion': 'error',
      '@typescript-eslint/restrict-template-expressions': ['error', { allowNumber: true }],
      '@typescript-eslint/strict-boolean-expressions': 'error',
      '@typescript-eslint/switch-exhaustiveness-check': 'error',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_', varsIgnorePattern: '^_' }]
    }
  },
  {
    files: typescriptFiles,
    plugins: {
      'react-hooks': reactHooks
    },
    rules: {
      // React Compiler is not enabled, so only enforce the runtime hook rules.
      'react-hooks/exhaustive-deps': 'warn',
      'react-hooks/rules-of-hooks': 'error'
    }
  },
  {
    files: typescriptFiles,
    plugins: { 'better-tailwindcss': pluginTailwind },
    rules: {
      ...pluginTailwind.configs['recommended-warn'].rules,
      'better-tailwindcss/enforce-consistent-class-order': 'error',
      'better-tailwindcss/enforce-consistent-line-wrapping': 'off',
      'better-tailwindcss/enforce-consistent-variable-syntax': 'warn',
      'better-tailwindcss/no-conflicting-classes': 'error',
      'better-tailwindcss/no-duplicate-classes': 'warn',
      'better-tailwindcss/no-restricted-classes': 'error',
      'better-tailwindcss/no-unnecessary-whitespace': 'warn',
      'better-tailwindcss/no-unknown-classes': 'error'
    },
    settings: {
      'better-tailwindcss': {
        entryPoint: './src/styles.css',
        rootFontSize: 16
      }
    }
  }
)
