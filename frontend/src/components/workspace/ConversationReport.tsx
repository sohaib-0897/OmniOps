"use client";

import { ArrowUpRight, Check, FileText } from "lucide-react";
import type {
  EpistemicClaim,
  InvestigationSession,
} from "@/types/api";

interface Props {
  report: NonNullable<InvestigationSession["final_response"]>;
  onInspectClaim: (claim: EpistemicClaim) => void;
  onInspectCitation: (citationId: string) => void;
  onViewFullAnalysis: () => void;
  fullAnalysisOpen: boolean;
}

export function ConversationReport({
  report,
  onInspectClaim,
  onInspectCitation,
  onViewFullAnalysis,
  fullAnalysisOpen,
}: Props) {
  const citationIds = [
    ...new Set(report.claims.flatMap((claim) => claim.citations || [])),
  ];
  const citationNumbers = new Map(
    citationIds.map((citation, index) => [citation, index + 1]),
  );
  const verifiedClaims = report.claims.filter(
    (claim) => claim.verification_status === "VERIFIED",
  );

  return (
    <article className="conversation-answer" aria-labelledby="answer-heading">
      <header className="response-byline">OmniOps <span>Intelligence brief</span></header>

      <section>
        <h2 id="answer-heading" className="sr-only">
          Investigation answer
        </h2>
        <div className="brief-summary">{report.executive_summary.split(/\n\s*\n/).map((paragraph, index) => <p key={index} className="whitespace-pre-wrap">{paragraph}</p>)}</div>
      </section>

      {report.key_findings.length > 0 && (
        <section className="brief-section" aria-labelledby="key-findings-heading">
          <h3 id="key-findings-heading" className="type-heading mb-2">
            Key findings
          </h3>
          <div>
            {report.key_findings.map((finding, index) => {
              const claim = finding.claim_id
                ? report.claims.find(
                    (candidate) => candidate.claim_id === finding.claim_id,
                  )
                : undefined;
              return (
                <article
                  key={`${finding.title}-${index}`}
                  className="brief-finding"
                >
                  <span className="pt-1 font-mono text-xs text-zinc-400">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  <div className="min-w-0">
                    <h4 className="leading-7 text-zinc-100">
                      {finding.title}
                    </h4>
                    <p className="brief-body mt-2">
                      {finding.detail}
                    </p>
                    {claim && (
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        {claim.citations.map((citation) => (
                          <button
                            key={citation}
                            className="inline-citation"
                            title={`Inspect persisted citation ${citation}`}
                            aria-label={`Inspect citation ${citation}`}
                            onClick={() => onInspectCitation(citation)}
                          >
                            [{citationNumbers.get(citation)}]
                          </button>
                        ))}
                        <button
                          className="text-xs text-zinc-400 underline decoration-zinc-700 underline-offset-4 hover:text-zinc-100"
                          onClick={() => onInspectClaim(claim)}
                        >
                          {claim.verification_status === "VERIFIED" ? "Inspect evidence" : claim.verification_status === "REJECTED" ? "Inspect rejected claim" : "Inspect claim · verification not reported"}
                        </button>
                      </div>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        </section>
      )}

      {report.recommendations.length > 0 && (
        <section className="brief-section">
          <h3 className="type-heading">Recommended actions</h3>
          <div className="brief-actions">{report.recommendations.slice(0, 3).map((item, index) => <article className="brief-action" key={item.recommendation_id || index}>
            <h4 className="text-base font-medium">{item.title}</h4>
            <p className="brief-body mt-2">{item.action}</p>
            <div className="mt-2 flex flex-wrap gap-3">{item.supported_by_claims.map(id => { const supporting = report.claims.find(value => value.claim_id === id); return supporting ? <button className="text-xs text-zinc-400 underline decoration-zinc-600 underline-offset-4 hover:text-zinc-100" key={id} onClick={() => onInspectClaim(supporting)}>Supporting evidence · {id}</button> : null; })}</div>
          </article>)}</div>
        </section>
      )}

      {Boolean(report.missing_data_warnings?.length) && <details className="mt-8 text-sm text-zinc-400"><summary>What this analysis cannot establish</summary><ul className="mt-3 space-y-2">{report.missing_data_warnings?.map((warning, index) => <li key={index} className="leading-6">{warning}</li>)}</ul></details>}

      <footer className="mt-10 flex flex-wrap items-center justify-between gap-3 border-t border-zinc-800 pt-5">
        <p className="flex items-center gap-2 text-xs text-zinc-400">
          <Check className="h-3.5 w-3.5" />
          {verifiedClaims.length} verified {verifiedClaims.length === 1 ? "claim" : "claims"}
          {citationIds.length > 0 && (
            <span>· {citationIds.length} source {citationIds.length === 1 ? "reference" : "references"}</span>
          )}
        </p>
        <button
          className="btn-ghost"
          aria-expanded={fullAnalysisOpen}
          aria-controls="full-analysis"
          onClick={onViewFullAnalysis}
        >
          <FileText className="h-4 w-4" />
          {fullAnalysisOpen ? "Hide full analysis" : "View full analysis"}
          <ArrowUpRight className="h-3.5 w-3.5" />
        </button>
      </footer>
    </article>
  );
}
