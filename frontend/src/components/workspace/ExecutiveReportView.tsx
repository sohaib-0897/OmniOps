"use client";

import React, { useState } from "react";
import { InvestigationSession, EpistemicClaim } from "@/types/api";
import {
  FileCheck,
  Calculator,
  Compass,
  Lightbulb,
  CheckCircle,
  AlertTriangle,
  ExternalLink,
  ShieldCheck,
  Copy,
  Check,
  Bookmark,
} from "lucide-react";
import { MetricChartRenderer } from "./MetricChartRenderer";

interface Props {
  report: NonNullable<InvestigationSession["final_response"]>;
  onInspectClaim: (claim: EpistemicClaim) => void;
  onInspectCitation: (citationId: string) => void;
}

export function ExecutiveReportView({ report, onInspectClaim, onInspectCitation }: Props) {
  const [copied, setCopied] = useState(false);

  const getEpistemicBadge = (type: string) => {
    switch (type.toLowerCase()) {
      case "fact":
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-semibold bg-zinc-900 text-zinc-200 border border-zinc-750 px-2 py-0.5 rounded">
            <FileCheck className="w-3 h-3 text-zinc-300" /> Fact
          </span>
        );
      case "calculation":
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-mono bg-zinc-900 text-white border border-zinc-750 px-2 py-0.5 rounded font-semibold">
            <Calculator className="w-3 h-3 text-zinc-300" /> Calc
          </span>
        );
      case "inference":
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-semibold bg-zinc-900 text-zinc-300 border border-dashed border-zinc-700 px-2 py-0.5 rounded">
            <Compass className="w-3 h-3 text-zinc-400" /> Inference
          </span>
        );
      case "recommendation":
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-semibold bg-zinc-900 text-zinc-300 border border-zinc-750 px-2 py-0.5 rounded">
            <Lightbulb className="w-3 h-3 text-zinc-400" /> Recommendation
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 text-[10px] font-medium bg-zinc-900 text-zinc-400 border border-zinc-800 px-2 py-0.5 rounded">
            Observation
          </span>
        );
    }
  };

  const handleCopyReport = async () => {
    try {
      const claimsMarkdown = report.claims
        .map((c) => `- **[${c.epistemic_type.toUpperCase()}] ${c.claim_id}**: ${c.statement}${c.confidence_score == null ? "" : ` (${(c.confidence_score * 100).toFixed(0)}% confidence)`}`)
        .join("\n");

      const recsMarkdown = report.recommendations
        .map((r) => `- **${r.title}** (${r.priority.toUpperCase()}): ${r.action}`)
        .join("\n");

      const fullMarkdown = `# Investigation Report\n\n## Summary\n${report.executive_summary}\n\n## Analytical Claims\n${claimsMarkdown}\n\n## Recommendations\n${recsMarkdown}\n\n---\n*OmniOps evidence reference contract*`;

      await navigator.clipboard.writeText(fullMarkdown);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy report:", err);
    }
  };

  return (
    <div className="space-y-5 font-sans">
      {/* 1. Executive Summary */}
      <div className="border border-zinc-800 bg-zinc-950 rounded-2xl p-5 sm:p-6 space-y-4 shadow-xl">
        <div className="flex items-center justify-between flex-wrap gap-2 pb-3 border-b border-zinc-850">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[10px] font-mono uppercase font-bold tracking-widest text-zinc-400 bg-zinc-900 px-2 py-0.5 rounded border border-zinc-800">
                Evidence-Referenced Briefing
              </span>
            </div>
            <h2 className="text-base sm:text-lg font-bold text-white tracking-tight mt-1.5">
              Executive Findings
            </h2>
          </div>

          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 text-xs text-zinc-300 font-semibold bg-zinc-900 border border-zinc-800 px-3 py-1 rounded-lg">
              <ShieldCheck className="w-3.5 h-3.5 text-zinc-400" />
              Evidence Lineage
            </span>
            <button
              type="button"
              onClick={handleCopyReport}
              className="inline-flex items-center gap-1.5 text-xs font-semibold text-zinc-300 hover:text-white bg-zinc-900 hover:bg-zinc-850 border border-zinc-800 px-3 py-1 rounded-lg transition-colors cursor-pointer"
              title="Copy Report Markdown"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-white" />
                  <span className="text-white font-bold">Copied</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5 text-zinc-400" />
                  <span>Copy Report</span>
                </>
              )}
            </button>
          </div>
        </div>

        <p className="text-xs sm:text-sm text-zinc-200 leading-relaxed font-sans">
          {report.executive_summary}
        </p>
      </div>

      {/* 2. Key Metrics & KPIs */}
      <MetricChartRenderer
        claims={report.claims}
        recommendations={report.recommendations}
      />

      {/* 3. Analytical claims */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-xs font-bold text-zinc-300 uppercase tracking-wider flex items-center gap-2">
            <span>Analytical Claims ({report.claims.length})</span>
          </h3>
          <span className="text-[10px] text-zinc-500 font-mono">Click any claim to inspect 7-stage lineage</span>
        </div>

        <div className="space-y-2">
          {report.claims.map((claim) => (
            <div
              key={claim.claim_id}
              role="button"
              tabIndex={0}
              onClick={() => onInspectClaim(claim)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  onInspectClaim(claim);
                }
              }}
              className="border border-zinc-850 bg-zinc-950 hover:bg-zinc-900 hover:border-zinc-700 rounded-xl p-4 transition-all cursor-pointer space-y-2 group text-left outline-none focus-visible:ring-1 focus-visible:ring-zinc-400"
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs font-bold text-white">
                    {claim.claim_id}
                  </span>
                  {getEpistemicBadge(claim.epistemic_type)}
                </div>
                <div className="flex items-center gap-1 text-xs text-zinc-400 group-hover:text-white font-semibold opacity-0 group-hover:opacity-100 transition-opacity">
                  <span>Inspect Proof</span>
                  <ExternalLink className="w-3 h-3" />
                </div>
              </div>

              <p className="text-xs sm:text-sm font-medium text-zinc-200 group-hover:text-white transition-colors leading-snug">
                {claim.statement}
              </p>

              {claim.calculation_summary && (
                <div className="bg-zinc-900 rounded-lg p-2.5 font-mono text-xs text-zinc-300 border border-zinc-800 space-y-1">
                  <span className="text-[10px] font-bold text-zinc-400 block uppercase">
                    Reproducible Formula / SQL:
                  </span>
                  <code className="text-xs text-zinc-100 block break-all">
                    {claim.calculation_summary}
                  </code>
                </div>
              )}

              {claim.citations && claim.citations.length > 0 && (
                <div className="flex items-center gap-2 flex-wrap pt-2 border-t border-zinc-850">
                  <span className="text-xs text-zinc-400 font-semibold flex items-center gap-1">
                    <Bookmark className="w-3 h-3 text-zinc-400" /> Citations:
                  </span>
                  {claim.citations.map((citId, idx) => (
                    <button
                      key={citId}
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        onInspectCitation(citId);
                      }}
                      className="inline-flex items-center gap-1 text-[10px] font-semibold bg-zinc-900 hover:bg-zinc-850 text-zinc-300 hover:text-white border border-zinc-800 px-2 py-0.5 rounded transition-all cursor-pointer font-mono"
                      title="Inspect Citation Source"
                    >
                      [#{idx + 1}] Source Coordinate
                    </button>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* 4. Strategic Recommendations */}
      {report.recommendations && report.recommendations.length > 0 && (
        <div className="space-y-3">
          <h3 className="text-xs font-bold text-zinc-300 uppercase tracking-wider flex items-center gap-1.5">
            <Lightbulb className="w-4 h-4 text-zinc-400" />
            <span>Strategic Recommendations ({report.recommendations.length})</span>
          </h3>

          <div className="space-y-2">
            {report.recommendations.map((rec, idx) => (
              <div
                key={idx}
                className="border border-zinc-850 bg-zinc-950 rounded-xl p-4 space-y-2"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs sm:text-sm font-bold text-zinc-100 flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-zinc-400 shrink-0" />
                    {rec.title}
                  </span>
                  <span
                    className={`text-[9px] font-bold uppercase px-2 py-0.5 rounded font-mono border ${
                      rec.priority === "high"
                        ? "bg-zinc-900 text-white border-zinc-700 font-bold"
                        : "bg-zinc-900 text-zinc-400 border-zinc-800"
                    }`}
                  >
                    {rec.priority} Priority
                  </span>
                </div>

                <p className="text-xs text-zinc-300 leading-relaxed font-sans">
                  {rec.action}
                </p>

                {rec.supported_by_claims && rec.supported_by_claims.length > 0 && (
                  <div className="flex items-center gap-1.5 text-xs text-zinc-400 pt-1">
                    <span className="font-semibold text-[10px]">Supported by:</span>
                    {rec.supported_by_claims.map((claimId) => (
                      <span
                        key={claimId}
                        className="font-mono text-[10px] font-bold text-zinc-200 bg-zinc-900 border border-zinc-800 px-1.5 py-0.5 rounded"
                      >
                        {claimId}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* 5. Data Boundary Observations */}
      {report.missing_data_warnings && report.missing_data_warnings.length > 0 && (
        <div className="p-4 rounded-xl border border-zinc-800 bg-zinc-950 space-y-2">
          <div className="flex items-center gap-2 text-xs font-bold text-zinc-300">
            <AlertTriangle className="w-4 h-4 text-zinc-400" />
            <span>Data Boundary Observations</span>
          </div>
          <ul className="list-disc list-inside text-xs text-zinc-400 space-y-1">
            {report.missing_data_warnings.map((w, idx) => (
              <li key={idx}>{w}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
