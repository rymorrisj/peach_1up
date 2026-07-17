import type { Config } from 'tailwindcss'

const config: Config = {
  darkMode: 'class',
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          0: 'rgb(var(--surface-0) / <alpha-value>)',
          1: 'rgb(var(--surface-1) / <alpha-value>)',
          2: 'rgb(var(--surface-2) / <alpha-value>)',
          3: 'rgb(var(--surface-3) / <alpha-value>)',
        },
        border: {
          DEFAULT: 'rgb(var(--border) / <alpha-value>)',
          strong: 'rgb(var(--border-strong) / <alpha-value>)',
        },
        fg: {
          1: 'rgb(var(--fg-1) / <alpha-value>)',
          2: 'rgb(var(--fg-2) / <alpha-value>)',
          3: 'rgb(var(--fg-3) / <alpha-value>)',
          inverse: 'rgb(var(--fg-inverse) / <alpha-value>)',
        },
        peach: {
          300: 'rgb(var(--peach-300) / <alpha-value>)',
          400: 'rgb(var(--peach-400) / <alpha-value>)',
          500: 'rgb(var(--peach-500) / <alpha-value>)',
          600: 'rgb(var(--peach-600) / <alpha-value>)',
          700: 'rgb(var(--peach-700) / <alpha-value>)',
          DEFAULT: 'rgb(var(--peach-500) / <alpha-value>)',
        },
        success: 'rgb(var(--success) / <alpha-value>)',
        warning: 'rgb(var(--warning) / <alpha-value>)',
        error: 'rgb(var(--error) / <alpha-value>)',
        info: 'rgb(var(--info) / <alpha-value>)',
        era: {
          dos:   'rgb(var(--era-dos) / <alpha-value>)',
          win95: 'rgb(var(--era-win95) / <alpha-value>)',
          win98: 'rgb(var(--era-win98) / <alpha-value>)',
          winxp: 'rgb(var(--era-winxp) / <alpha-value>)',
        },
        'tag-color': {
          1: 'rgb(var(--tag-color-1) / <alpha-value>)',
          2: 'rgb(var(--tag-color-2) / <alpha-value>)',
          3: 'rgb(var(--tag-color-3) / <alpha-value>)',
          4: 'rgb(var(--tag-color-4) / <alpha-value>)',
          5: 'rgb(var(--tag-color-5) / <alpha-value>)',
          6: 'rgb(var(--tag-color-6) / <alpha-value>)',
          7: 'rgb(var(--tag-color-7) / <alpha-value>)',
        },
        accent: {
          DEFAULT: 'rgb(var(--peach-500) / <alpha-value>)',
          hover: 'rgb(var(--peach-600) / <alpha-value>)',
          fg: 'rgb(var(--fg-inverse) / <alpha-value>)',
        },
      },
      fontFamily: {
        sans: ['Space Grotesk', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}

export default config
