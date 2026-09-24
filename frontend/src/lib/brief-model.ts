/**
 * Derives everything the brief, the source tracks and the inspector show from
 * two persisted records: the saved report (`final_response`) and the lineage
 * graph (`/investigations/{id}/evidence`). Nothing here fetches, times or
 * guesses; every link drawn in the UI is a link present in these records.
 */
import type {
  EpistemicClaim,
  EvidenceLineageGraph,
  InvestigationSession,
  KeyFinding,
  LineageNode,
  Recommendation,
} from "@/types/api";

export type Report = NonNullable<InvestigationSession["final_response"]>;

export interface PassageRef {
  chunkId: string;
  sourceId: string | null;
  sourceName: string;
  modality: string | null;
  content: string;
  chunkIndex: number | null;
  pageNumber: number | null;
  audioStartMs: number | null;
  evidenceIds: string[];
}

export interface CalculationRef {
  id: string;
  type: string;
  code: string;
  output: unknown;
  hash: string | null;
}

export interface BriefClaim {
  claimId: string;
  statement: string;
  status: "VERIFIED" | "REJECTED" | "UNREPORTED";
  errors: string[];
  /** Citation markers: one per distinct cited passage, numbered brief-wide. */
  citations: Array<{ number: number; chunkId: string }>;
  /** Cited evidence ids the lineage could not resolve to a passage. */
  unresolved: string[];
  calculations: Array<{ number: number; calculation: CalculationRef }>;
}

export interface BriefFinding {
  title: string;
  detail: string;
  claim: BriefClaim | null;
  /** How the finding was joined to its claim, if at all. */
  join: "claim_id" | "exact_statement" | null;
}

export interface ChartSpec {
  calculation: CalculationRef;
  calcNumber: number;
  claimId: string;
  labelKey: string;
  valueKey: string;
  rows: Array<{ label: string; value: number }>;
}

export interface UnsupportedItem {
  kind: "claim" | "inference" | "recommendation" | "warning" | "contradiction";
  text: string;
  reasons: string[];
}

export interface BriefModel {
  summary: string;
  findings: BriefFinding[];
  /** Verified claims not shown through a finding (never hidden). */
  otherClaims: BriefClaim[];
  claims: BriefClaim[];
  recommendations: Array<Recommendation & { cited: boolean }>;
  passages: Map<string, PassageRef>;
  /** Passage chunk id → citation number. */
  citationNumbers: Map<string, number>;
  /** Citation number → chunk id (ordered). */
  citationOrder: string[];
  /** Passage chunk id → 1-based claim ordinals that cite it. */
  citedBy: Map<string, number[]>;
  calculations: Map<string, CalculationRef>;
  calcOrder: string[];
  charts: ChartSpec[];
  /** Every evidence passage retrieved by the run (neutral until cited). */
  evidenceChunkIds: Set<string>;
  citedChunkIds: Set<string>;
  verifiedClaimCount: number;
  rejectedCount: number;
  unsupported: UnsupportedItem[];
  sourceIds: Set<string>;
}

const stripPrefix = (value: string, prefix: string) =>
  value.startsWith(prefix) ? value.slice(prefix.length) : value;

export const normalizeStatement = (value: string) => value.replace(/\s+/g, " ").trim();

export interface LineageIndex {
  /** Evidence id (no prefix) → passage. */
  evidenceToPassage: Map<string, PassageRef>;
  passages: Map<string, PassageRef>;
  calculations: Map<string, CalculationRef>;
}

export function indexLineage(graph: EvidenceLineageGraph | null | undefined): LineageIndex {
  const evidenceToPassage = new Map<string, PassageRef>();
  const passages = new Map<string, PassageRef>();
  const calculations = new Map<string, CalculationRef>();
  if (!graph) return { evidenceToPassage, passages, calculations };
  const nodes = new Map<string, LineageNode>(graph.nodes.map((node) => [node.id, node]));
  const sourceOf = new Map<string, LineageNode>();
  const contentOf = new Map<string, LineageNode>();
  for (const edge of graph.edges) {
    if (edge.relation === "EXTRACTED_FROM") {
      const source = nodes.get(edge.source);
      if (source) sourceOf.set(edge.target, source);
    } else if (edge.relation === "SUPPORTED_BY_CONTENT") {
      const content = nodes.get(edge.source);
      if (content) contentOf.set(edge.target, content);
    }
  }
  for (const node of graph.nodes) {
    if (node.type === "calculation") {
      const id = stripPrefix(node.id, "calc_");
      const type = /\(([^)]+)\)/.exec(node.label)?.[1] ?? "calculation";
      calculations.set(id, {
        id,
        type,
        code: typeof node.data?.code === "string" ? node.data.code : "",
        output: node.data?.output,
        hash: typeof node.data?.reproducibility_hash === "string" ? node.data.reproducibility_hash : null,
      });
    }
    if (node.type !== "evidence") continue;
    const evidenceId = stripPrefix(node.id, "ev_");
    const content = contentOf.get(node.id);
    if (!content) continue;
    const chunkId = String(content.data?.content_id ?? stripPrefix(content.id, "content_"));
    const source = sourceOf.get(content.id);
    const locator = (content.data?.locator ?? {}) as Record<string, unknown>;
    const indexMatch = /#(\d+)/.exec(content.label);
    // Chunk nodes are not de-duplicated by the API; group by chunk id here.
    const existing = passages.get(chunkId);
    const passage: PassageRef = existing ?? {
      chunkId,
      sourceId: source ? String(source.data?.source_id ?? stripPrefix(source.id, "src_")) : null,
      sourceName: source?.label ?? "Source unavailable",
      modality: source ? String(source.data?.modality ?? "") || null : null,
      content: typeof content.data?.content === "string" ? content.data.content : "",
      chunkIndex: indexMatch ? Number(indexMatch[1]) : null,
      pageNumber: typeof locator.page_number === "number" ? locator.page_number : null,
      audioStartMs: typeof locator.audio_start_ms === "number" ? locator.audio_start_ms : null,
      evidenceIds: [],
    };
    if (!passage.evidenceIds.includes(evidenceId)) passage.evidenceIds.push(evidenceId);
    passages.set(chunkId, passage);
    evidenceToPassage.set(evidenceId, passage);
  }
  return { evidenceToPassage, passages, calculations };
}

/** Identical repeated claims (same id, statement and citations) are one claim. */
export function dedupeClaims(claims: EpistemicClaim[]): EpistemicClaim[] {
  const seen = new Set<string>();
  return claims.filter((claim) => {
    const key = JSON.stringify([
      claim.claim_id,
      normalizeStatement(claim.statement || ""),
      [...(claim.citations || [])].sort(),
      [...(claim.calculation_ids || [])].sort(),
      claim.verification_status ?? null,
    ]);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

const numericValue = (value: unknown): number | null => {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  return null;
};

/**
 * A chart is drawn only for an SQL calculation cited by a VERIFIED claim whose
 * saved output is at least two rows of exactly one label column and one
 * numeric column. The rows are plotted as saved; nothing is parsed from prose.
 */
export function chartFromCalculation(calculation: CalculationRef): Omit<ChartSpec, "calcNumber" | "claimId"> | null {
  if (calculation.type !== "sql_query") return null;
  const output = calculation.output;
  if (!Array.isArray(output) || output.length < 2 || output.length > 24) return null;
  if (!output.every((row) => row && typeof row === "object" && !Array.isArray(row))) return null;
  const keys = Object.keys(output[0] as Record<string, unknown>);
  if (keys.length !== 2) return null;
  const rows = output as Array<Record<string, unknown>>;
  if (!rows.every((row) => Object.keys(row).length === 2 && keys.every((key) => key in row))) return null;
  const valueKey = keys.find((key) => rows.every((row) => numericValue(row[key]) != null));
  const labelKey = keys.find((key) => key !== valueKey && rows.every((row) => typeof row[key] === "string" || typeof row[key] === "number"));
  if (!valueKey || !labelKey) return null;
  return {
    calculation,
    labelKey,
    valueKey,
    rows: rows.map((row) => ({ label: String(row[labelKey]), value: numericValue(row[valueKey])! })),
  };
}

export function buildBrief(report: Report, graph: EvidenceLineageGraph | null | undefined): BriefModel {
  const lineage = indexLineage(graph);
  const claimsRaw = dedupeClaims(report.claims || []);
  const citationNumbers = new Map<string, number>();
  const citationOrder: string[] = [];
  const calcNumbers = new Map<string, number>();
  const calcOrder: string[] = [];
  const citedBy = new Map<string, number[]>();

  const toBriefClaim = (claim: EpistemicClaim): BriefClaim => {
    const status: BriefClaim["status"] =
      claim.verification_status === "VERIFIED" ? "VERIFIED" : claim.verification_status === "REJECTED" ? "REJECTED" : "UNREPORTED";
    return {
      claimId: claim.claim_id,
      statement: claim.statement,
      status,
      errors: claim.verification_errors || [],
      citations: [],
      unresolved: [],
      calculations: [],
    };
  };
  const claims = claimsRaw.map(toBriefClaim);
  const claimByRaw = new Map(claimsRaw.map((raw, index) => [raw, claims[index]]));

  // Findings join their claim by id, or by an exact (whitespace-normalised)
  // statement match with a VERIFIED claim. No fuzzy matching.
  const verifiedByStatement = new Map<string, EpistemicClaim>();
  for (const raw of claimsRaw) {
    if (raw.verification_status === "VERIFIED") {
      const key = normalizeStatement(raw.statement || "");
      if (!verifiedByStatement.has(key)) verifiedByStatement.set(key, raw);
    }
  }
  const findingJoins = (report.key_findings || []).map((finding: KeyFinding) => {
    const byId = finding.claim_id ? claimsRaw.find((raw) => raw.claim_id === finding.claim_id) : undefined;
    if (byId) return { finding, raw: byId, join: "claim_id" as const };
    const byStatement = verifiedByStatement.get(normalizeStatement(finding.detail || ""));
    if (byStatement) return { finding, raw: byStatement, join: "exact_statement" as const };
    return { finding, raw: undefined, join: null };
  });

  // Number citations in reading order: findings first, then other claims.
  const shownRaw: EpistemicClaim[] = [];
  for (const join of findingJoins) if (join.raw && !shownRaw.includes(join.raw)) shownRaw.push(join.raw);
  const otherRaw = claimsRaw.filter((raw) => raw.verification_status === "VERIFIED" && !shownRaw.includes(raw));
  const ordered = [...shownRaw, ...otherRaw];

  ordered.forEach((raw, ordinal) => {
    const claim = claimByRaw.get(raw)!;
    if (claim.status !== "VERIFIED") return; // only verified claims carry citations
    for (const citation of raw.citations || []) {
      const evidenceId = stripPrefix(String(citation), "ev_");
      const passage = lineage.evidenceToPassage.get(evidenceId);
      if (!passage) {
        claim.unresolved.push(evidenceId);
        continue;
      }
      if (!citationNumbers.has(passage.chunkId)) {
        citationNumbers.set(passage.chunkId, citationOrder.length + 1);
        citationOrder.push(passage.chunkId);
      }
      if (!claim.citations.some((item) => item.chunkId === passage.chunkId)) {
        claim.citations.push({ number: citationNumbers.get(passage.chunkId)!, chunkId: passage.chunkId });
        const list = citedBy.get(passage.chunkId) ?? [];
        if (!list.includes(ordinal + 1)) list.push(ordinal + 1);
        citedBy.set(passage.chunkId, list);
      }
    }
    for (const calcRaw of raw.calculation_ids || []) {
      const calcId = stripPrefix(String(calcRaw), "calc_");
      const calculation = lineage.calculations.get(calcId);
      if (!calculation) continue;
      if (!calcNumbers.has(calcId)) {
        calcNumbers.set(calcId, calcOrder.length + 1);
        calcOrder.push(calcId);
      }
      claim.calculations.push({ number: calcNumbers.get(calcId)!, calculation });
    }
  });

  const charts: ChartSpec[] = [];
  for (const raw of ordered) {
    const claim = claimByRaw.get(raw)!;
    if (claim.status !== "VERIFIED") continue;
    for (const { number, calculation } of claim.calculations) {
      if (charts.some((chart) => chart.calculation.id === calculation.id)) continue;
      const chart = chartFromCalculation(calculation);
      if (chart) charts.push({ ...chart, calcNumber: number, claimId: claim.claimId });
    }
  }

  const findings: BriefFinding[] = findingJoins.map(({ finding, raw, join }) => ({
    title: finding.title,
    detail: finding.detail,
    claim: raw ? claimByRaw.get(raw)! : null,
    join,
  }));

  const citedChunkIds = new Set(citationOrder);
  const evidenceChunkIds = new Set(lineage.passages.keys());
  const verifiedClaimCount = claims.filter((claim) => claim.status === "VERIFIED").length;
  const verifiedCodes = new Set(claims.filter((claim) => claim.status === "VERIFIED").map((claim) => claim.claimId));

  const unsupported: UnsupportedItem[] = [];
  for (const claim of claims) {
    if (claim.status === "REJECTED") unsupported.push({ kind: "claim", text: claim.statement, reasons: claim.errors });
  }
  for (const proposal of report.rejected_proposals || []) {
    const record = proposal as Record<string, unknown>;
    const text = [record.statement, record.action, record.title].find((value) => typeof value === "string" && value.trim()) as string | undefined;
    if (!text) continue;
    const kind: UnsupportedItem["kind"] = "recommendation_id" in record ? "recommendation" : "inference_id" in record ? "inference" : "claim";
    if (kind === "claim" && unsupported.some((item) => item.kind === "claim" && item.text === text)) continue;
    unsupported.push({ kind, text, reasons: Array.isArray(record.verification_errors) ? record.verification_errors.map(String) : [] });
  }
  for (const warning of report.missing_data_warnings || []) unsupported.push({ kind: "warning", text: warning, reasons: [] });
  for (const topic of report.contradictions || []) unsupported.push({ kind: "contradiction", text: topic, reasons: [] });

  const recommendations = (report.recommendations || []).map((item) => ({
    ...item,
    cited: (item.supported_by_claims || []).some((code) => verifiedCodes.has(code)),
  }));

  const sourceIds = new Set<string>();
  lineage.passages.forEach((passage) => passage.sourceId && sourceIds.add(passage.sourceId));

  return {
    summary: report.executive_summary,
    findings,
    otherClaims: otherRaw.map((raw) => claimByRaw.get(raw)!),
    claims,
    recommendations,
    passages: lineage.passages,
    citationNumbers,
    citationOrder,
    citedBy,
    calculations: lineage.calculations,
    calcOrder,
    charts,
    evidenceChunkIds,
    citedChunkIds,
    verifiedClaimCount,
    rejectedCount: claims.filter((claim) => claim.status === "REJECTED").length +
      (report.rejected_proposals || []).filter((item) => !("recommendation_id" in (item as object)) && !("inference_id" in (item as object))).length,
    unsupported,
    sourceIds,
  };
}

/**
 * Figures that appear in both the claim and the passage. This is a
 * deterministic text match computed in the browser, labelled as such, and is
 * never presented as verification.
 */
export function sharedFigures(claim: string, passage: string): string[] {
  const pattern = /(?:[$€£]\s?)?\d[\d,]*(?:\.\d+)?\s?(?:%|[mMbBkK](?![a-z])|million|billion)?|\bQ[1-4]\b|\bFY\s?\d{2,4}\b/g;
  const normalize = (token: string) => token.replace(/\s+/g, "").replace(/,/g, "").toLowerCase();
  const inPassage = new Set((passage.match(pattern) || []).map(normalize));
  const figures: string[] = [];
  for (const token of claim.match(pattern) || []) {
    const trimmed = token.trim();
    if (!trimmed || /^\d$/.test(trimmed)) continue;
    if (inPassage.has(normalize(trimmed)) && !figures.includes(trimmed)) figures.push(trimmed);
  }
  return figures.slice(0, 8);
}

/** Plain-language reasons for saved verification codes. */
export function explainReason(code: string): string {
  const [name] = code.split(":");
  const map: Record<string, string> = {
    SOURCE_DELETED: "Its source was deleted after the brief was saved.",
    DUPLICATE_CLAIM_ID: "The model reused a claim ID, so every claim sharing it was set aside.",
    EVIDENCE_NOT_FOUND: "A cited passage was not found in this investigation.",
    EVIDENCE_CONTENT_MISMATCH: "The quoted text did not match the source passage.",
    CROSS_WORKSPACE_EVIDENCE: "A citation pointed outside this workspace.",
    CROSS_INVESTIGATION_EVIDENCE: "A citation pointed at another investigation.",
    BROKEN_EVIDENCE_SOURCE_CHAIN: "A citation's link back to its source is broken.",
    UNSUPPORTED_CLAIM: "It had no citation or calculation behind it.",
    UNSUPPORTED_INFERENCE: "It did not rest on verified claims.",
    UNSUPPORTED_RECOMMENDATION: "It did not rest on verified claims.",
    VERIFIED_CLAIM_NOT_FOUND: "A supporting claim it relied on was not verified.",
    VERIFIED_INFERENCE_NOT_FOUND: "A supporting inference it relied on was not verified.",
    AMBIGUOUS_CLAIM_REFERENCE: "It referenced a claim ID that matched more than one claim.",
    AMBIGUOUS_INFERENCE_REFERENCE: "It referenced an inference ID that matched more than one inference.",
    CALCULATION_NOT_FOUND: "A cited calculation was not found.",
    INCOMPLETE_CALCULATION: "A cited calculation was incomplete.",
    CROSS_INVESTIGATION_CALCULATION: "A cited calculation belonged to another investigation.",
    CALCULATION_REPRODUCIBILITY_MISMATCH: "A calculation's saved hash did not match its inputs.",
    CALCULATION_INPUT_PROVENANCE_MISSING: "A calculation had no recorded inputs.",
    CALCULATION_SOURCE_NOT_FOUND: "A calculation's source was not found.",
    CALCULATION_CROSS_WORKSPACE_SOURCE: "A calculation read a source outside this workspace.",
  };
  return map[name] ?? name.replace(/_/g, " ").toLowerCase().replace(/^./, (c) => c.toUpperCase());
}
