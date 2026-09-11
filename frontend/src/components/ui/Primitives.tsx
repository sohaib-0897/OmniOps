import React from "react";
import {
  Inbox,
  AlertCircle,
  Check,
  Clock3,
  Minus,
  AlertTriangle,
} from "lucide-react";
import { cn } from "@/lib/utils";

export function BrandMark({ compact = false }: { compact?: boolean }) {
  return (
    <div className={cn("flex items-center gap-2.5", compact && "gap-2")}>
      <span
        className="flex h-8 w-8 items-center justify-center rounded-md border border-zinc-700 bg-zinc-100 text-zinc-950"
        aria-hidden="true"
      >
        <span className="h-3 w-3 rounded-[2px] border-2 border-zinc-950" />
      </span>
      <span className="leading-none">
        <span className="block text-sm font-semibold tracking-tight text-zinc-100">
          OmniOps
        </span>
        {!compact && (
          <span className="mt-1 block text-[11px] text-zinc-400">
            Evidence intelligence
          </span>
        )}
      </span>
    </div>
  );
}

export function StatusBadge({
  status,
  label,
}: {
  status?: string | null;
  label?: string;
}) {
  const normalized = (status || "idle").toLowerCase();
  const success = ["completed", "ready", "verified"].includes(normalized);
  const failure = ["failed", "rejected"].includes(normalized);
  const warning = [
    "partially_ready",
    "partial",
    "conflicting",
    "insufficient_evidence",
  ].includes(normalized);
  const Icon = success
    ? Check
    : failure
      ? AlertCircle
      : warning
        ? AlertTriangle
        : normalized === "cancelled" || normalized === "idle"
          ? Minus
          : Clock3;
  const tone = failure
    ? "border-red-900/70 text-red-300"
    : warning
      ? "border-amber-900/70 text-amber-200"
      : "border-zinc-700 text-zinc-300";
  const labels: Record<string, string> = {
    partially_ready: "Partially ready",
    in_progress: "Running",
    idle: "Not started",
  };
  const display = label || labels[normalized] || normalized.replace(/_/g, " ");
  return (
    <span
      className={cn(
        "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded border bg-zinc-950/40 px-2 py-1 text-[11px] font-medium capitalize",
        tone,
      )}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      {display}
    </span>
  );
}

export function SectionHeader({
  eyebrow,
  title,
  description,
  action,
}: {
  eyebrow?: string;
  title: string;
  description?: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        {eyebrow && <p className="eyebrow mb-1.5">{eyebrow}</p>}
        <h2 className="section-title">{title}</h2>
        {description && (
          <p className="meta-copy mt-1 max-w-2xl">{description}</p>
        )}
      </div>
      {action}
    </div>
  );
}

export function EmptyState({
  icon: Icon = Inbox,
  title,
  description,
  action,
}: {
  icon?: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="surface-muted flex min-h-36 flex-col items-center justify-center gap-2 px-5 py-8 text-center">
      <span className="flex h-9 w-9 items-center justify-center rounded-md border border-zinc-700 bg-zinc-950 text-zinc-400">
        <Icon className="h-4 w-4" />
      </span>
      <h3 className="text-sm font-medium text-zinc-200">{title}</h3>
      <p className="max-w-sm text-xs leading-5 text-zinc-400">{description}</p>
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" className="surface space-y-4 p-5">
      <p className="meta-copy">{label}</p>
      <div aria-hidden="true" className="loading-pulse space-y-3">
        <div className="h-3 w-2/3 rounded bg-zinc-800" />
        <div className="h-3 w-full rounded bg-zinc-800/60" />
        <div className="h-3 w-1/2 rounded bg-zinc-800/60" />
      </div>
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
  title = "Something needs attention",
}: {
  message: string;
  onRetry?: () => void;
  title?: string;
}) {
  return (
    <div
      role="alert"
      className="rounded-md border border-red-900/70 bg-red-950/20 px-4 py-3 text-xs text-red-200"
    >
      <div className="flex items-start gap-2">
        <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
        <div className="min-w-0">
          <p className="font-medium">{title}</p>
          <p className="mt-1 break-words leading-5">{message}</p>
          {onRetry && (
            <button
              type="button"
              onClick={onRetry}
              className="mt-2 underline underline-offset-4 hover:text-white"
            >
              Try again
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
