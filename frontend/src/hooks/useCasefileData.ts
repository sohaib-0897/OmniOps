"use client";

import useSWR from "swr";
import { apiClient } from "@/lib/api-client";
import type {
  EvidenceLineageGraph,
  InvestigationHistoryPage,
  PassageMap,
  SourceDocument,
} from "@/types/api";

const passageSources = (files: SourceDocument[]) =>
  files.filter((file) => file.modality !== "spreadsheet");

/**
 * Passage maps for every passage-indexed source in a workspace. Spreadsheets
 * create no passages and are drawn as table blocks instead.
 */
export function useOutlines(workspaceId: string | null, files: SourceDocument[]) {
  const indexed = passageSources(files);
  // Refetch when a source's processing state changes.
  const key = workspaceId && indexed.length
    ? ["outlines", workspaceId, ...indexed.map((file) => `${file.id}:${file.processing_status}`)]
    : null;
  const { data, error, isLoading } = useSWR<Record<string, PassageMap>>(
    key,
    async () => {
      const entries = await Promise.all(
        indexed.map(async (file) => {
          try {
            const map = await apiClient.get<PassageMap>(`/workspaces/${workspaceId}/files/${file.id}/outline`);
            return [file.id, map] as const;
          } catch {
            return null;
          }
        }),
      );
      return Object.fromEntries(entries.filter((entry): entry is readonly [string, PassageMap] => entry !== null));
    },
    { revalidateOnFocus: false, keepPreviousData: true },
  );
  return { outlines: data ?? {}, error, isLoading };
}

export function useInvestigationHistory(workspaceId: string | null, limit = 50) {
  const { data, error, isLoading, mutate } = useSWR<InvestigationHistoryPage>(
    workspaceId ? `/workspaces/${workspaceId}/investigations?limit=${limit}` : null,
    (url: string) => apiClient.get<InvestigationHistoryPage>(url),
    {
      refreshInterval: (page) =>
        page?.items.some((item) => !["completed", "failed", "cancelled"].includes(item.status)) ? 4000 : 0,
    },
  );
  return { history: data, error, isLoading, mutate };
}

/**
 * The lineage graph has no status gate: it is readable once the search batch
 * is committed. It is fetched when the batch arrives and again on completion.
 */
export function useLineage(investigationId: string | null, generation: string | null) {
  const { data, error, isLoading, mutate } = useSWR<EvidenceLineageGraph>(
    investigationId && generation ? ["lineage", investigationId, generation] : null,
    () => apiClient.get<EvidenceLineageGraph>(`/investigations/${investigationId}/evidence`),
    { revalidateOnFocus: false, keepPreviousData: true },
  );
  // keepPreviousData avoids a blank gap between the batch and completion
  // fetches; never let one investigation's lineage show on another.
  const lineage = data && String(data.session_id) === investigationId ? data : null;
  return { lineage, error, isLoading, mutate };
}
