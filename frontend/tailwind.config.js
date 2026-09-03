/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Status colors used everywhere
        online: '#22c55e',   // green
        offline: '#ef4444',  // red
        unknown: '#eab308',  // yellow
        // Dark theme palette
        bg: '#0b1120',
        panel: '#111827',
        panel2: '#1f2937',
        border: '#1f2937',
        text: '#e5e7eb',
        muted: '#94a3b8',
        accent: '#3b82f6',
      },
      keyframes: {
        pulse_dot: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
        slide_in: {
          '0%': { transform: 'translateX(120%)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
      },
      animation: {
        'pulse-dot': 'pulse_dot 1.5s ease-in-out infinite',
        'slide-in': 'slide_in 200ms ease-out',
      },
    },
  },
  plugins: [],
};