"use client";
import { useState } from "react";
import {
  AlertTriangle,
  ArrowUpRight,
  Clipboard,
  Calculator,
  Compass,
  FileCheck2,
  Lightbulb,
} from "lucide-react";
import { InvestigationSession, EpistemicClaim } from "@/types/api";
import { MetricChartRenderer } from "./MetricChartRenderer";
import { ErrorState, StatusBadge } from "@/components/ui/Primitives";

interface Props {
  report: NonNullable<InvestigationSession["final_response"]>;
  onInspectClaim: (claim: EpistemicClaim) => void;
  onInspectCitation: (citationId: string) => void;
}
export function ExecutiveReportView({
  report,
  onInspectClaim,
  onInspectCitation,
}: Props) {
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState<string | null>(null);
  const copy = async () => {
    const sections = [
      "# Investigation report",
      report.executive_summary,
      "## Claims",
      ...report.claims.map(
        (claim) =>
          `- [${claim.epistemic_type}; ${claim.verification_status || "Not reported"}] ${claim.statement} ${claim.citations.join(", ")}`,
      ),
      "## Inferences",
      ...(report.inferences || []).map((item) => item.statement),
      "## Recommendations",
      ...report.recommendations.map((item) => `${item.title}: ${item.action}`),
      "## Conflicting evidence",
      ...(report.contradictions || []),
      "## Limitations",
      ...(report.missing_data_warnings || []),
    ];
    try {
      await navigator.clipboard.writeText(sections.join("\n\n"));
      setCopied(true);
      setCopyError(null);
    } catch {
      setCopyError(
        "Copy is unavailable. Select the report text and copy it manually.",
      );
    }
  };
  const citations = [
    ...new Set(report.claims.flatMap((claim) => claim.citations)),
  ];
  const citationNumbers = new Map(
    citations.map((citation, index) => [citation, index + 1]),
  );
  const calculationClaims = report.claims.filter(
    (claim) =>
      claim.epistemic_type === "calculation" || claim.calculation_ids.length > 0,
  );
  return (
    <div className="report-stack">
      <section id="summary" className="report-section">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="mt-2 text-lg font-semibold tracking-tight">
              Executive summary
            </h2>
          </div>
          <button onClick={() => void copy()} className="btn-secondary">
            <Clipboard className="h-3.5 w-3.5" />
            {copied ? "Copied" : "Copy report"}
          </button>
        </div>
        <p className="mt-5 whitespace-pre-wrap text-sm leading-7 text-zinc-300">
          {report.executive_summary}
        </p>
        <p className="meta-copy mt-5 border-t border-zinc-800 pt-3">
          Verification checks evidence references. It does not independently
          establish semantic truth.
        </p>
        {copyError && (
          <div className="mt-3">
            <ErrorState message={copyError} />
          </div>
        )}
      </section>
      <MetricChartRenderer
        claims={report.claims}
        recommendations={report.recommendations}
      />
      {report.key_findings?.length > 0 && (
        <section>
          <h2 className="section-title mb-3">Key findings</h2>
          <div className="divide-y divide-zinc-800">
            {report.key_findings.map((finding, index) => (
              <article
                key={`${finding.title}-${index}`}
                className="py-3 first:pt-0"
              >
                <h3 className="text-sm font-medium">{finding.title}</h3>
                <p className="body-copy mt-1">{finding.detail}</p>
                {finding.claim_id &&
                  report.claims.some(
                    (claim) => claim.claim_id === finding.claim_id,
                  ) && (
                    <button
                      className="citation mt-2"
                      onClick={() =>
                        onInspectClaim(
                          report.claims.find(
                            (claim) => claim.claim_id === finding.claim_id,
                          )!,
                        )
                      }
                    >
                      {finding.claim_id}
                      <ArrowUpRight className="h-3 w-3" />
                    </button>
                  )}
              </article>
            ))}
          </div>
        </section>
      )}
      <section id="claims">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="section-title">Claims</h2>
          <span className="meta-copy">{report.claims.length} recorded</span>
        </div>
        {report.claims.length === 0 ? (
          <p className="meta-copy">
            No supported claims were produced. Review the limitations below.
          </p>
        ) : (
          <div className="divide-y divide-zinc-800">
            {report.claims.map((claim) => {
              const Icon =
                claim.epistemic_type === "calculation"
                  ? Calculator
                  : claim.epistemic_type === "inference"
                    ? Compass
                    : claim.epistemic_type === "recommendation"
                      ? Lightbulb
                      : FileCheck2;
              return (
                <article
                  key={claim.claim_id}
                  className="claim-row"
                >
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <Icon className="h-4 w-4 text-zinc-400" />
                    <span className="text-xs font-medium capitalize text-zinc-300">
                      {claim.epistemic_type}
                    </span>
                    <span className="mono-copy">{claim.claim_id}</span>
                    <StatusBadge
                      status={claim.verification_status || "not_reported"}
                      label={
                        claim.verification_status === "VERIFIED"
                          ? "References verified"
                          : claim.verification_status
                            ? undefined
                            : "Verification not reported"
                      }
                    />
                  </div>
                  <button
                    onClick={() => onInspectClaim(claim)}
                    className="w-full text-left text-sm leading-7 text-zinc-200 hover:text-white"
                  >
                    {claim.statement}
                  </button>
                  {claim.calculation_summary && (
                    <details className="mt-3 text-xs text-zinc-400">
                      <summary>Calculation · formula and lineage</summary>
                      <pre className="mt-3 whitespace-pre-wrap break-words rounded-md border border-zinc-800 bg-[#0d0e10] p-3 text-xs leading-6">
                        {claim.calculation_summary}
                      </pre>
                    </details>
                  )}
                  {claim.verification_errors?.length ? (
                    <ul className="mt-3 space-y-1 text-xs text-amber-200">
                      {claim.verification_errors.map((error) => (
                        <li key={error}>{error}</li>
                      ))}
                    </ul>
                  ) : null}
                  {claim.citations.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2">
                      {claim.citations.map((citation) => (
                        <button
                          className="citation"
                          key={citation}
                          title={citation}
                          aria-label={`Inspect citation ${citation}`}
                          onClick={() => onInspectCitation(citation)}
                        >
                          [{citationNumbers.get(citation)}]
                          <ArrowUpRight className="h-3 w-3" />
                        </button>
                      ))}
                    </div>
                  )}
                </article>
              );
            })}
          </div>
        )}
      </section>
      {calculationClaims.length > 0 && (
        <section id="calculations">
          <h2 className="section-title mb-3">Calculations</h2>
          <div className="divide-y divide-zinc-800 border-y border-zinc-800">
            {calculationClaims.map((claim) => (
              <article key={claim.claim_id} className="py-4">
                <div className="flex flex-wrap items-center gap-2">
                  <Calculator className="h-4 w-4 text-zinc-400" />
                  <span className="mono-copy">{claim.claim_id}</span>
                  <StatusBadge status={claim.verification_status || "not_reported"} />
                </div>
                <p className="body-copy mt-2">{claim.statement}</p>
                {claim.calculation_summary && (
                  <pre className="mt-3 whitespace-pre-wrap break-words rounded-md border border-zinc-800 bg-[#0d0e10] p-3 text-xs leading-6 text-zinc-300">
                    {claim.calculation_summary}
                  </pre>
                )}
                <button className="btn-ghost mt-2 h-8 px-0" onClick={() => onInspectClaim(claim)}>
                  Inspect calculation lineage
                  <ArrowUpRight className="h-3 w-3" />
                </button>
              </article>
            ))}
          </div>
        </section>
      )}
      {report.contradictions?.length ? (
        <section className="rounded-md border border-amber-900/70 p-4">
          <h2 className="section-title flex items-center gap-2">
            <AlertTriangle className="h-4 w-4 text-amber-200" />
            Conflicting evidence
          </h2>
          <ul className="mt-3 space-y-3 text-sm leading-6 text-zinc-300">
            {report.contradictions.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {report.inferences?.length > 0 && (
        <section>
          <h2 className="section-title mb-3">Inferences</h2>
          <p className="meta-copy mb-3">
            Interpretations supported by claims, distinct from verified facts.
          </p>
          {report.inferences.map((item) => (
            <article
              key={item.inference_id}
              className="mb-3 border-l-2 border-zinc-600 pl-4"
            >
              <p className="body-copy">{item.statement}</p>
              <p className="mono-copy mt-2">
                {item.supporting_claim_ids.join(" · ") ||
                  "No supporting claims reported"}
              </p>
            </article>
          ))}
        </section>
      )}
      {report.recommendations.length > 0 && (
        <section>
          <h2 className="section-title mb-3">Recommendations</h2>
          <div className="space-y-3">
            {report.recommendations.map((item) => (
              <article
                key={item.recommendation_id || item.title}
                className="report-section"
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <h3 className="text-sm font-medium">{item.title}</h3>
                  <span className="text-[11px] capitalize text-zinc-400">
                    {item.priority} priority
                  </span>
                </div>
                <p className="body-copy mt-2">{item.action}</p>
                <div className="mt-3 flex flex-wrap gap-2">
                  {item.supported_by_claims.map((id) => {
                    const claim = report.claims.find(
                      (candidate) => candidate.claim_id === id,
                    );
                    return claim ? (
                      <button
                        key={id}
                        className="citation"
                        onClick={() => onInspectClaim(claim)}
                      >
                        {id}
                        <ArrowUpRight className="h-3 w-3" />
                      </button>
                    ) : (
                      <span key={id} className="mono-copy">
                        {id}
                      </span>
                    );
                  })}
                </div>
              </article>
            ))}
          </div>
        </section>
      )}
      {report.missing_data_warnings?.length ? (
        <section className="report-section">
          <h2 className="section-title">Caveats and limitations</h2>
          <ul className="mt-3 list-disc space-y-2 pl-4 text-xs leading-6 text-zinc-300">
            {report.missing_data_warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </section>
      ) : null}
      {report.rejected_proposals?.length > 0 && (
        <details className="report-section text-xs text-zinc-400">
          <summary>
            {report.rejected_proposals.length} rejected proposals
          </summary>
          <p className="mt-3 leading-6">
            These proposals were excluded from the supported findings.
          </p>
          {report.rejected_proposals.map((item, index) => (
            <p key={index} className="mt-3 break-words leading-6">
              {String(
                item.statement ||
                  item.reason ||
                  item.title ||
                  "Proposal details not reported",
              )}
            </p>
          ))}
        </details>
      )}
      {citations.length > 0 && (
        <section>
          <h2 className="section-title mb-3">Source references</h2>
          <div className="flex flex-wrap gap-2">
            {citations.map((citation, index) => (
              <button
                key={citation}
                className="citation"
                title={citation}
                onClick={() => onInspectCitation(citation)}
              >
                [{index + 1}] Reference
                <ArrowUpRight className="h-3 w-3" />
              </button>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
