import type { Config } from "tailwindcss";

// Design tokens are declared once as CSS variables in app/globals.css (:root),
// lifted verbatim from mockups/portfolio-v3. Tailwind utilities below reference
// those vars so utility classes and hand-written component CSS never drift.
export default {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)",
        s1: "var(--s1)",
        s2: "var(--s2)",
        s3: "var(--s3)",
        line: "var(--line)",
        line2: "var(--line2)",
        tx: "var(--tx)",
        dim: "var(--dim)",
        accent: {
          DEFAULT: "var(--acc)", // blue #5B9CFF
          ink: "var(--acc-ink)",
        },
        green: "var(--green)",
        cyan: "var(--cyan)",
        amber: "var(--amber)",
      },
      fontFamily: {
        display: ["var(--font-display)", "Space Grotesk", "sans-serif"],
        body: ["var(--font-body)", "Manrope", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "JetBrains Mono", "monospace"],
      },
      maxWidth: {
        content: "1100px",
      },
      transitionTimingFunction: {
        corp: "cubic-bezier(0.2,0,0,1)",
      },
    },
  },
  plugins: [],
} satisfies Config;
