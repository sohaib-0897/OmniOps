import type { Config } from "tailwindcss";

const token = (name: string) => `rgb(var(--${name}-rgb) / <alpha-value>)`;

/*
 * The neutral scale is remapped onto the Concept B tokens so every retained
 * utility (zinc-*, red-*, amber-*) follows the active theme. New components use
 * the semantic names (canvas, surface, ink, provenance…).
 */
const neutral = {
  50: token("ink"),
  100: token("ink"),
  200: token("ink"),
  300: token("ink-2"),
  400: token("ink-3"),
  500: token("ink-3"),
  600: token("line-strong"),
  700: token("line-strong"),
  800: token("line"),
  900: token("raised"),
  950: token("canvas"),
};
const critical = Object.fromEntries(
  [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950].map((step) => [step, token("critical")]),
);
const caution = Object.fromEntries(
  [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950].map((step) => [step, token("caution")]),
);

const config: Config = {
  darkMode: ["selector", '[data-theme="dark"]'],
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        zinc: neutral,
        neutral,
        red: critical,
        amber: caution,
        canvas: token("canvas"),
        surface: token("surface"),
        raised: token("raised"),
        line: { DEFAULT: token("line"), strong: token("line-strong") },
        ink: { DEFAULT: token("ink"), 2: token("ink-2"), 3: token("ink-3"), inverse: token("ink-inverse") },
        provenance: { DEFAULT: token("provenance"), strong: token("provenance-strong") },
        caution: token("caution"),
        critical: token("critical"),
        border: token("line"),
      },
      fontFamily: {
        sans: ["var(--font-ui)"],
        serif: ["var(--font-reading)"],
        mono: ["var(--font-code)"],
      },
      borderRadius: {
        control: "var(--radius-control)",
        chip: "var(--radius-chip)",
        pane: "var(--radius-pane)",
        composer: "var(--radius-composer)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
export default config;
