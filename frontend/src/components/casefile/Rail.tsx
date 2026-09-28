"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  Check,
  ChevronDown,
  Clock,
  FileText,
  LogOut,
  Menu,
  Minus,
  PanelLeft,
  Plus,
} from "lucide-react";
import useSWR from "swr";
import { apiClient } from "@/lib/api-client";
import type { InvestigationSummary, User, Workspace } from "@/types/api";
import { BrandLockup, BrandMark, ThemeToggle } from "./Brand";

export type WorkspaceView = "ask" | "investigation" | "sources";

export function StatusIcon({ status }: { status: string }) {
  if (status === "completed") return <Check className="h-4 w-4 shrink-0 text-provenance" aria-label="Completed" />;
  if (status === "failed") return <AlertCircle className="h-4 w-4 shrink-0 text-caution" aria-label="Stopped" />;
  if (status === "cancelled") return <Minus className="h-4 w-4 shrink-0 text-ink-3" aria-label="Cancelled" />;
  return <Clock className="h-4 w-4 shrink-0 text-ink-2" aria-label="Running" />;
}

function dayLabel(value: string, now = new Date()): string {
  const date = new Date(value);
  const startOf = (d: Date) => new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime();
  const days = Math.round((startOf(now) - startOf(date)) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 7) return date.toLocaleDateString(undefined, { weekday: "long" });
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric", year: date.getFullYear() === now.getFullYear() ? undefined : "numeric" });
}

export function groupByDay(items: InvestigationSummary[]) {
  const groups: Array<{ label: string; items: InvestigationSummary[] }> = [];
  for (const item of items) {
    const label = dayLabel(item.created_at);
    const group = groups[groups.length - 1];
    if (group && group.label === label) group.items.push(item);
    else groups.push({ label, items: [item] });
  }
  return groups;
}

export function initials(user: Pick<User, "full_name" | "email"> | null | undefined) {
  const source = user?.full_name?.trim() || user?.email || "";
  const parts = source.split(/[\s@._-]+/).filter(Boolean);
  return ((parts[0]?.[0] ?? "") + (parts[1]?.[0] ?? "")).toUpperCase() || "·";
}

function WorkspaceSwitcher({ workspace, readyLabel }: { workspace: Workspace; readyLabel: string }) {
  const [open, setOpen] = useState(false);
  const { data: workspaces } = useSWR<Workspace[]>(open ? "/workspaces" : null, (url: string) => apiClient.get<Workspace[]>(url));
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      if (!box.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);
  return (
    <div ref={box} className="rail-hide-collapsed relative w-full">
      <button
        type="button"
        className="flex w-full items-center gap-2 rounded-control border border-line px-2.5 py-2 text-left hover:bg-raised"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => event.key === "Escape" && setOpen(false)}
      >
        <span className="min-w-0 flex-1">
          <span className="t-body-strong block truncate text-ink">{workspace.name}</span>
          <span className="t-meta block truncate text-ink-3">{readyLabel}</span>
        </span>
        <ChevronDown className="h-4 w-4 shrink-0 text-ink-2" aria-hidden="true" />
      </button>
      {open && (
        <div role="menu" className="absolute left-0 right-0 top-[calc(100%+4px)] z-30 rounded-control border border-line-strong bg-surface p-1" style={{ boxShadow: "var(--elevation-pane)" }}>
          {(workspaces ?? []).map((item) => (
            <Link
              key={item.id}
              role="menuitem"
              href={`/workspaces/${item.id}`}
              className="rail-item"
              aria-current={item.id === workspace.id ? "true" : undefined}
              onClick={() => setOpen(false)}
            >
              <span className="rail-item-label">{item.name}</span>
            </Link>
          ))}
          {!workspaces && <p className="t-meta px-2.5 py-2 text-ink-3">Loading workspaces…</p>}
          <div className="my-1 border-t border-line" />
          <Link role="menuitem" href="/app" className="rail-item" onClick={() => setOpen(false)}>
            <span className="rail-item-label">All casefiles</span>
          </Link>
        </div>
      )}
    </div>
  );
}

function AccountRow({ collapsed }: { collapsed?: boolean }) {
  const { data: user } = useSWR<User>("/auth/me", (url: string) => apiClient.get<User>(url), { revalidateOnFocus: false });
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const logout = async () => {
    setBusy(true);
    try {
      await apiClient.logout();
    } finally {
      // Drop all protected component and SWR state before another sign-in.
      window.location.replace("/login");
    }
  };
  return (
    <div className="relative flex w-full items-center gap-2.5 py-1.5 pl-2.5 pr-1" data-collapsed={collapsed || undefined}>
      <button
        type="button"
        className="flex min-w-0 flex-1 items-center gap-2.5 rounded-control text-left"
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-raised text-[11px] leading-4 text-ink-2" aria-hidden="true">
          {initials(user)}
        </span>
        <span className="rail-hide-collapsed t-body min-w-0 flex-1 truncate text-ink-2">{user?.full_name || user?.email || "Account"}</span>
      </button>
      <span className="rail-hide-collapsed">
        <ThemeToggle />
      </span>
      {open && (
        <div role="menu" className="absolute bottom-[calc(100%+4px)] left-0 z-30 w-56 rounded-control border border-line-strong bg-surface p-1" style={{ boxShadow: "var(--elevation-pane)" }}>
          {user?.email && <p className="t-meta truncate px-2.5 py-2 text-ink-3">{user.email}</p>}
          <button type="button" role="menuitem" className="rail-item" disabled={busy} onClick={() => void logout()}>
            <LogOut className="h-4 w-4" aria-hidden="true" />
            <span className="rail-item-label">{busy ? "Signing out…" : "Sign out"}</span>
          </button>
        </div>
      )}
    </div>
  );
}

export interface RailProps {
  workspace: Workspace;
  sourceCount: number;
  readyCount: number;
  history: InvestigationSummary[];
  historyLoading?: boolean;
  activeInvestigationId: string | null;
  view: WorkspaceView;
  running: boolean;
  collapsed: boolean;
  drawerOpen: boolean;
  onToggleCollapsed: () => void;
  onCloseDrawer: () => void;
  onNewInvestigation: () => void;
  onOpenSources: () => void;
  onOpenInvestigation: (id: string) => void;
}

export function Rail(props: RailProps) {
  const {
    workspace,
    sourceCount,
    readyCount,
    history,
    historyLoading,
    activeInvestigationId,
    view,
    collapsed,
    drawerOpen,
  } = props;
  const readyLabel =
    sourceCount === 0 ? "No sources yet" : readyCount === sourceCount ? `${sourceCount} ${sourceCount === 1 ? "source" : "sources"} ready` : `${readyCount} of ${sourceCount} sources ready`;
  const groups = groupByDay(history);
  const pick = (action: () => void) => () => {
    action();
    props.onCloseDrawer();
  };
  return (
    <>
      {drawerOpen && <div className="rail-scrim" onClick={props.onCloseDrawer} aria-hidden="true" />}
      <nav
        className="rail"
        aria-label="Workspace"
        data-collapsed={collapsed || undefined}
        data-drawer={drawerOpen ? "open" : undefined}
        onKeyDown={(event) => drawerOpen && event.key === "Escape" && props.onCloseDrawer()}
      >
        <div className="flex w-full items-center gap-2.5 py-1 pl-2">
          <Link href="/app" className="rail-hide-collapsed rounded-control" aria-label="OmniOps casefiles">
            <BrandLockup />
          </Link>
          {collapsed && (
            <Link href="/app" className="rounded-control" aria-label="OmniOps casefiles">
              <BrandMark />
            </Link>
          )}
          <span className="rail-hide-collapsed flex-1" />
          <button
            type="button"
            className="btn-icon rail-hide-collapsed hidden lg:inline-flex"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-pressed={collapsed}
            onClick={props.onToggleCollapsed}
          >
            <PanelLeft className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        {collapsed && (
          <button type="button" className="btn-icon" aria-label="Expand sidebar" onClick={props.onToggleCollapsed}>
            <PanelLeft className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
        <WorkspaceSwitcher workspace={workspace} readyLabel={readyLabel} />
        <div className="h-2" />
        <button
          type="button"
          className="btn-secondary w-full justify-start px-3"
          onClick={pick(props.onNewInvestigation)}
          aria-label="New investigation"
          aria-current={view === "ask" ? "page" : undefined}
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          <span className="rail-hide-collapsed">New investigation</span>
        </button>
        <button
          type="button"
          className="rail-item"
          aria-current={view === "sources" ? "page" : undefined}
          onClick={pick(props.onOpenSources)}
          aria-label={`Sources, ${sourceCount}`}
        >
          <FileText className="h-4 w-4 shrink-0" aria-hidden="true" />
          <span className="rail-item-label rail-hide-collapsed">Sources</span>
          <span className="t-meta rail-hide-collapsed text-ink-3">{sourceCount}</span>
        </button>
        <div className="h-4" />
        <div className="rail-scroll rail-hide-collapsed w-full" aria-label="Investigations">
          {historyLoading && history.length === 0 && <p className="rail-group-label">Loading history…</p>}
          {!historyLoading && history.length === 0 && <p className="rail-group-label">No investigations yet</p>}
          {groups.map((group) => (
            <div key={group.label} role="group" aria-label={group.label}>
              <p className="rail-group-label">{group.label}</p>
              <ul className="flex flex-col gap-0.5">
                {group.items.map((item) => {
                  const current = view === "investigation" && item.id === activeInvestigationId;
                  return (
                    <li key={item.id}>
                      <button
                        type="button"
                        className="rail-item"
                        aria-current={current ? "page" : undefined}
                        onClick={pick(() => props.onOpenInvestigation(item.id))}
                        title={item.objective}
                      >
                        {current && <span className="rail-item-marker" aria-hidden="true" />}
                        <StatusIcon status={item.status} />
                        <span className={`rail-item-label ${current ? "text-ink" : ""}`}>{item.objective}</span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </div>
        {collapsed && <div className="flex-1" />}
        <AccountRow collapsed={collapsed} />
      </nav>
    </>
  );
}

export function MobileBar({ title, onMenu }: { title: string; onMenu: () => void }) {
  return (
    <header className="mobile-bar">
      <button type="button" className="btn-icon" aria-label="Open navigation" onClick={onMenu}>
        <Menu className="h-4 w-4" aria-hidden="true" />
      </button>
      <span className="t-body min-w-0 flex-1 truncate text-ink">{title}</span>
    </header>
  );
}
