"use client";
import { useMemo, useState } from "react";
import { ArrowUpRight, Copy } from "lucide-react";
import { EpistemicClaim, EvidenceLineageGraph, LineageNode } from "@/types/api";
import { Dialog } from "@/components/ui/Dialog";
import {
  EmptyState,
  ErrorState,
  StatusBadge,
} from "@/components/ui/Primitives";
import { formatDuration, formatNumber } from "@/lib/utils";

interface Props {
  claim: EpistemicClaim | null;
  citationId: string | null;
  lineageGraph: EvidenceLineageGraph | null;
  onClose: () => void;
  onInspectSource?: (id: string) => void;
  loading?: boolean;
  error?: string | null;
  onRetry?: () => void;
}
const groups = [
  "source",
  "extracted_content",
  "evidence",
  "calculation",
  "claim",
  "inference",
  "recommendation",
];
const category = (node: LineageNode) =>
  node.id.startsWith("claim_") && node.type !== "inference"
    ? "claim"
    : node.type;
const displayValue = (value: unknown) =>
  typeof value === "number"
    ? formatNumber(value)
    : typeof value === "string"
      ? value
      : JSON.stringify(value, null, 2);

export function EvidenceLineageDrawer({
  claim,
  citationId,
  lineageGraph,
  onClose,
  onInspectSource,
  loading,
  error,
  onRetry,
}: Props) {
  const [copied, setCopied] = useState<string | null>(null);
  const [copyError, setCopyError] = useState<string | null>(null);
  const nodes = useMemo(() => {
    if (!lineageGraph) return [];
    const seed = lineageGraph.nodes.find((node) =>
      citationId
        ? node.id === citationId || node.id === `ev_${citationId}`
        : node.data.claim_code === claim?.claim_id,
    );
    if (!seed) return [];
    const selected = new Set([seed.id]);
    // Follow ancestors and descendants separately; do not infer sibling relationships.
    for (const direction of ["up", "down"]) {
      const visited = new Set([seed.id]);
      const pending = [seed.id];
      while (pending.length) {
        const current = pending.pop();
        for (const edge of lineageGraph.edges) {
          const next =
            direction === "up" && edge.target === current
              ? edge.source
              : direction === "down" && edge.source === current
                ? edge.target
                : null;
          if (next && !visited.has(next)) {
            visited.add(next);
            selected.add(next);
            pending.push(next);
          }
        }
      }
    }
    return [
      ...new Map(
        lineageGraph.nodes
          .filter((node) => selected.has(node.id))
          .map((node) => [node.id, node]),
      ).values(),
    ];
  }, [claim, citationId, lineageGraph]);
  const copy = async (value: string, id: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(id);
      setCopyError(null);
    } catch {
      setCopyError(
        "Copy is unavailable. Select the text and copy it manually.",
      );
    }
  };
  return (
    <Dialog
      open={Boolean(claim || citationId)}
      onClose={onClose}
      title="Evidence and provenance"
      description="Recorded relationships for the selected claim or citation."
      drawer
    >
      <div className="space-y-5">
        {claim && (
          <section className="border-b border-zinc-800 pb-5">
            <div className="flex flex-wrap items-center gap-2">
              <span className="mono-copy">{claim.claim_id}</span>
              <span className="text-xs capitalize text-zinc-300">
                {claim.epistemic_type}
              </span>
              <StatusBadge
                status={claim.verification_status || "not_reported"}
              />
            </div>
            <p className="body-copy mt-3">{claim.statement}</p>
            {claim.confidence_score != null && (
              <p className="meta-copy mt-3">
                Provider-reported confidence:{" "}
                {formatNumber(claim.confidence_score * 100)}%
              </p>
            )}
          </section>
        )}
        {copyError && <ErrorState message={copyError} />}
        {error ? (
          <ErrorState
            title="Provenance unavailable"
            message={error}
            onRetry={onRetry}
          />
        ) : loading ? (
          <p role="status" className="meta-copy">
            Loading persisted provenance…
          </p>
        ) : nodes.length === 0 ? (
          <EmptyState
            title="No recorded lineage found"
            description="This selection has no available provenance graph. No relationships have been inferred."
          />
        ) : (
          groups.map((group, index) => {
            const items = nodes.filter((node) => category(node) === group);
            return (
              <section key={group}>
                <h3 className="eyebrow mb-3">
                  <span className="mr-2 font-mono text-zinc-400">
                    0{index + 1}
                  </span>
                  {group.replace(/_/g, " ")}
                </h3>
                {items.length === 0 ? (
                  <p className="border-l border-zinc-800 pl-4 text-xs text-zinc-400">
                    No linked record
                  </p>
                ) : (
                  items.map((node) => {
                    const locator =
                      node.data.locator || node.data.coordinates || {};
                    return (
                      <article
                        key={node.id}
                        className="mb-3 border-l border-zinc-600 pl-4"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <h4 className="break-words text-xs font-medium">
                            {node.type === "evidence" ? "Evidence excerpt" : node.type === "extracted_content" ? "Extracted content" : node.label}
                          </h4>
                          {node.data.quote && (
                            <button
                              className="btn-ghost h-7"
                              onClick={() =>
                                void copy(node.data.quote, node.id)
                              }
                            >
                              <Copy className="h-3.5 w-3.5" />
                              {copied === node.id ? "Copied" : "Copy"}
                            </button>
                          )}
                        </div>
                        {node.data.modality && (
                          <p className="meta-copy mt-1 capitalize">
                            {node.data.modality}
                          </p>
                        )}
                        {node.data.source_id && onInspectSource && (
                          <button
                            className="citation mt-2"
                            onClick={() => onInspectSource(node.data.source_id)}
                          >
                            Inspect source
                            <ArrowUpRight className="h-3 w-3" />
                          </button>
                        )}
                        {(node.data.quote ||
                          node.data.content ||
                          node.data.statement) && (
                          <p className="mt-2 whitespace-pre-wrap break-words text-xs leading-6 text-zinc-300">
                            {node.data.quote ||
                              node.data.content ||
                              node.data.statement}
                          </p>
                        )}
                        <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-zinc-400">
                          {locator.page_number != null && (
                            <span>Page {locator.page_number}</span>
                          )}
                          {locator.cell_range && (
                            <span>Cells {locator.cell_range}</span>
                          )}
                          {locator.audio_start_ms != null && (
                            <span>
                              {formatDuration(locator.audio_start_ms)} –{" "}
                              {formatDuration(locator.audio_end_ms)}
                            </span>
                          )}
                          {node.data.extraction_method && (
                            <span>
                              {String(node.data.extraction_method).replace(
                                /_/g,
                                " ",
                              )}
                            </span>
                          )}
                        </div>
                        {node.data.code && (
                          <details className="mt-2 text-xs text-zinc-300">
                            <summary>Formula / code</summary>
                            <pre className="mt-2 whitespace-pre-wrap break-words rounded border border-zinc-800 p-3 text-[11px] leading-6">
                              {node.data.code}
                            </pre>
                          </details>
                        )}
                        {node.data.output != null && (
                          <div className="mt-3">
                            <p className="eyebrow">Output</p>
                            <pre className="mt-2 whitespace-pre-wrap break-words text-xs leading-6">
                              {displayValue(node.data.output)}
                            </pre>
                          </div>
                        )}
                        {node.data.verification_status && (
                          <div className="mt-3">
                            <StatusBadge
                              status={node.data.verification_status}
                            />
                          </div>
                        )}
                        <details className="mt-3 text-[11px] text-zinc-400">
                          <summary>Record and relationships</summary>
                          <p className="mt-2 break-all font-mono">{node.id}</p>
                          {lineageGraph?.edges
                            .filter(
                              (edge) =>
                                edge.source === node.id ||
                                edge.target === node.id,
                            )
                            .map((edge, edgeIndex) => (
                              <p
                                key={edgeIndex}
                                className="mt-2 break-words leading-5"
                              >
                                {edge.relation.replace(/_/g, " ").toLowerCase()}{" "}
                                ·{" "}
                                {lineageGraph.nodes.find(
                                  (other) =>
                                    other.id ===
                                    (edge.source === node.id
                                      ? edge.target
                                      : edge.source),
                                )?.label || "Record unavailable"}
                              </p>
                            ))}
                          {node.data.reproducibility_hash && (
                            <p className="mt-3 break-all font-mono">
                              SHA-256: {node.data.reproducibility_hash}
                            </p>
                          )}
                        </details>
                      </article>
                    );
                  })
                )}
              </section>
            );
          })
        )}
      </div>
    </Dialog>
  );
}
