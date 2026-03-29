/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class', 'data-theme="dark"'],
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Kuasarr Space Theme
        'bg-primary': '#0B0B10',
        'bg-secondary': '#12121A',
        'bg-tertiary': '#1A1A25',
        'kuasarr-primary': '#7C3AED',
        'kuasarr-primary-light': '#A78BFA',
        'kuasarr-secondary': '#3B82F6',
        'kuasarr-accent': '#06B6D4',
        'text-primary': '#F8FAFC',
        'text-secondary': '#94A3B8',
        'kuasarr-success': '#22C55E',
        'kuasarr-warning': '#F59E0B',
        'kuasarr-error': '#EF4444',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        heading: ['Space Grotesk', 'Inter', 'sans-serif'],
      },
      animation: {
        'fade-in': 'fadeIn 0.2s ease-out',
        'slide-up': 'slideUp 0.3s ease-out',
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        slideUp: {
          '0%': { transform: 'translateY(10px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
