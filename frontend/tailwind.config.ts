import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        akfa: {
          red: "#d71920",
          ink: "#18181b",
          muted: "#6b7280",
          line: "#e5e7eb",
          soft: "#f7f7f8",
          green: "#0f8f5f",
          gold: "#b88900"
        }
      },
      boxShadow: {
        panel: "0 16px 40px rgba(15, 23, 42, 0.08)"
      }
    }
  },
  plugins: []
} satisfies Config;

