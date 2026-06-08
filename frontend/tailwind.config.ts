import type { Config } from "tailwindcss";

export default {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Enterprise design language: near-black base + one energy-green accent
        surface: {
          DEFAULT: "#0a0a0b",
          raised: "#131316",
          border: "#26262b",
        },
        accent: {
          DEFAULT: "#10b981", // energy green
          soft: "#10b98122",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
} satisfies Config;
