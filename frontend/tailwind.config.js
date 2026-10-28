/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: '#3b82f6',
        'brand-soft': '#60a5fa',
        accent: '#14b8a6',
        ink: '#f8fafc',
        fog: '#94a3b8',
        paper: '#020617', // slate-950
        panel: '#0f172a', // slate-900
        line: '#1e293b', // slate-800
        warning: '#f59e0b',
        danger: '#ef4444'
      },
      fontFamily: {
        display: ['Space Grotesk', 'sans-serif'],
        sans: ['Inter', 'sans-serif']
      },
      animation: {
        'slide-up': 'slideUp 0.6s cubic-bezier(0.16, 1, 0.3, 1) both',
        'pulse-slow': 'pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'fill-width': 'fillWidth 1.5s cubic-bezier(0.16, 1, 0.3, 1) both',
      },
      keyframes: {
        slideUp: {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        fillWidth: {
          '0%': { width: '0%' },
        }
      }
    },
  },
  plugins: [],
}
