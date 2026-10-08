/** @type {import('tailwindcss').Config} */
// M4 design system — see phases/milestone-4/design-system.md
// Every color, spacing, font, and motion token used in the UI is defined
// here. Component code must use these tokens (e.g. `bg-surface`,
// `text-primary`, `border-strong`); raw hex values are a code-review red flag.

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // ── Surface (slate) ───────────────────────────────────────────
        'bg-base': '#0b1220',
        'bg-surface': '#111a2e',
        'bg-surface-2': '#172239',

        // ── Border ────────────────────────────────────────────────────
        border: '#1f2d4a',
        'border-strong': '#2d4170',
        'border-muted': '#152037',

        // ── Text ──────────────────────────────────────────────────────
        'text-primary': '#e6edf7',
        'text-secondary': '#8aa0c4',
        'text-muted': '#5a6e91',
        'text-inverse': '#0b1220',

        // ── Status (semantic — never reused for unrelated things) ────
        accent: '#22d3ee',
        'accent-soft': 'rgba(34, 211, 238, 0.15)',
        success: '#34d399',
        'success-soft': 'rgba(52, 211, 153, 0.15)',
        warn: '#fbbf24',
        'warn-soft': 'rgba(251, 191, 36, 0.15)',
        danger: '#f87171',
        'danger-soft': 'rgba(248, 113, 113, 0.15)',
        info: '#818cf8',
        'info-soft': 'rgba(129, 140, 248, 0.15)',

        // ── Subnet palette (wire colors) ──────────────────────────────
        'subnet-1': '#22d3ee',
        'subnet-2': '#a78bfa',
        'subnet-3': '#34d399',
        'subnet-4': '#fbbf24',
        'subnet-5': '#f472b6',
        'subnet-6': '#60a5fa',

        // ── Protocol palette (packet rows) ────────────────────────────
        'protocol-tcp': '#22d3ee',
        'protocol-udp': '#a78bfa',
        'protocol-icmp': '#34d399',
        'protocol-arp': '#fbbf24',
        'protocol-http': '#60a5fa',
        'protocol-other': '#8aa0c4',
        'protocol-attack': '#f87171',

        // ── Node-kind palette (canvas icons + status pills) ──────────
        'node-host': '#60a5fa',
        'node-switch': '#34d399',
        'node-router': '#22d3ee',
        'node-server': '#a78bfa',
        'node-attacker': '#f87171',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['"JetBrains Mono"', '"SF Mono"', 'Menlo', 'Consolas', 'monospace'],
      },
      fontSize: {
        '2xs': ['10px', '14px'],
        xs: ['11px', '16px'],
        sm: ['13px', '18px'],
        base: ['15px', '22px'],
        lg: ['18px', '26px'],
        xl: ['22px', '30px'],
        '2xl': ['30px', '38px'],
      },
      borderRadius: {
        sm: '4px',
        md: '6px',
        lg: '10px',
        xl: '16px',
      },
      boxShadow: {
        sm: '0 1px 2px rgba(0,0,0,0.3)',
        md: '0 4px 12px rgba(0,0,0,0.4)',
        lg: '0 12px 32px rgba(0,0,0,0.5)',
        'glow-accent': '0 0 16px rgba(34, 211, 238, 0.4)',
        'glow-danger': '0 0 16px rgba(248, 113, 113, 0.4)',
      },
      transitionDuration: {
        fast: '150ms',
        base: '200ms',
        slow: '400ms',
      },
      keyframes: {
        'pulse-dot': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.4' },
        },
        'slide-in': {
          '0%': { transform: 'translateX(120%)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' },
        },
        'slide-in-up': {
          '0%': { transform: 'translateY(8px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        'shimmer': {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      animation: {
        'pulse-dot': 'pulse-dot 2s ease-in-out infinite',
        'slide-in': 'slide-in 200ms cubic-bezier(0.16, 1, 0.3, 1)',
        'slide-in-up': 'slide-in-up 200ms cubic-bezier(0.16, 1, 0.3, 1)',
        'shimmer': 'shimmer 1.2s linear infinite',
      },
    },
  },
  plugins: [],
};
