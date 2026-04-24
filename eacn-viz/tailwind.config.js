/** @type {import('tailwindcss').Config} */
export default {
  content: ["./src/web/**/*.{ts,tsx,html}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Sora"', 'system-ui', 'sans-serif'],
        mono: ['"IBM Plex Mono"', 'monospace'],
      },
      colors: {
        cream: {
          50: "#fffcf6",
          100: "#fbf8f2",
          200: "#f5f0e6",
          300: "#f2ebdf",
          400: "#e8dfd0",
        },
        teal: {
          DEFAULT: "#0f766e",
          light: "#16a394",
          dark: "#0d5f59",
        },
        terracotta: {
          DEFAULT: "#df6d2d",
          light: "#e8884f",
          dark: "#b85a24",
        },
        navy: {
          DEFAULT: "#174066",
          light: "#1e5a8f",
          dark: "#0f2d47",
        },
      },
    },
  },
  plugins: [],
};
