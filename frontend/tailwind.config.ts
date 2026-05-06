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
          950: '#0d1014',
          900: '#111820',
          800: '#161e2a',
          700: '#1a2332',
          600: '#1e273a',
          500: '#22293c',
          400: '#262e3e',
        },
        peach: '#ff8a5c',
        error: '#ff6a55',
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
