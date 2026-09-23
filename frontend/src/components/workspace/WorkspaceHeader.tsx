"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { Activity, Files, PanelLeft, Plus } from "lucide-react";
import { Workspace } from "@/types/api";
import { apiClient } from "@/lib/api-client";
import { BrandMark } from "@/components/ui/Primitives";

export function WorkspaceHeader({
  workspace,
  onNewInvestigation,
  onSources,
  onActivity,
  onToggleNavigation,
  navigationOpen,
  sourceCount = 0,
}: {
  workspace?: Workspace | null;
  onNewInvestigation?: () => void;
  onSources?: () => void;
  onActivity?: () => void;
  onToggleNavigation?: () => void;
  navigationOpen?: boolean;
  sourceCount?: number;
}) {
  const router = useRouter();
  const { data: workspaces } = useSWR("/workspaces", (url: string) =>
    apiClient.get<Workspace[]>(url),
  );
  if (!workspace) return null;
  return (
    <header className="app-topbar workspace-topbar">
      <div className="flex h-16 items-center gap-3 px-4 sm:px-6">
        {onToggleNavigation && <button className="btn-icon hidden lg:inline-flex" aria-label="Toggle navigation" aria-expanded={navigationOpen} aria-controls="workspace-navigation" onClick={onToggleNavigation}><PanelLeft className="h-4 w-4" /></button>}
        <Link href="/" aria-label="All workspaces" className="workspace-brand shrink-0">
          <BrandMark compact />
        </Link>
        <span className="mx-1 text-zinc-600" aria-hidden="true">/</span>
        <div className="min-w-0 flex-1">
          <label htmlFor="workspace-switcher" className="sr-only">
            Switch workspace
          </label>
          <select
            id="workspace-switcher"
            value={workspace.id}
            onChange={(event) =>
              router.push(`/workspaces/${event.target.value}`)
            }
            className="max-w-full truncate rounded-md border border-transparent bg-[#101113] py-2 pr-2 text-xs text-zinc-200 hover:border-zinc-700 sm:max-w-xs sm:text-sm"
          >
            {(workspaces?.some((item) => item.id === workspace.id)
              ? workspaces
              : [workspace, ...(workspaces || [])]
            ).map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </div>
        {onSources && <button onClick={onSources} className={`btn-ghost ${navigationOpen ? "lg:hidden" : ""}`} aria-label={`Sources (${sourceCount})`}><Files className="h-4 w-4" /><span className="hidden sm:inline">Sources</span><span className="text-xs">{sourceCount}</span></button>}
        {onActivity && <button onClick={onActivity} className="btn-ghost" aria-label="Activity"><Activity className="h-4 w-4" /><span className="hidden sm:inline">Activity</span></button>}
        {onNewInvestigation && (
          <button
            type="button"
            onClick={onNewInvestigation}
            className="btn-icon lg:hidden"
            aria-label="New investigation"
          >
            <Plus className="h-4 w-4" />
          </button>
        )}
      </div>
    </header>
  );
}
