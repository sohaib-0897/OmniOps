"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { apiClient } from "@/lib/api-client";
import { AuthSession, Workspace } from "@/types/api";
import {
  Layers,
  ShieldCheck,
  ArrowRight,
  Plus,
  Lock,
  Mail,
  User as UserIcon,
  Loader2,
  Database,
  FileCheck,
  Cpu,
  Sparkles,
} from "lucide-react";

export default function LandingAndWorkspacePicker() {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [isLogin, setIsLogin] = useState(true);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [currentUser, setCurrentUser] = useState<any | null>(null);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [fetchingWorkspaces, setFetchingWorkspaces] = useState(false);
  const [newWorkspaceName, setNewWorkspaceName] = useState("");
  const [creatingWorkspace, setCreatingWorkspace] = useState(false);

  useEffect(() => {
    setMounted(true);
    const token = localStorage.getItem("omniops_token");
    if (token) {
      fetchWorkspaces();
    }
  }, []);

  const fetchWorkspaces = async () => {
    setFetchingWorkspaces(true);
    try {
      const user = await apiClient.get<any>("/auth/me");
      setCurrentUser(user);
      const wsList = await apiClient.get<Workspace[]>("/workspaces");
      setWorkspaces(wsList || []);
    } catch (e) {
      apiClient.clearToken();
      setCurrentUser(null);
    } finally {
      setFetchingWorkspaces(false);
    }
  };

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);

    try {
      if (isLogin) {
        const res = await apiClient.post<AuthSession>("/auth/login", { email, password });
        apiClient.setToken(res.token.access_token);
        setCurrentUser(res.user);
      } else {
        const res = await apiClient.post<AuthSession>("/auth/register", {
          email,
          password,
          full_name: fullName,
        });
        apiClient.setToken(res.token.access_token);
        setCurrentUser(res.user);
      }
      await fetchWorkspaces();
    } catch (err: any) {
      setError(err.message || "Authentication failed.");
    } finally {
      setLoading(false);
    }
  };

  const handleCreateWorkspace = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newWorkspaceName.trim()) return;
    setCreatingWorkspace(true);
    try {
      const newWs = await apiClient.post<Workspace>("/workspaces", {
        name: newWorkspaceName.trim(),
        description: "Multimodal Decision Intelligence Lakehouse",
      });
      router.push(`/workspaces/${newWs.id}`);
    } catch (err: any) {
      setError(err.message || "Failed to create workspace.");
    } finally {
      setCreatingWorkspace(false);
    }
  };

  const handleLogout = () => {
    apiClient.clearToken();
    setCurrentUser(null);
    setWorkspaces([]);
  };

  return (
    <div
      suppressHydrationWarning
      className="min-h-screen bg-black text-zinc-100 flex flex-col justify-between relative overflow-hidden font-sans selection:bg-zinc-800 selection:text-white"
    >
      {/* Header */}
      <header className="border-b border-zinc-850 bg-black/90 backdrop-blur-md px-6 sm:px-10 py-4 flex items-center justify-between sticky top-0 z-30">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-zinc-900 border border-zinc-750 text-white flex items-center justify-center font-bold">
            <Layers className="w-4 h-4" />
          </div>
          <div>
            <span className="font-bold text-sm tracking-tight text-white block">OmniOps</span>
            <span className="text-[10px] text-zinc-400 font-mono block -mt-0.5">
              Evidence-Grounded Decision Intelligence
            </span>
          </div>
        </div>

        {mounted && currentUser && (
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-xs text-zinc-400">
              <span className="w-2 h-2 rounded-full bg-zinc-400" />
              <span>Signed in as <strong className="text-white font-semibold">{currentUser.full_name}</strong></span>
            </div>
            <button
              onClick={handleLogout}
              suppressHydrationWarning
              className="text-xs text-zinc-400 hover:text-white transition-colors font-medium px-3 py-1 rounded-lg border border-zinc-800 hover:bg-zinc-900 cursor-pointer"
            >
              Sign out
            </button>
          </div>
        )}
      </header>

      {/* Main Container */}
      <main className="flex-1 flex items-center justify-center p-6 sm:p-10 z-10">
        <div className="w-full max-w-5xl grid md:grid-cols-12 gap-8 lg:gap-12 items-center">
          {/* Left Brand Showcase */}
          <div className="md:col-span-7 space-y-6">
            <div className="inline-flex items-center gap-2 px-3 py-1 rounded-md bg-zinc-900 border border-zinc-800 text-zinc-300 text-xs font-semibold">
              <ShieldCheck className="w-3.5 h-3.5 text-zinc-400" />
              <span>7-Stage Evidence Reference Contract</span>
            </div>

            <h1 className="text-3xl sm:text-4xl lg:text-5xl font-extrabold text-white tracking-tight leading-[1.15]">
              Investigate complex business questions with verifiable proof.
            </h1>

            <p className="text-xs sm:text-sm text-zinc-400 leading-relaxed max-w-xl">
              Upload spreadsheets, PDFs, available audio transcripts, and documents. OmniOps creates
              analytical DAGs, executes vectorized calculations in DuckDB, verifies claims, and produces
              transparent evidence lineage with deterministic reference checks.
            </p>

            <div className="grid sm:grid-cols-2 gap-3 pt-2">
              <div className="p-4 rounded-xl bg-zinc-950 border border-zinc-800 space-y-1.5 shadow-sm">
                <div className="font-bold text-xs text-white flex items-center gap-2">
                  <Database className="w-4 h-4 text-zinc-300" />
                  DuckDB Vectorized Lakehouse
                </div>
                <p className="text-zinc-400 text-xs leading-relaxed">
                  In-memory analytical SQL with reproducible query hashes.
                </p>
              </div>

              <div className="p-4 rounded-xl bg-zinc-950 border border-zinc-800 space-y-1.5 shadow-sm">
                <div className="font-bold text-xs text-white flex items-center gap-2">
                  <FileCheck className="w-4 h-4 text-zinc-300" />
                  7-Stage Verifiable Lineage
                </div>
                <p className="text-zinc-400 text-xs leading-relaxed">
                  Deterministic provenance linking primary excerpts directly to strategic recommendations.
                </p>
              </div>
            </div>
          </div>

          {/* Right Action / Auth Card */}
          <div className="md:col-span-5 border border-zinc-800 bg-zinc-950 p-6 sm:p-7 rounded-2xl shadow-2xl space-y-6">
            {mounted && currentUser ? (
              /* Workspace Selector */
              <div className="space-y-5">
                <div>
                  <h2 className="text-sm font-bold text-white tracking-tight">Select Workspace</h2>
                  <p className="text-xs text-zinc-400 mt-1">
                    Choose an existing workspace or initialize a new isolated lakehouse.
                  </p>
                </div>

                {fetchingWorkspaces ? (
                  <div className="py-12 flex flex-col items-center justify-center gap-2 text-zinc-500 text-xs">
                    <Loader2 className="w-5 h-5 animate-spin text-zinc-400" />
                    <span>Loading your workspaces...</span>
                  </div>
                ) : (
                  <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
                    {workspaces.map((ws) => (
                      <div
                        key={ws.id}
                        role="button"
                        tabIndex={0}
                        onClick={() => router.push(`/workspaces/${ws.id}`)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            router.push(`/workspaces/${ws.id}`);
                          }
                        }}
                        className="group flex items-center justify-between p-3 rounded-xl border border-zinc-800/80 bg-zinc-900/60 hover:bg-zinc-900 hover:border-zinc-700 cursor-pointer transition-all outline-none focus-visible:ring-1 focus-visible:ring-zinc-400"
                      >
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-lg bg-zinc-900 border border-zinc-800 text-zinc-300 flex items-center justify-center font-bold text-xs">
                            <Layers className="w-4 h-4" />
                          </div>
                          <div>
                            <p className="text-xs font-bold text-zinc-200 group-hover:text-white transition-colors">
                              {ws.name}
                            </p>
                            <p className="text-[11px] text-zinc-400 font-mono mt-0.5">
                              {ws.documents_count || 0} files • {ws.tables_count || 0} tables
                            </p>
                          </div>
                        </div>
                        <ArrowRight className="w-4 h-4 text-zinc-500 group-hover:text-white group-hover:translate-x-0.5 transition-all" />
                      </div>
                    ))}
                  </div>
                )}

                {/* Create New Workspace Form */}
                <form onSubmit={handleCreateWorkspace} suppressHydrationWarning className="pt-4 border-t border-zinc-850 space-y-3">
                  <label className="text-xs font-bold text-zinc-300 uppercase tracking-wider block">
                    Create New Workspace
                  </label>
                  <div className="flex items-center gap-2">
                    <input
                      type="text"
                      suppressHydrationWarning
                      value={newWorkspaceName}
                      onChange={(e) => setNewWorkspaceName(e.target.value)}
                      placeholder="E.g., Q3 Revenue Analysis"
                      className="flex-1 text-xs bg-zinc-900 border border-zinc-800 rounded-xl px-3.5 py-2 text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-zinc-600 transition-all"
                    />
                    <button
                      type="submit"
                      suppressHydrationWarning
                      disabled={!newWorkspaceName.trim() || creatingWorkspace}
                      className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-white text-black hover:bg-zinc-200 text-xs font-bold disabled:opacity-40 transition-all cursor-pointer"
                    >
                      {creatingWorkspace ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Plus className="w-3.5 h-3.5" />}
                      <span>Create</span>
                    </button>
                  </div>
                </form>
              </div>
            ) : (
              /* Auth Form (Login / Register) */
              <div className="space-y-5" suppressHydrationWarning>
                <div>
                  <h2 className="text-base font-bold text-white tracking-tight">
                    {isLogin ? "Sign in to OmniOps" : "Create OmniOps Account"}
                  </h2>
                  <p className="text-xs text-zinc-400 mt-1">
                    {isLogin ? "Enter your credentials to access workspace investigations." : "Get started with evidence-grounded decision intelligence."}
                  </p>
                </div>

                <form onSubmit={handleAuth} suppressHydrationWarning className="space-y-3.5">
                  {!isLogin && (
                    <div className="space-y-1">
                      <label className="text-xs font-semibold text-zinc-300">Full Name</label>
                      <div className="relative">
                        <UserIcon className="w-3.5 h-3.5 absolute left-3 top-3 text-zinc-500" />
                        <input
                          type="text"
                          required
                          suppressHydrationWarning
                          value={fullName}
                          onChange={(e) => setFullName(e.target.value)}
                          placeholder="Finance Director"
                          className="w-full bg-zinc-900 border border-zinc-800 rounded-xl pl-9 pr-3.5 py-2 text-xs text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-zinc-600 transition-all"
                        />
                      </div>
                    </div>
                  )}

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-zinc-300">Work Email</label>
                    <div className="relative">
                      <Mail className="w-3.5 h-3.5 absolute left-3 top-3 text-zinc-500" />
                      <input
                        type="email"
                        required
                        suppressHydrationWarning
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="director@company.com"
                        className="w-full bg-zinc-900 border border-zinc-800 rounded-xl pl-9 pr-3.5 py-2 text-xs text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-zinc-600 transition-all"
                      />
                    </div>
                  </div>

                  <div className="space-y-1">
                    <label className="text-xs font-semibold text-zinc-300">Password</label>
                    <div className="relative">
                      <Lock className="w-3.5 h-3.5 absolute left-3 top-3 text-zinc-500" />
                      <input
                        type="password"
                        required
                        suppressHydrationWarning
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="••••••••"
                        className="w-full bg-zinc-900 border border-zinc-800 rounded-xl pl-9 pr-3.5 py-2 text-xs text-zinc-100 placeholder:text-zinc-500 outline-none focus:border-zinc-600 transition-all"
                      />
                    </div>
                  </div>

                  {error && (
                    <div className="text-xs text-zinc-300 bg-zinc-900 p-3 rounded-xl border border-zinc-800 leading-snug">
                      {error}
                    </div>
                  )}

                  <button
                    type="submit"
                    disabled={loading}
                    suppressHydrationWarning
                    className="w-full py-2.5 rounded-xl bg-white text-black hover:bg-zinc-200 font-bold text-xs disabled:opacity-40 transition-all flex items-center justify-center gap-2 mt-2 cursor-pointer shadow-sm"
                  >
                    {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                    <span>{isLogin ? "Sign In" : "Create Account"}</span>
                  </button>
                </form>

                <div className="text-center pt-2 border-t border-zinc-850 text-xs text-zinc-400">
                  <span>{isLogin ? "Don't have an account? " : "Already have an account? "}</span>
                  <button
                    type="button"
                    suppressHydrationWarning
                    onClick={() => {
                      setIsLogin(!isLogin);
                      setError(null);
                    }}
                    className="text-white hover:underline font-bold cursor-pointer"
                  >
                    {isLogin ? "Register" : "Sign In"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-zinc-850 bg-black px-6 sm:px-10 py-4 text-xs text-zinc-500 flex items-center justify-between font-mono">
        <span>© 2026 OmniOps • Evidence-Grounded Business Intelligence</span>
        <span>Evidence Reference Contract</span>
      </footer>
    </div>
  );
}
