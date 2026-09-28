export type ThemePreference = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

/**
 * Run in <head> before first paint. Every new page load begins in light mode.
 * A visitor can still switch to dark mode for the current page session.
 */
export const THEME_BOOTSTRAP_SCRIPT = '(function(){var d=document.documentElement;d.dataset.theme="light";d.dataset.themePreference="light";})();';

export function readThemePreference(): ThemePreference {
  if (typeof document === "undefined") return "light";
  const value = document.documentElement.dataset.themePreference;
  return value === "dark" || value === "system" ? value : "light";
}

export function resolveTheme(preference: ThemePreference): ResolvedTheme {
  if (preference === "system" && typeof window !== "undefined") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return preference === "dark" ? "dark" : "light";
}

/** Apply a theme for this page session, with a short cross-fade when motion is allowed. */
export function applyThemePreference(preference: ThemePreference) {
  if (typeof window === "undefined") return;
  const root = document.documentElement;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reduced) {
    root.classList.add("theme-transition");
    window.setTimeout(() => root.classList.remove("theme-transition"), 220);
  }
  root.dataset.themePreference = preference;
  const resolved = resolveTheme(preference);
  root.dataset.theme = resolved;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", resolved === "dark" ? "#181f1d" : "#f6f5ef");
  window.dispatchEvent(new Event("omniops:theme-change"));
}

export const THEME_ORDER: ThemePreference[] = ["light", "dark", "system"];
