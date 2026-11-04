/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['"Be Vietnam Pro"', 'system-ui', 'Segoe UI', 'Arial', 'sans-serif'],
      },
      colors: {
        brand: { 50: '#eef4fa', 100: '#d6e4f1', 300: '#8db0d3', 500: '#2f6aa3', 600: '#1f4e79', 700: '#173b5c' },
      },
    },
  },
  plugins: [],
};
