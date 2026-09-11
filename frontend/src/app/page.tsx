"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type FormEvent,
} from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ArrowRight,
  Database,
  FileText,
  Layers3,
  Loader2,
  Plus,
  Search,
  Eye,
  EyeOff,
} from "lucide-react";
import { apiClient } from "@/lib/api-client";
import { formatDate } from "@/lib/utils";
import { AuthSession, User, Workspace } from "@/types/api";
import {
  BrandMark,
  EmptyState,
  ErrorState,
  LoadingState,
} from "@/components/ui/Primitives";
import { Dialog } from "@/components/ui/Dialog";

export default function HomePage() {
  const router = useRouter();
  const [restoring, setRestoring] = useState(true);
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [fullName, setFullName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [createOpen, setCreateOpen] = useState(false);
  const [name, setName] = useState("");
  const [createError, setCreateError] = useState<string | null>(null);
  const [expired, setExpired] = useState(false);
  const load = useCallback(async () => {
    setLoading(true);
    try {
      const items = await apiClient.get<Workspace[]>("/workspaces");
      setWorkspaces(items);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Workspaces could not be loaded.",
      );
    } finally {
      setLoading(false);
    }
  }, []);
  useEffect(() => {
    let alive = true;
    setExpired(
      new URLSearchParams(window.location.search).get("session") === "expired",
    );
    void (async () => {
      try {
        const authenticated =
          Boolean(apiClient.getAccessToken()) || (await apiClient.refresh());
        if (authenticated) {
          const current = await apiClient.get<User>("/auth/me");
          if (alive) {
            setUser(current);
            await load();
          }
        }
      } catch (err) {
        if (alive)
          setError(
            err instanceof Error
              ? err.message
              : "Could not restore your session. Please try again.",
          );
      } finally {
        if (alive) setRestoring(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [load]);
  const authenticate = async (event: FormEvent) => {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const result = await apiClient.post<AuthSession>(
        isLogin ? "/auth/login" : "/auth/register",
        isLogin
          ? { email, password }
          : { email, password, full_name: fullName },
      );
      apiClient.setToken(result.token.access_token);
      setUser(result.user);
      setPassword("");
      setExpired(false);
      await load();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Sign-in failed. Check your details and try again.",
      );
    } finally {
      setBusy(false);
    }
  };
  const create = async (event: FormEvent) => {
    event.preventDefault();
    if (busy || !name.trim()) return;
    setBusy(true);
    setCreateError(null);
    try {
      const workspace = await apiClient.post<Workspace>("/workspaces", {
        name: name.trim(),
      });
      router.push(`/workspaces/${workspace.id}`);
    } catch (err) {
      setCreateError(
        err instanceof Error ? err.message : "Workspace could not be created.",
      );
    } finally {
      setBusy(false);
    }
  };
  const logout = async () => {
    setBusy(true);
    setError(null);
    try {
      await apiClient.logout();
      setUser(null);
      setWorkspaces([]);
      // Drop all protected component/SWR state before another account signs in.
      window.location.replace("/");
    } catch {
      setError(
        "Sign-out could not be confirmed. Check your connection and try again.",
      );
    } finally {
      setBusy(false);
    }
  };
  const visible = useMemo(
    () =>
      [...workspaces]
        .filter((item) =>
          item.name.toLowerCase().includes(search.toLowerCase()),
        )
        .sort((a, b) => b.updated_at.localeCompare(a.updated_at)),
    [workspaces, search],
  );
  const total = (key: "documents_count" | "tables_count") =>
    workspaces.every((item) => item[key] != null)
      ? workspaces.reduce((sum, item) => sum + item[key]!, 0).toLocaleString()
      : "Unavailable";

  if (restoring)
    return (
      <main
        id="main-content"
        className="app-page flex items-center justify-center p-6"
      >
        <div className="w-full max-w-sm space-y-8">
          <BrandMark />
          <LoadingState label="Restoring your workspace" />
        </div>
      </main>
    );
  if (!user)
    return (
      <div className="app-page flex min-h-dvh flex-col">
        <header className="app-container py-6">
          <BrandMark />
        </header>
        <main
          id="main-content"
          className="flex flex-1 items-center justify-center px-5 py-10"
        >
          <section className="auth-panel content-enter">
            <p className="eyebrow">Workspace access</p>
            <h1 className="page-title mt-3">
              {isLogin ? "Welcome back" : "Create your account"}
            </h1>
            <p className="body-copy mt-2">
              Investigate questions. Inspect the evidence.
            </p>
            {expired && (
              <p
                role="status"
                className="mt-5 rounded-md border border-zinc-700 p-3 text-xs text-zinc-300"
              >
                Your session has ended. Sign in to continue.
              </p>
            )}
            <form onSubmit={authenticate} aria-busy={busy} className="mt-8 space-y-5">
              {!isLogin && (
                <div>
                  <label htmlFor="full-name" className="field-label">
                    Full name
                  </label>
                  <input
                    id="full-name"
                    autoComplete="name"
                    required
                    value={fullName}
                    onChange={(event) => setFullName(event.target.value)}
                    className="field h-11"
                  />
                </div>
              )}
              <div>
                <label htmlFor="email" className="field-label">
                  Email
                </label>
                <input
                  id="email"
                  type="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  className="field h-11"
                  placeholder="name@company.com"
                  aria-describedby={error ? "auth-error" : undefined}
                />
              </div>
              <div>
                <label htmlFor="password" className="field-label">
                  Password
                </label>
                <div className="relative">
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete={isLogin ? "current-password" : "new-password"}
                  required
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  className="field h-11 pr-12"
                  aria-describedby={error ? "auth-error" : undefined}
                />
                <button type="button" className="btn-icon absolute right-0.5 top-0.5" aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}>
                  {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
                </div>
              </div>
              {error && (
                <div id="auth-error">
                  <ErrorState title="Unable to sign in" message={error} />
                </div>
              )}
              <button disabled={busy} className="btn-primary h-11 w-full">
                {busy && <Loader2 className="h-4 w-4 animate-spin" />}
                <span>{busy ? (isLogin ? "Signing in…" : "Creating account…") : isLogin ? "Sign in" : "Create account"}</span>
                <ArrowRight className="ml-auto h-4 w-4" />
              </button>
              <p role="status" className="sr-only">{busy ? (isLogin ? "Signing in" : "Creating account") : ""}</p>
            </form>
            <p className="mt-6 text-center text-xs text-zinc-400">
              {isLogin ? "New to OmniOps?" : "Already have an account?"}{" "}
              <button
                type="button"
                disabled={busy}
                onClick={() => {
                  setIsLogin(!isLogin);
                  setError(null);
                }}
                className="ml-1 text-zinc-100 underline decoration-zinc-600 underline-offset-4"
              >
                {isLogin ? "Create an account" : "Sign in"}
              </button>
            </p>
          </section>
        </main>
        <footer className="py-6 text-center text-xs text-zinc-400">
          OmniOps · Evidence intelligence
        </footer>
      </div>
    );
  return (
    <div className="app-page">
      <header className="app-topbar">
        <div className="app-container flex h-16 items-center justify-between gap-4">
          <BrandMark compact />
          <div className="flex min-w-0 items-center gap-3">
            <span className="hidden truncate text-xs text-zinc-400 sm:block">
              {user.email}
            </span>
            <button
              onClick={() => void logout()}
              disabled={busy}
              className="btn-ghost"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>
      <main id="main-content" className="app-container py-7 sm:py-9">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="eyebrow">Overview</p>
            <h1 className="page-title mt-2">Your workspaces</h1>
            <p className="meta-copy mt-2">
              Sources, investigations, and the evidence behind your decisions.
            </p>
          </div>
          <button
            onClick={() => {
              setCreateOpen(true);
              setCreateError(null);
            }}
            className="btn-primary"
          >
            <Plus className="h-4 w-4" />
            Create workspace
          </button>
        </div>
        <dl className="surface my-7 grid grid-cols-3 divide-x divide-zinc-700 p-5">
          {[
            {
              label: "Workspaces",
              value: workspaces.length.toLocaleString(),
              icon: Layers3,
            },
            {
              label: "Source files",
              value: total("documents_count"),
              icon: FileText,
            },
            { label: "Tables", value: total("tables_count"), icon: Database },
          ].map(({ label, value, icon: Icon }) => (
            <div key={label} className="px-3 first:pl-0 sm:px-6">
              <dt className="flex items-center gap-2 text-xs text-zinc-400">
                <Icon className="hidden h-3.5 w-3.5 sm:block" />
                {label}
              </dt>
              <dd className="mt-2 text-xl font-medium tracking-tight sm:text-2xl">
                {loading ? "—" : value}
              </dd>
            </div>
          ))}
        </dl>
        {error && (
          <div className="mb-5">
            <ErrorState message={error} onRetry={() => void load()} />
          </div>
        )}
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <h2 className="section-title">Workspace directory</h2>
          <label className="relative w-full sm:w-64">
            <Search className="pointer-events-none absolute left-3 top-3 h-3.5 w-3.5 text-zinc-400" />
            <input
              aria-label="Search workspaces"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search workspaces"
              className="field h-10 pl-9"
            />
          </label>
        </div>
        {loading ? (
          <LoadingState label="Loading workspaces" />
        ) : visible.length === 0 ? (
          <EmptyState
            title={search ? "No matching workspaces" : "Start with a workspace"}
            description={
              search
                ? "Try a different name or clear your search."
                : "Keep related sources and investigations together. Create a workspace, then upload your first source."
            }
            action={
              <button
                className="btn-secondary"
                onClick={() => (search ? setSearch("") : setCreateOpen(true))}
              >
                {search ? "Clear search" : "Create workspace"}
              </button>
            }
          />
        ) : (
          <div className="overflow-hidden rounded-lg border border-zinc-800">
            <div className="hidden grid-cols-[minmax(0,1fr)_100px_100px_150px_24px] gap-4 border-b border-zinc-800 bg-[#151618] px-5 py-3 text-[11px] font-medium text-zinc-400 md:grid">
              <span>Name</span>
              <span className="text-right">Files</span>
              <span className="text-right">Tables</span>
              <span>Updated</span>
              <span />
            </div>
            {visible.map((workspace) => (
              <Link
                href={`/workspaces/${workspace.id}`}
                key={workspace.id}
                className="directory-row group grid grid-cols-[minmax(0,1fr)_24px] items-center gap-4 border-b border-zinc-800 bg-[#181a1e] px-4 py-5 last:border-0 hover:bg-zinc-800/70 sm:px-5 md:grid-cols-[minmax(0,1fr)_100px_100px_150px_24px]"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md border border-zinc-700">
                    <Layers3 className="h-4 w-4 text-zinc-400" />
                  </span>
                  <div className="min-w-0">
                    <h3 className="truncate text-sm font-medium">
                      {workspace.name}
                    </h3>
                    <p className="meta-copy mt-1 truncate">
                      {workspace.description || "Sources and investigations"}
                    </p>
                    <p className="mt-1 text-[11px] text-zinc-400 md:hidden">
                      {workspace.documents_count == null
                        ? "Files not reported"
                        : `${workspace.documents_count} files`}{" "}
                      · {formatDate(workspace.updated_at)}
                    </p>
                  </div>
                </div>
                <span className="hidden text-right text-sm text-zinc-300 md:block">
                  {workspace.documents_count ?? "—"}
                </span>
                <span className="hidden text-right text-sm text-zinc-300 md:block">
                  {workspace.tables_count ?? "—"}
                </span>
                <time
                  title={new Date(workspace.updated_at).toLocaleString()}
                  className="hidden text-xs text-zinc-400 md:block"
                >
                  {formatDate(workspace.updated_at)}
                </time>
                <ArrowRight className="h-4 w-4 text-zinc-500 group-hover:text-zinc-100" />
              </Link>
            ))}
          </div>
        )}
      </main>
      <Dialog
        compact
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        title="Create workspace"
        description="Group the sources for an investigation."
        busy={busy}
      >
        <form onSubmit={create} className="space-y-5">
          <div>
            <label htmlFor="workspace-name" className="field-label">
              Workspace name
            </label>
            <input
              id="workspace-name"
              autoFocus
              required
              maxLength={255}
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="e.g. Quarterly operating review"
              className="field"
              aria-describedby={createError ? "create-error" : undefined}
            />
          </div>
          {createError && (
            <div id="create-error">
              <ErrorState message={createError} />
            </div>
          )}
          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setCreateOpen(false)}
              disabled={busy}
              className="btn-secondary"
            >
              Cancel
            </button>
            <button disabled={busy || !name.trim()} className="btn-primary">
              {busy && <Loader2 className="h-4 w-4 animate-spin" />}Create
              workspace
            </button>
          </div>
        </form>
      </Dialog>
    </div>
  );
}
