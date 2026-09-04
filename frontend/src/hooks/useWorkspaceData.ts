"use client";

import useSWR from "swr";
import { apiClient } from "@/lib/api-client";
import { Workspace, SourceDocument, TabularDataset } from "@/types/api";

const fetcher = (url: string) => apiClient.get<any>(url);

export function useWorkspaceData(workspaceId: string | null) {
  const {
    data: workspace,
    error: workspaceError,
    mutate: mutateWorkspace,
  } = useSWR<Workspace>(
    workspaceId ? `/workspaces/${workspaceId}` : null,
    fetcher
  );

  const {
    data: files,
    error: filesError,
    mutate: mutateFiles,
  } = useSWR<SourceDocument[]>(
    workspaceId ? `/workspaces/${workspaceId}/files` : null,
    fetcher
  );

  const {
    data: tables,
    error: tablesError,
    mutate: mutateTables,
  } = useSWR<TabularDataset[]>(
    workspaceId ? `/workspaces/${workspaceId}/tables` : null,
    fetcher
  );

  return {
    workspace,
    files: files || [],
    tables: tables || [],
    isLoading: !workspace && !workspaceError,
    isError: Boolean(workspaceError || filesError || tablesError),
    mutateAll: () => {
      mutateWorkspace();
      mutateFiles();
      mutateTables();
    },
  };
}
