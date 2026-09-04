"use client";

import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Workspace } from "@/types/api";
import { apiClient } from "@/lib/api-client";
import {
  Layers,
  Users,
  FileText,
  Database,
  ArrowLeft,
  ChevronDown,
  Plus,
  Check,
} from "lucide-react";

interface Props {
  workspace: Workspace | null | undefined;
  onNewInvestigation?: () => void;
}

export function WorkspaceHeader({ workspace }: Props) {
  const router = useRouter();
  const [allWorkspaces, setAllWorkspaces] = useState<Workspace[]>([]);
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    apiClient
      .get<Workspace[]>("/workspaces")
      .then((data) => setAllWorkspaces(data || []))
      .catch(() => {});
  }, []);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent | TouchEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setSwitcherOpen(false);
      }
    };
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setSwitcherOpen(false);
      }
    };

    if (switcherOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("touchstart", handleClickOutside);
      document.addEventListener("keydown", handleKeyDown);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("touchstart", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [switcherOpen]);

  if (!workspace) return null;

  return (
    <header className="border-b border-zinc-850 bg-black/95 backdrop-blur-md px-6 py-2.5 flex items-center justify-between sticky top-0 z-30 font-sans">
      <div className="flex items-center gap-4">
        {/* Logo & Backlink */}
        <Link
          href="/"
          className="flex items-center gap-2.5 text-zinc-400 hover:text-white transition-colors py-1 px-2 rounded-lg hover:bg-zinc-900"
          title="All Workspaces"
        >
          <div className="w-7 h-7 rounded-lg bg-zinc-900 border border-zinc-800 text-white flex items-center justify-center font-bold text-xs">
            <Layers className="w-3.5 h-3.5" />
          </div>
          <span className="font-bold text-sm text-white tracking-tight">OmniOps</span>
        </Link>

        <div className="h-4 w-px bg-zinc-800" />

        {/* Workspace Identity and Dropdown Switcher */}
        <div className="relative" ref={dropdownRef}>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              setSwitcherOpen((prev) => !prev);
            }}
            className="flex items-center gap-2 px-2.5 py-1 rounded-lg hover:bg-zinc-900 transition-all text-left outline-none focus-visible:ring-1 focus-visible:ring-zinc-400 cursor-pointer group"
          >
            <div>
              <div className="flex items-center gap-2">
                <span className="font-semibold text-zinc-100 text-xs sm:text-sm leading-none flex items-center gap-1.5 group-hover:text-white transition-colors">
                  <span>{workspace.name}</span>
                  <ChevronDown className={`w-3.5 h-3.5 text-zinc-400 group-hover:text-zinc-200 transition-transform ${switcherOpen ? "rotate-180" : ""}`} />
                </span>
                <span className="text-[10px] font-semibold font-mono bg-zinc-900 text-zinc-300 border border-zinc-800 px-2 py-0.5 rounded capitalize">
                  {workspace.user_role || "Owner"}
                </span>
              </div>
            </div>
          </button>

          {/* Switcher Dropdown Menu */}
          {switcherOpen && (
            <div className="absolute left-0 top-full mt-2 w-72 bg-zinc-950 border border-zinc-800 rounded-xl shadow-2xl p-2 z-50 space-y-1">
              <div className="px-2.5 py-1 text-[10px] font-semibold text-zinc-400 uppercase tracking-wider flex items-center justify-between font-mono">
                <span>Workspaces</span>
                <span>({allWorkspaces.length})</span>
              </div>
              <div className="max-h-48 overflow-y-auto space-y-0.5 pr-0.5">
                {allWorkspaces.map((ws) => (
                  <button
                    key={ws.id}
                    type="button"
                    onClick={() => {
                      setSwitcherOpen(false);
                      if (ws.id !== workspace.id) {
                        router.push(`/workspaces/${ws.id}`);
                      }
                    }}
                    className={`w-full flex items-center justify-between p-2 rounded-lg text-xs transition-all cursor-pointer ${
                      ws.id === workspace.id
                        ? "bg-zinc-900 text-white font-semibold border border-zinc-750"
                        : "hover:bg-zinc-900 text-zinc-400 hover:text-white font-medium"
                    }`}
                  >
                    <span className="truncate">{ws.name}</span>
                    {ws.id === workspace.id && <Check className="w-3.5 h-3.5 text-white shrink-0" />}
                  </button>
                ))}
              </div>
              <div className="pt-1.5 border-t border-zinc-850">
                <Link
                  href="/"
                  className="w-full flex items-center gap-2 p-2 rounded-lg text-xs text-zinc-400 hover:text-white hover:bg-zinc-900 transition-colors font-medium cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5 text-zinc-300" />
                  <span>Create Workspace</span>
                </Link>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Right Stats Telemetry with high-contrast monochrome badge pills */}
      <div className="flex items-center gap-2.5 text-xs font-mono">
        <div
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-300"
          title="Ingested Multi-Source Documents"
        >
          <FileText className="w-3.5 h-3.5 text-zinc-500" />
          <span className="font-bold text-white">{workspace.documents_count || 0}</span>
          <span className="text-zinc-500">Docs</span>
        </div>

        <div
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-300"
          title="Vectorized Tabular Parquet Datasets"
        >
          <Database className="w-3.5 h-3.5 text-zinc-500" />
          <span className="font-bold text-white">{workspace.tables_count || 0}</span>
          <span className="text-zinc-500">Tables</span>
        </div>

        <div
          className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-300"
          title="Active Workspace Members"
        >
          <Users className="w-3.5 h-3.5 text-zinc-500" />
          <span className="font-bold text-white">{workspace.members_count || 1}</span>
          <span className="text-zinc-500">Member</span>
        </div>
      </div>
    </header>
  );
}
