"use client";

import React, { useEffect, useState } from "react";
import { EpistemicClaim, EvidenceLineageGraph } from "@/types/api";
import {
  X,
  ShieldCheck,
  FileText,
  FileSearch,
  Bookmark,
  Calculator,
  CheckCircle2,
  Compass,
  Lightbulb,
  ArrowRight,
  Hash,
  Copy,
  Check,
} from "lucide-react";

interface Props {
  claim: EpistemicClaim | null;
  citationId: string | null;
  lineageGraph: EvidenceLineageGraph | null;
  onClose: () => void;
}

export function EvidenceLineageDrawer({ claim, citationId, lineageGraph, onClose }: Props) {
  const [copiedType, setCopiedType] = useState<string | null>(null);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  if (!claim && !citationId) return null;

  const copyToClipboard = async (text: string, type: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedType(type);
      setTimeout(() => setCopiedType(null), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  };

  const activeEvNode = citationId && lineageGraph
    ? lineageGraph.nodes.find((n) => n.id === `ev_${citationId}` || n.id === citationId)
    : null;

  const activeClaimNode = claim && lineageGraph
    ? lineageGraph.nodes.find((node) => node.type === claim.epistemic_type && node.data?.claim_code === claim.claim_id)
    : null;
  const calculationEdge = activeClaimNode && lineageGraph
    ? lineageGraph.edges.find((edge) => edge.target === activeClaimNode.id && edge.relation === "CALCULATED_FROM")
    : null;
  const activeCalcNode = calculationEdge && lineageGraph
    ? lineageGraph.nodes.find((node) => node.id === calculationEdge.source)
    : null;

  const quoteText = activeEvNode?.data?.quote || "No extracted evidence content is available for this selection.";
  const calculationCode = claim?.calculation_summary || activeCalcNode?.data?.code || null;
  const hashValue = activeCalcNode?.data?.reproducibility_hash || null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="lineage-drawer-title"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          onClose();
        }
      }}
      className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex justify-end font-sans cursor-pointer"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full sm:w-[480px] h-full bg-zinc-950 border-l border-zinc-800 shadow-2xl flex flex-col cursor-default"
      >
        {/* Header */}
        <div className="p-4 sm:p-5 border-b border-zinc-850 flex items-center justify-between bg-black">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-xl bg-zinc-900 border border-zinc-800 text-zinc-300 flex items-center justify-center font-bold">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div>
              <h3 id="lineage-drawer-title" className="text-sm font-bold text-white">
                7-Stage Evidentiary Lineage
              </h3>
              <span className="text-[11px] text-zinc-400 block">
                Persisted provenance and reference validation
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onClose();
            }}
            aria-label="Close lineage drawer"
            className="p-1.5 rounded-lg text-zinc-400 hover:text-white hover:bg-zinc-900 transition-colors cursor-pointer"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 flex-1 overflow-y-auto space-y-4 text-xs">
          {/* Selected Claim Overview */}
          {claim && (
            <div className="space-y-2 border border-zinc-800 p-3.5 rounded-xl bg-zinc-900">
              <div className="flex items-center justify-between">
                <span className="font-mono font-bold text-xs text-white">{claim.claim_id}</span>
                <span className="uppercase text-[10px] font-semibold bg-zinc-950 text-zinc-300 border border-zinc-800 px-2 py-0.5 rounded font-mono">
                  {claim.epistemic_type}
                </span>
              </div>
              <p className="text-xs font-semibold text-zinc-100 leading-snug">{claim.statement}</p>
              <div className="flex items-center gap-2 text-[11px] text-zinc-400 pt-1 font-mono">
                <span>Provider confidence:</span>
                <span className="font-bold text-white">{claim.confidence_score == null ? "NOT_PROVIDED" : `${(claim.confidence_score * 100).toFixed(1)}%`}</span>
              </div>
            </div>
          )}

          {/* Selected Citation Quote */}
          {activeEvNode && (
            <div className="space-y-2 border border-zinc-800 p-3.5 rounded-xl bg-zinc-900/60">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-1.5 text-zinc-300 font-bold text-xs">
                  <Bookmark className="w-3.5 h-3.5 text-zinc-400" />
                  <span>Source Excerpt</span>
                </div>
                <button
                  type="button"
                  onClick={() => copyToClipboard(quoteText, "quote")}
                  className="text-[11px] text-zinc-400 hover:text-white inline-flex items-center gap-1 cursor-pointer"
                >
                  {copiedType === "quote" ? <Check className="w-3 h-3 text-white" /> : <Copy className="w-3 h-3" />}
                  <span>{copiedType === "quote" ? "Copied" : "Copy Quote"}</span>
                </button>
              </div>
              <blockquote className="text-xs text-zinc-300 italic leading-relaxed border-l-2 border-zinc-700 pl-3">
                &ldquo;{quoteText}&rdquo;
              </blockquote>
            </div>
          )}

          {/* 7-Stage Lineage Flow Visualizer */}
          <div className="space-y-2">
            <span className="text-xs font-bold text-zinc-300 uppercase tracking-wider block">
              7-Stage Evidentiary Lineage Chain
            </span>

            <div className="space-y-1.5 border border-zinc-850 rounded-xl p-3 bg-zinc-900/40">
              {/* 1. SOURCE */}
              <div className="flex items-center gap-2.5 p-2 rounded-lg bg-zinc-900 border border-zinc-800">
                <FileText className="w-4 h-4 text-zinc-400 shrink-0" />
                <div className="min-w-0">
                  <span className="text-[9px] uppercase font-bold text-zinc-400 block font-mono">1. SOURCE</span>
                  <p className="text-xs font-medium text-zinc-200 truncate">Primary Workspace Files</p>
                </div>
              </div>

              <div className="flex justify-center text-zinc-600"><ArrowRight className="w-3 h-3 rotate-90" /></div>

              {/* 2. EXTRACTED CONTENT */}
              <div className="flex items-center gap-2.5 p-2 rounded-lg bg-zinc-900 border border-zinc-800">
                <FileSearch className="w-4 h-4 text-zinc-400 shrink-0" />
                <div className="min-w-0">
                  <span className="text-[9px] uppercase font-bold text-zinc-400 block font-mono">2. EXTRACTED CONTENT</span>
                  <p className="text-xs font-medium text-zinc-200 truncate">Layout Chunks & Parquet Arrow Tables</p>
                </div>
              </div>

              <div className="flex justify-center text-zinc-600"><ArrowRight className="w-3 h-3 rotate-90" /></div>

              {/* 3. EVIDENCE */}
              <div className="flex items-center gap-2.5 p-2 rounded-lg bg-zinc-900 border border-zinc-800">
                <Bookmark className="w-4 h-4 text-zinc-400 shrink-0" />
                <div className="min-w-0">
                  <span className="text-[9px] uppercase font-bold text-zinc-400 block font-mono">3. EVIDENCE</span>
                  <p className="text-xs font-medium text-zinc-200 truncate">
                    {activeEvNode?.label || "Page / Cell / Audio Coordinates"}
                  </p>
                </div>
              </div>

              <div className="flex justify-center text-zinc-600"><ArrowRight className="w-3 h-3 rotate-90" /></div>

              {/* 4. CALCULATION */}
              <div className="flex items-center gap-2.5 p-2 rounded-lg bg-zinc-900 border border-zinc-800">
                <Calculator className="w-4 h-4 text-zinc-400 shrink-0" />
                <div className="min-w-0">
                  <span className="text-[9px] uppercase font-bold text-zinc-400 block font-mono">4. CALCULATION</span>
                  <p className="text-xs font-medium text-zinc-200 truncate">
                    {activeCalcNode?.label || "DuckDB Vectorized SQL / Python Math"}
                  </p>
                </div>
              </div>

              <div className="flex justify-center text-zinc-600"><ArrowRight className="w-3 h-3 rotate-90" /></div>

              {/* 5. CLAIM */}
              <div className="flex items-center gap-2.5 p-2 rounded-lg bg-white text-black font-bold">
                <CheckCircle2 className="w-4 h-4 text-black shrink-0" />
                <div className="min-w-0">
                  <span className="text-[9px] uppercase font-bold block opacity-70 font-mono">5. CLAIM</span>
                  <p className="text-xs font-bold truncate">{claim?.claim_id || "No claim selected"}</p>
                </div>
              </div>

              <div className="flex justify-center text-zinc-600"><ArrowRight className="w-3 h-3 rotate-90" /></div>

              {/* 6. INFERENCE */}
              <div className="flex items-center gap-2.5 p-2 rounded-lg bg-zinc-900 border border-zinc-800">
                <Compass className="w-4 h-4 text-zinc-400 shrink-0" />
                <div className="min-w-0">
                  <span className="text-[9px] uppercase font-bold text-zinc-400 block font-mono">6. INFERENCE</span>
                  <p className="text-xs font-medium text-zinc-200 truncate">Synthesized Cross-Source Correlation</p>
                </div>
              </div>

              <div className="flex justify-center text-zinc-600"><ArrowRight className="w-3 h-3 rotate-90" /></div>

              {/* 7. RECOMMENDATION */}
              <div className="flex items-center gap-2.5 p-2 rounded-lg bg-zinc-900 border border-zinc-800">
                <Lightbulb className="w-4 h-4 text-zinc-400 shrink-0" />
                <div className="min-w-0">
                  <span className="text-[9px] uppercase font-bold text-zinc-400 block font-mono">7. RECOMMENDATION</span>
                  <p className="text-xs font-medium text-zinc-200 truncate">Actionable Strategy Backed by Claims</p>
                </div>
              </div>
            </div>
          </div>

          {/* Reproducibility metadata */}
          {calculationCode && (
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-zinc-300 uppercase tracking-wider">
                  Reproducible Code / SQL
                </span>
                <button
                  type="button"
                  onClick={() => copyToClipboard(calculationCode, "sql")}
                  className="text-[11px] text-zinc-400 hover:text-white inline-flex items-center gap-1 cursor-pointer"
                >
                  {copiedType === "sql" ? <Check className="w-3 h-3 text-white" /> : <Copy className="w-3 h-3" />}
                  <span>{copiedType === "sql" ? "Copied" : "Copy Code"}</span>
                </button>
              </div>
              <div className="bg-zinc-900 p-3 rounded-xl border border-zinc-800 font-mono text-xs space-y-2">
                <code className="text-zinc-100 block break-all leading-relaxed">
                  {calculationCode}
                </code>
                {hashValue && (
                  <div className="flex items-center justify-between pt-2 border-t border-zinc-800 text-xs">
                    <span className="flex items-center gap-1 font-mono text-zinc-400">
                      <Hash className="w-3.5 h-3.5 text-zinc-500" /> SHA-256: {hashValue.slice(0, 16)}...
                    </span>
                    <button
                      type="button"
                      onClick={() => copyToClipboard(hashValue, "hash")}
                      className="text-zinc-400 hover:text-white text-[11px] cursor-pointer"
                    >
                      {copiedType === "hash" ? "Copied" : "Copy Hash"}
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="p-3 border-t border-zinc-850 bg-black text-[11px] text-zinc-400 text-center flex items-center justify-center gap-2 font-mono">
          <ShieldCheck className="w-3.5 h-3.5 text-zinc-400" />
          <span>Evidence Reference Contract</span>
        </div>
      </div>
    </div>
  );
}
