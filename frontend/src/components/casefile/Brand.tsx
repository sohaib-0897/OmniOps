"use client";

import { useEffect, useState } from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import {
  applyThemePreference,
  readThemePreference,
  THEME_ORDER,
  type ThemePreference,
} from "@/lib/theme";

/**
 * Brand/Mark (Figma 4:84): a citation bracket enclosing a highlighted passage.
 * Geometry is the exported asset; colours are bound to tokens so the mark
 * follows the theme.
 */
export function BrandMark({ size = 24 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden="true" className="shrink-0">
      <path d="M8 3H4V21H8" stroke="var(--ink)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M16 3H20V21H16" stroke="var(--ink)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="8" y="9" width="8" height="6" rx="1.5" fill="var(--provenance)" />
    </svg>
  );
}

export function BrandLockup({ size = 24 }: { size?: number }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <BrandMark size={size} />
      <span className="t-body-strong text-ink">OmniOps</span>
    </span>
  );
}

const icons = { system: Monitor, light: Sun, dark: Moon } as const;
const labels = { system: "System", light: "Light", dark: "Dark" } as const;

export function useThemePreference() {
  const [preference, setPreference] = useState<ThemePreference>("system");
  useEffect(() => {
    setPreference(readThemePreference());
    const media = window.matchMedia("(prefers-color-scheme: light)");
    const follow = () => {
      if (readThemePreference() === "system") applyThemePreference("system");
    };
    media.addEventListener("change", follow);
    return () => media.removeEventListener("change", follow);
  }, []);
  const choose = (value: ThemePreference) => {
    setPreference(value);
    applyThemePreference(value);
  };
  return { preference, choose };
}

/** Cycles System → Light → Dark. The label always states the current choice. */
export function ThemeToggle({ withLabel = false }: { withLabel?: boolean }) {
  const { preference, choose } = useThemePreference();
  const next = THEME_ORDER[(THEME_ORDER.indexOf(preference) + 1) % THEME_ORDER.length];
  const Icon = icons[preference];
  return (
    <button
      type="button"
      className={withLabel ? "btn-ghost h-8 px-2 text-[12px] !font-normal text-ink-3" : "btn-icon"}
      onClick={() => choose(next)}
      aria-label={`Theme: ${labels[preference]}. Switch to ${labels[next]}.`}
      title={`Theme: ${labels[preference]}`}
    >
      {withLabel ? <span>Theme: {labels[preference]}</span> : <Icon className="h-4 w-4" aria-hidden="true" />}
    </button>
  );
}
