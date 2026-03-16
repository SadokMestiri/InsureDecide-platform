/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx}",
    "./components/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["'DM Sans'", "sans-serif"],
        display: ["'Geist'", "sans-serif"],
        mono: ["'Geist Mono'", "monospace"],
      },
      colors: {
        slate: {
          850: "#172033",
        },
        brand: {
          50:  "#eff6ff",
          100: "#dbeafe",
          500: "#3b82f6",
          600: "#2563eb",
          700: "#1d4ed8",
          900: "#1e3a8a",
        },
        amber: {
          400: "#fbbf24",
          500: "#f59e0b",
        }
      },
    },
  },
  plugins: [],
};
