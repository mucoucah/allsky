/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Astronomy-friendly dark palette: deep neutrals + a single accent.
        bg: {
          base: "#0b0f17",
          panel: "#121826",
          raised: "#1a2233",
        },
        ink: {
          DEFAULT: "#e7ecf3",
          muted: "#9aa4b8",
          dim: "#64708a",
        },
        accent: {
          DEFAULT: "#ff8c42", // sodium-amber so it doesn't ruin night vision
          soft: "#ffb886",
        },
        ok: "#3dd68c",
        warn: "#ffd166",
        err: "#ff6b6b",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
};
