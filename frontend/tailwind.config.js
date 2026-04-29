/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Warm cream/beige backgrounds
        'ac-cream': '#F9F3E4',
        'ac-warm': '#F0E6D3',
        'ac-card': '#FFFDF7',
        // Nature greens
        'ac-leaf': '#7BC47F',
        'ac-leaf-dark': '#5EA862',
        'ac-mint': '#B5E6B5',
        // Sky
        'ac-sky': '#87CEEB',
        'ac-sky-light': '#D4EEF7',
        // Warm accents
        'ac-gold': '#F7BC4C',
        'ac-amber': '#E8A838',
        // Text
        'ac-brown': '#5D4037',
        'ac-brown-light': '#8D6E63',
        'ac-brown-dark': '#3E2723',
        // Borders and details
        'ac-tan': '#D4B896',
        'ac-tan-light': '#E8D5C0',
        // Accent colors
        'ac-pink': '#F8BBD0',
        'ac-peach': '#FFCCBC',
        // State colors
        'ac-idle': '#A1887F',
        'ac-active': '#7BC47F',
        'ac-processing': '#F7BC4C',
        'ac-speaking': '#87CEEB',
        'ac-error': '#EF9A9A',
      },
      fontFamily: {
        'body': ['Nunito', 'sans-serif'],
        'display': ['Fredoka', 'sans-serif'],
      },
      borderRadius: {
        'xl': '1rem',
        '2xl': '1.25rem',
        '3xl': '1.75rem',
        'bubble': '1.5rem',
      },
      boxShadow: {
        'ac-soft': '0 4px 16px rgba(93, 64, 55, 0.08), 0 1px 3px rgba(93, 64, 55, 0.04)',
        'ac-card': '0 2px 12px rgba(93, 64, 55, 0.06), 0 1px 2px rgba(93, 64, 55, 0.04), inset 0 1px 0 rgba(255,255,255,0.6)',
        'ac-hover': '0 6px 24px rgba(93, 64, 55, 0.12), 0 2px 6px rgba(93, 64, 55, 0.08)',
        'ac-button': '0 3px 0 rgba(93, 64, 55, 0.15)',
      },
      animation: {
        'float': 'float 3s ease-in-out infinite',
        'bounce-soft': 'bounceSoft 2s ease-in-out infinite',
        'slide-up': 'slideUp 0.4s cubic-bezier(0.16, 1, 0.3, 1)',
        'pop-in': 'popIn 0.3s cubic-bezier(0.34, 1.56, 0.64, 1)',
        'wiggle': 'wiggle 0.5s ease-in-out',
        'cloud-drift': 'cloudDrift 20s linear infinite',
        'leaf-fall': 'leafFall 4s ease-in-out infinite',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-6px)' },
        },
        bounceSoft: {
          '0%, 100%': { transform: 'translateY(0) scale(1)' },
          '50%': { transform: 'translateY(-4px) scale(1.02)' },
        },
        slideUp: {
          '0%': { transform: 'translateY(12px)', opacity: '0' },
          '100%': { transform: 'translateY(0)', opacity: '1' },
        },
        popIn: {
          '0%': { transform: 'scale(0.8)', opacity: '0' },
          '100%': { transform: 'scale(1)', opacity: '1' },
        },
        wiggle: {
          '0%, 100%': { transform: 'rotate(0deg)' },
          '25%': { transform: 'rotate(-3deg)' },
          '75%': { transform: 'rotate(3deg)' },
        },
        cloudDrift: {
          '0%': { transform: 'translateX(-20%)' },
          '100%': { transform: 'translateX(120%)' },
        },
        leafFall: {
          '0%': { transform: 'translateY(-10px) rotate(0deg)', opacity: '0' },
          '20%': { transform: 'translateY(0) rotate(5deg)', opacity: '1' },
          '80%': { transform: 'translateY(0) rotate(-5deg)', opacity: '1' },
          '100%': { transform: 'translateY(10px) rotate(0deg)', opacity: '0' },
        },
      },
    },
  },
  plugins: [],
}
