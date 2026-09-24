export type ThemePreference = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "omniops-theme";

/**
 * Runs inline in <head> before first paint. It only reads a UI preference;
 * no credentials or application data are stored client-side.
 */
export const THEME_BOOTSTRAP_SCRIPT = `(function(){try{var k="${THEME_STORAGE_KEY}",p=localStorage.getItem(k);if(p!=="light"&&p!=="dark")p="system";var m=window.matchMedia("(prefers-color-scheme: light)");var r=p==="system"?(m.matches?"light":"dark"):p;var d=document.documentElement;d.dataset.theme=r;d.dataset.themePreference=p;}catch(e){}})();`;

export function readThemePreference(): ThemePreference {
  if (typeof window === "undefined") return "system";
  try {
    const value = window.localStorage.getItem(THEME_STORAGE_KEY);
    return value === "light" || value === "dark" ? value : "system";
  } catch {
    return "system";
  }
}

export function resolveTheme(preference: ThemePreference, systemPrefersLight: boolean): ResolvedTheme {
  if (preference === "system") return systemPrefersLight ? "light" : "dark";
  return preference;
}

/** Apply a preference with a short token cross-fade (skipped under reduced motion). */
export function applyThemePreference(preference: ThemePreference) {
  if (typeof window === "undefined") return;
  try {
    if (preference === "system") window.localStorage.removeItem(THEME_STORAGE_KEY);
    else window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    /* storage may be unavailable; the choice still applies for this page */
  }
  const root = document.documentElement;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reduced) {
    root.classList.add("theme-transition");
    window.setTimeout(() => root.classList.remove("theme-transition"), 220);
  }
  root.dataset.themePreference = preference;
  root.dataset.theme = resolveTheme(
    preference,
    window.matchMedia("(prefers-color-scheme: light)").matches,
  );
}

export const THEME_ORDER: ThemePreference[] = ["system", "light", "dark"];
