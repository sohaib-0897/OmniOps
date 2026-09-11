import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatBytes(bytes: number, decimals = 2): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "Unavailable";
  if (bytes === 0) return "0 B";
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ["B", "KB", "MB", "GB"];
  const i = Math.min(
    sizes.length - 1,
    Math.max(0, Math.floor(Math.log(bytes) / Math.log(k))),
  );
  return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
}

export const formatNumber = (value: number) =>
  new Intl.NumberFormat(undefined, { maximumFractionDigits: 4 }).format(value);
export function formatDate(value?: string) {
  if (!value || !Number.isFinite(Date.parse(value))) return "Date unavailable";
  return new Date(value).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}
export function formatDuration(ms?: number | null) {
  if (ms == null || !Number.isFinite(ms)) return "Not recorded";
  const seconds = Math.max(0, ms / 1000);
  return seconds < 60
    ? `${formatNumber(seconds)}s`
    : `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`;
}
