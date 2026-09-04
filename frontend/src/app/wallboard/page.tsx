"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { apiClient } from "@/lib/api-client";
import { Workspace } from "@/types/api";
import {
  Activity,
  ArrowLeft,
  Database,
  FileText,
  Layers,
  Search,
  ShieldCheck,
  Zap,
} from "lucide-react";

export default function WallboardPage() {
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiClient
      .get<Workspace[]>("/workspaces")
      .then((data) => setWorkspaces(data || []))
      .catch((err) => console.error("Failed to load workspaces for wallboard:", err))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-black text-zinc-100 p-6 sm:p-10 font-sans selection:bg-zinc-800 selection:text-white">
      <div className="max-w-6xl mx-auto space-y-8">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-zinc-800 pb-6">
          <div className="space-y-1">
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono uppercase tracking-widest text-zinc-400 bg-zinc-900 border border-zinc-800 px-2 py-0.5 rounded font-semibold">
                Telemetry Overview
              </span>
            </div>
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-white">
              OmniOps Workspaces & Active Lakehouses
            </h1>
            <p className="text-xs sm:text-sm text-zinc-400">
              Live status across business intelligence workspaces and vectorized data pipelines.
            </p>
          </div>

          <Link
            href="/"
            className="inline-flex items-center gap-2 text-xs font-semibold text-zinc-300 hover:text-white bg-zinc-900 hover:bg-zinc-800 border border-zinc-800 px-3.5 py-2 rounded-xl transition-all"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Back to Dashboard</span>
          </Link>
        </div>

        {/* System Subsystems Grid */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-950 space-y-2">
            <div className="flex items-center justify-between text-xs font-semibold text-zinc-400 uppercase tracking-wider">
              <span>Vectorized DuckDB</span>
              <Database className="w-4 h-4 text-zinc-300" />
            </div>
            <p className="text-lg font-bold text-white font-mono">In-Memory Parquet</p>
            <p className="text-xs text-zinc-500">Read-only execution with zero token waste</p>
          </div>

          <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-950 space-y-2">
            <div className="flex items-center justify-between text-xs font-semibold text-zinc-400 uppercase tracking-wider">
              <span>Evidence Contract</span>
              <ShieldCheck className="w-4 h-4 text-zinc-300" />
            </div>
            <p className="text-lg font-bold text-white font-mono">7-Stage Provenance</p>
            <p className="text-xs text-zinc-500">Persisted evidence references</p>
          </div>

          <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-950 space-y-2">
            <div className="flex items-center justify-between text-xs font-semibold text-zinc-400 uppercase tracking-wider">
              <span>Python Sandbox</span>
              <Zap className="w-4 h-4 text-zinc-300" />
            </div>
            <p className="text-lg font-bold text-white font-mono">Isolated Subprocess</p>
            <p className="text-xs text-zinc-500">AST-validated mathematical execution</p>
          </div>
        </div>

        {/* Workspaces List */}
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-bold text-zinc-300 uppercase tracking-wider flex items-center gap-2">
              <Layers className="w-4 h-4 text-zinc-400" />
              <span>Registered Workspaces ({workspaces.length})</span>
            </h2>
          </div>

          {loading ? (
            <div className="p-12 text-center text-xs text-zinc-500 border border-zinc-900 rounded-xl bg-zinc-950">
              Loading workspaces...
            </div>
          ) : workspaces.length === 0 ? (
            <div className="p-12 text-center text-xs text-zinc-500 border border-dashed border-zinc-800 rounded-xl bg-zinc-950 space-y-2">
              <p className="font-semibold text-zinc-300">No active workspaces found</p>
              <p>Create a workspace from the dashboard to begin multimodal investigations.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              {workspaces.map((ws) => (
                <Link
                  key={ws.id}
                  href={`/workspaces/${ws.id}`}
                  className="group p-5 rounded-xl border border-zinc-800 bg-zinc-950 hover:bg-zinc-900 hover:border-zinc-700 transition-all space-y-3 block"
                >
                  <div className="flex items-start justify-between">
                    <div className="space-y-0.5">
                      <h3 className="text-sm font-bold text-zinc-100 group-hover:text-white transition-colors">
                        {ws.name}
                      </h3>
                      {ws.description && (
                        <p className="text-xs text-zinc-400 line-clamp-1">{ws.description}</p>
                      )}
                    </div>
                    <span className="text-[10px] uppercase font-mono bg-zinc-900 border border-zinc-800 px-2 py-0.5 rounded text-zinc-400 font-semibold">
                      {ws.user_role || "member"}
                    </span>
                  </div>

                  <div className="flex items-center gap-4 text-xs text-zinc-400 font-mono pt-2 border-t border-zinc-900">
                    <span className="flex items-center gap-1.5">
                      <FileText className="w-3.5 h-3.5 text-zinc-500" />
                      {ws.documents_count || 0} Files
                    </span>
                    <span className="flex items-center gap-1.5">
                      <Database className="w-3.5 h-3.5 text-zinc-500" />
                      {ws.tables_count || 0} Tables
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
