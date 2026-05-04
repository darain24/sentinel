import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        sentinel: {
          bg: "#0A0E1A",
          card: "#0F1629",
          cyan: "#00D4FF",
          warn: "#FF6B35",
          crit: "#FF2D55",
          ok: "#00E676",
          muted: "#6B7A9F",
          border: "#1E2A45",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "ui-monospace", "monospace"],
        body: ["var(--font-body)", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};
export default config;
