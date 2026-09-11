"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import useSWR from "swr";
import { Plus } from "lucide-react";
import { Workspace } from "@/types/api";
import { apiClient } from "@/lib/api-client";
import { BrandMark } from "@/components/ui/Primitives";

export function WorkspaceHeader({
  workspace,
  onNewInvestigation,
}: {
  workspace?: Workspace | null;
  onNewInvestigation?: () => void;
}) {
  const router = useRouter();
  const { data: workspaces } = useSWR("/workspaces", (url: string) =>
    apiClient.get<Workspace[]>(url),
  );
  if (!workspace) return null;
  return (
    <header className="app-topbar">
      <div className="app-container flex h-16 items-center gap-3 sm:gap-5">
        <Link href="/" aria-label="All workspaces" className="shrink-0">
          <BrandMark compact />
        </Link>
        <span className="h-5 w-px bg-zinc-700" aria-hidden="true" />
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
        <Link href="/" className="btn-ghost hidden sm:inline-flex">
          All workspaces
        </Link>
        {onNewInvestigation && (
          <button
            type="button"
            onClick={onNewInvestigation}
            className="btn-secondary"
            aria-label="New investigation"
          >
            <Plus className="h-4 w-4" />
            <span className="hidden sm:inline">New investigation</span>
          </button>
        )}
      </div>
    </header>
  );
}
