"use client";

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, Loader2, LogOut } from "lucide-react";
import useSWR from "swr";
import { apiClient } from "@/lib/api-client";
import type {
  AuthSession,
  InvestigationHistoryPage,
  SourceDocument,
  TabularDataset,
  User,
  Workspace,
} from "@/types/api";
import { ErrorState, LoadingState } from "@/components/ui/Primitives";
import { Dialog } from "@/components/ui/Dialog";
import { BrandLockup, ThemeToggle } from "@/components/casefile/Brand";
import { AuthExperience } from "@/components/auth/AuthExperience";
import "./home.css";
import { initials, StatusIcon } from "@/components/casefile/Rail";
import { SourceRow } from "@/components/casefile/SourceRow";
import { useOutlines } from "@/hooks/useCasefileData";

function relativeTime(value: string | null | undefined, now = Date.now()) {
  if (!value || !Number.isFinite(Date.parse(value))) return "";
  const seconds = Math.max(0, Math.round((now - Date.parse(value)) / 1000));
  if (seconds < 45) return "now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d`;
  return new Date(value).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function sinceLabel(value: string | null | undefined) {
  const short = relativeTime(value);
  if (!short) return "";
  if (short === "now") return "just now";
  const match = /^(\d+)([mhd])$/.exec(short);
  if (!match) return short;
  const unit = { m: "min", h: "h", d: "d" }[match[2] as "m" | "h" | "d"];
  return `${match[1]} ${unit} ago`;
}

const fetcher = <T,>(url: string) => apiClient.get<T>(url);

function WorkspaceCard({ workspace }: { workspace: Workspace }) {
  const { data: files } = useSWR<SourceDocument[]>(`/workspaces/${workspace.id}/files`, fetcher);
  const { data: tables } = useSWR<TabularDataset[]>(`/workspaces/${workspace.id}/tables`, fetcher);
  const { data: history } = useSWR<InvestigationHistoryPage>(`/workspaces/${workspace.id}/investigations?limit=3`, fetcher);
  const shown = (files ?? []).slice(0, 5);
  const { outlines } = useOutlines(workspace.id, shown);
  const processing = (files ?? []).filter((file) => ["pending", "processing"].includes(file.processing_status)).length;
  const last = history?.items[0];
  const summary = [
    files ? `${files.length} ${files.length === 1 ? "source" : "sources"}` : "Loading sources",
    processing ? `${processing} processing` : last ? `last question ${sinceLabel(last.created_at)}` : history ? "no questions yet" : null,
  ].filter(Boolean).join(" · ");
  return (
    <article className="casefile-card rev-workspace-card" aria-labelledby={`ws-${workspace.id}`}>
      <h2 id={`ws-${workspace.id}`} className="t-title truncate text-ink">{workspace.name}</h2>
      <p className="t-meta mt-1 text-ink-3">{summary}</p>

      <div className="min-h-[152px]">
        <p className="t-overline mt-[22px]">Sources</p>
        <div className="mt-2 flex flex-col">
        {files && files.length === 0 && <p className="t-meta py-1 text-ink-3">No sources yet.</p>}
        {shown.map((file) => (
          <SourceRow key={file.id} file={file} map={outlines[file.id]} tables={(tables ?? []).filter((table) => table.source_id === file.id)} height={6} indexedFull decorative compact right={["pending", "processing"].includes(file.processing_status) ? "Processing" : ""} />
        ))}
        {files && files.length > shown.length && <p className="t-meta pt-1 text-ink-3">+ {files.length - shown.length} more</p>}
        </div>
      </div>

      <div className="mt-[22px] border-t border-line pt-4">
        <p className="t-overline">Recent questions</p>
        <ul className="mt-2.5 flex flex-col gap-3">
          {history && history.items.length === 0 && <li className="t-meta text-ink-3">No investigations yet.</li>}
          {history?.items.map((item) => (
            <li key={item.id}>
              <Link href={`/workspaces/${workspace.id}?investigation=${item.id}`} className="grid grid-cols-[16px_minmax(0,1fr)_auto] items-start gap-x-2 rounded-control">
                <span className="pt-0.5"><StatusIcon status={item.status} /></span>
                <span className="t-label truncate text-ink">{item.objective}</span>
                <span className="t-meta pt-0.5 text-ink-3">{relativeTime(item.created_at)}</span>
                <span className={`t-meta col-start-2 mt-0.5 ${item.status === "failed" ? "text-caution" : "text-ink-3"}`}>
                  {item.status === "completed"
                    ? `Completed${item.completed_at ? ` · ${sinceLabel(item.completed_at)}` : ""}`
                    : item.status === "failed"
                      ? "Stopped before a brief was saved"
                      : item.status === "cancelled"
                        ? "Cancelled"
                        : `Running · started ${sinceLabel(item.created_at)}`}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </div>
      <span className="flex-1" />
      <Link href={`/workspaces/${workspace.id}`} className="t-label mt-6 self-start text-ink-2 hover:text-ink">
        Open workspace →
      </Link>
    </article>
  );
}

function Home({ user, onSignOut }: { user: User; onSignOut: () => void }) {
  const router = useRouter();
  const { data: workspaces, error, isLoading, mutate } = useSWR<Workspace[]>("/workspaces", fetcher);
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [menu, setMenu] = useState(false);
  const sourceTotal = (workspaces ?? []).reduce((sum, item) => sum + (item.documents_count ?? 0), 0);
  const sorted = [...(workspaces ?? [])].sort((a, b) => b.updated_at.localeCompare(a.updated_at));

  const create = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || !name.trim()) return;
    setBusy(true);
    setCreateError(null);
    try {
      const workspace = await apiClient.post<Workspace>("/workspaces", { name: name.trim() });
      router.push(`/workspaces/${workspace.id}`);
    } catch (err) {
      setCreateError(err instanceof Error ? err.message : "Workspace could not be created.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="min-h-dvh">
      <header className="border-b border-line">
        <div className="mx-auto flex h-[76px] max-w-[1248px] items-center justify-between gap-4 px-6">
          <BrandLockup />
          <div className="relative flex items-center gap-3">
            <ThemeToggle withLabel />
            <button type="button" className="t-meta rounded-control px-2 py-1 text-ink-2 hover:text-ink" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu((value) => !value)} aria-label={`Account: ${user.email}`}>
              {initials(user)}
            </button>
            {menu && (
              <div role="menu" className="absolute right-0 top-[calc(100%+6px)] z-30 w-60 rounded-control border border-line-strong bg-surface p-1" style={{ boxShadow: "var(--elevation-pane)" }}>
                <p className="t-meta truncate px-2.5 py-2 text-ink-3">{user.email}</p>
                <button type="button" role="menuitem" className="rail-item" onClick={onSignOut}>
                  <LogOut className="h-4 w-4" aria-hidden="true" />
                  <span className="rail-item-label">Sign out</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </header>
      <main id="main-content" className="rev-home-main">
        <section className="rev-home-hero"><div><span className="rev-home-kicker">YOUR INVESTIGATIONS</span><h1>What would you like<br/>to understand next?</h1><p>Choose a workspace, add material, and ask a question worth tracing back.</p><div className="rev-home-actions">{sorted[0] && <Link href={`/workspaces/${sorted[0].id}`} className="rev-home-hero-link">Open {sorted[0].name} <span>↗</span></Link>}<button type="button" onClick={() => { setCreateOpen(true); setCreateError(null); }}>Create a workspace <span>+</span></button></div></div><div className="rev-home-art" aria-hidden="true"><span className="rev-home-paper a"/><span className="rev-home-paper b"/><span className="rev-home-paper c"/><span className="rev-home-art-line"/><span className="rev-home-art-dot"/></div></section>
        {error && (
          <div className="mt-6">
            <ErrorState message={error instanceof Error ? error.message : "Workspaces could not be loaded."} onRetry={() => void mutate()} />
          </div>
        )}
        <div className="rev-home-section-title"><div><h2>Pick up where you left off</h2><p>{workspaces ? `${workspaces.length} ${workspaces.length === 1 ? "workspace" : "workspaces"} · ${sourceTotal} ${sourceTotal === 1 ? "source" : "sources"}` : "Loading workspaces"}</p></div><button type="button" onClick={() => setCreateOpen(true)}>New workspace +</button></div>
        {isLoading ? (
          <div className="mt-10"><LoadingState label="Loading workspaces" /></div>
        ) : sorted.length === 0 && !error ? (
          <div className="mt-10 rounded-pane border border-dashed border-line-strong p-10 text-center">
            <p className="r-heading text-ink">Start a casefile</p>
            <p className="t-body mx-auto mt-2 max-w-md text-ink-2">A workspace keeps related sources and investigations together. Create one, then add your first source.</p>
            <button type="button" className="btn-primary mt-5" onClick={() => setCreateOpen(true)}>New workspace</button>
          </div>
        ) : (
          <div className="rev-workspace-grid">
            {sorted.map((workspace) => <WorkspaceCard key={workspace.id} workspace={workspace} />)}
          </div>
        )}
        {sorted.length > 0 && (
          <p className="t-meta mt-6 text-ink-3">Each segment is one indexed passage. Spreadsheets appear as tables. A dashed outline means the source is still processing.</p>
        )}
      </main>
      <Dialog compact open={createOpen} onClose={() => setCreateOpen(false)} title="New workspace" description="Group the sources for an investigation." busy={busy}>
        <form onSubmit={create} className="space-y-5">
          <div>
            <label htmlFor="workspace-name" className="field-label">Workspace name</label>
            <input id="workspace-name" autoFocus required maxLength={255} value={name} onChange={(event) => setName(event.target.value)} placeholder="e.g. Quarterly operating review" className="field" aria-describedby={createError ? "create-error" : undefined} />
          </div>
          {createError && <div id="create-error"><ErrorState message={createError} /></div>}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={() => setCreateOpen(false)} disabled={busy} className="btn-secondary">Cancel</button>
            <button disabled={busy || !name.trim()} className="btn-primary">{busy && <Loader2 className="h-4 w-4 animate-spin" />}Create workspace</button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}

/** Decorative motif: rows of passages, three threads converging on one answer. */
function TraceMotif() {
  const rows = 13;
  const seeded = (row: number, index: number) => ((row * 73 + index * 37) % 11) / 11;
  const cited: Record<number, number> = { 3: 0.38, 7: 0.55, 10: 0.74 };
  return (
    <svg className="absolute inset-0 h-full w-full" viewBox="0 0 880 900" preserveAspectRatio="xMinYMid slice" aria-hidden="true" focusable="false">
      {Array.from({ length: rows }, (_, row) => {
        const y = 150 + row * 40;
        const segments: Array<{ x: number; w: number }> = [];
        let x = 0;
        let index = 0;
        while (x < 390) {
          const w = 4 + seeded(row, index) * 14;
          segments.push({ x, w });
          x += w + 3;
          index += 1;
        }
        const target = cited[row];
        const hit = target != null ? segments[Math.floor(segments.length * target)] : null;
        return (
          <g key={row}>
            {segments.map((segment, i) => (
              <rect key={i} x={segment.x} y={y} width={segment.w} height="5" rx="1.5" fill={segment === hit ? "var(--provenance)" : "var(--track-indexed)"} />
            ))}
            {hit && <path d={`M${hit.x + hit.w} ${y + 2.5} C ${hit.x + 260} ${y + 2.5}, ${480} 443, 598 443`} fill="none" stroke="var(--provenance)" strokeWidth="1" />}
          </g>
        );
      })}
      <circle cx="598" cy="443" r="3.5" fill="var(--provenance)" />
    </svg>
  );
}

function SignIn({ expired, onAuthenticated }: { expired: boolean; onAuthenticated: (user: User) => void }) {
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const authenticate = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await apiClient.post<AuthSession>(isLogin ? "/auth/login" : "/auth/register", isLogin ? { email, password } : { email, password, full_name: fullName });
      apiClient.setToken(result.token.access_token);
      setPassword("");
      onAuthenticated(result.user);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed. Check your details and try again.");
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="auth-grid">
      <div className="auth-panel-b">
        <BrandLockup />
        <main id="main-content" className="my-auto w-full max-w-[368px] pb-[94px] pt-12">
          <h1 className="r-title text-ink">{isLogin ? "Sign in" : "Create your account"}</h1>
          <p className="t-body mt-2.5 text-ink-2">{isLogin ? "Continue to your casefiles." : "Start a casefile for your sources."}</p>
          {expired && (
            <p role="status" className="t-meta mt-5 rounded-control border border-line-strong p-3 text-ink-2">Your session has ended. Sign in to continue.</p>
          )}
          <form onSubmit={authenticate} aria-busy={busy} className="mt-8 space-y-7">
            {!isLogin && (
              <div>
                <label htmlFor="full-name" className="field-label">Full name</label>
                <input id="full-name" autoComplete="name" required value={fullName} onChange={(event) => setFullName(event.target.value)} className="field h-11" />
              </div>
            )}
            <div>
              <label htmlFor="email" className="field-label">Email</label>
              <input id="email" type="email" autoComplete="username" required value={email} onChange={(event) => setEmail(event.target.value)} className="field h-11" aria-describedby={error ? "auth-error" : undefined} />
            </div>
            <div>
              <label htmlFor="password" className="field-label">Password</label>
              <div className="relative">
                <input id="password" type={showPassword ? "text" : "password"} autoComplete={isLogin ? "current-password" : "new-password"} required value={password} onChange={(event) => setPassword(event.target.value)} className="field h-11 pr-12" aria-describedby={error ? "auth-error" : undefined} />
                <button type="button" className="btn-icon absolute right-1.5 top-1.5" aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword} onClick={() => setShowPassword((value) => !value)}>
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>
            {error && <div id="auth-error"><ErrorState title="Unable to sign in" message={error} /></div>}
            <button disabled={busy} className="btn-primary !mt-9 h-11 w-full">
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}
              {busy ? (isLogin ? "Signing in…" : "Creating account…") : isLogin ? "Sign in" : "Create account"}
            </button>
            <p role="status" className="sr-only">{busy ? (isLogin ? "Signing in" : "Creating account") : ""}</p>
          </form>
          <p className="t-label mt-6 text-ink-2">
            {isLogin ? "New here?" : "Already have an account?"}{" "}
            <button type="button" disabled={busy} onClick={() => { setIsLogin(!isLogin); setError(null); }} className="ml-1 text-ink underline-offset-4 hover:underline">
              {isLogin ? "Create an account" : "Sign in"}
            </button>
          </p>
        </main>
        <p className="t-meta text-ink-3">Sessions are short-lived and rotate automatically.</p>
      </div>
      <div className="auth-motif">
        <TraceMotif />
        <p className="r-title absolute max-w-[240px] text-ink" style={{ left: "calc(598 / 880 * 100% + 14px)", top: "calc(50% - 26px)" }}>
          Every answer, traced to the passage it came from.
        </p>
      </div>
    </div>
  );
}

export default function HomePage() {
  const router = useRouter();
  const [restoring, setRestoring] = useState(true);
  const [user, setUser] = useState<User | null>(null);
  const [expired, setExpired] = useState(false);
  const [restoreError, setRestoreError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setExpired(new URLSearchParams(window.location.search).get("session") === "expired");
    document.title = "OmniOps";
    void (async () => {
      try {
        const authenticated = Boolean(apiClient.getAccessToken()) || (await apiClient.refresh());
        if (authenticated) {
          const current = await apiClient.get<User>("/auth/me");
          if (alive) {
            setUser(current);
            const target = new URLSearchParams(window.location.search).get("next");
            if (target?.startsWith("/workspaces/") && !target.startsWith("//")) router.replace(target);
          }
        }
      } catch (err) {
        if (alive) setRestoreError(err instanceof Error ? err.message : "Could not restore your session. Please try again.");
      } finally {
        if (alive) setRestoring(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [router]);

  const signOut = useCallback(async () => {
    try {
      await apiClient.logout();
    } finally {
      // Drop all protected component and SWR state before another account signs in.
      window.location.replace("/login");
    }
  }, []);

  if (restoring)
    return (
      <main id="main-content" className="flex min-h-dvh items-center justify-center p-6">
        <div className="w-full max-w-sm space-y-8">
          <BrandLockup />
          <LoadingState label="Restoring your casefiles" />
        </div>
      </main>
    );
  if (!user)
    return (
      <>
        {restoreError && <p className="sr-only" role="alert">{restoreError}</p>}
        <AuthExperience mode="login" expired={expired} onAuthenticated={(nextUser) => {
          setExpired(false);
          setUser(nextUser);
          const target = new URLSearchParams(window.location.search).get("next");
          if (target?.startsWith("/workspaces/") && !target.startsWith("//")) router.replace(target);
        }} />
      </>
    );
  return <Home user={user} onSignOut={() => void signOut()} />;
}
