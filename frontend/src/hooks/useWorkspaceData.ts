"use client";

import useSWR from "swr";
import { useEffect } from "react";
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
    fetcher,
  );

  const {
    data: files,
    error: filesError,
    mutate: mutateFiles,
  } = useSWR<SourceDocument[]>(
    workspaceId ? `/workspaces/${workspaceId}/files` : null,
    fetcher,
    {
      refreshInterval: (items) =>
        items?.some((file) =>
          ["pending", "processing"].includes(file.processing_status),
        )
          ? 2500
          : 0,
    },
  );

  const {
    data: tables,
    error: tablesError,
    mutate: mutateTables,
  } = useSWR<TabularDataset[]>(
    workspaceId ? `/workspaces/${workspaceId}/tables` : null,
    fetcher,
  );

  const readySources = (files || [])
    .filter((file) =>
      ["ready", "partially_ready"].includes(file.processing_status),
    )
    .map((file) => file.id)
    .join(",");
  useEffect(() => {
    if (readySources) {
      void mutateTables();
      void mutateWorkspace();
    }
  }, [readySources, mutateTables, mutateWorkspace]);

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
