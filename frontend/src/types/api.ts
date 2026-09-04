export interface ResponseEnvelope<T> {
  success: boolean;
  data: T | null;
  error: {
    code: string;
    message: string;
    details: Array<{ code: string; message: string; field?: string }>;
  } | null;
  meta: {
    timestamp: string;
    request_id?: string;
  };
}

export interface User {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  created_at: string;
}

export interface AuthSession {
  user: User;
  token: {
    access_token: string;
    token_type: string;
    expires_in_seconds: number;
  };
}

export interface Workspace {
  id: string;
  name: string;
  description?: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  user_role?: "owner" | "editor" | "viewer";
  members_count?: number;
  documents_count?: number;
  tables_count?: number;
}

export interface SourceDocument {
  id: string;
  workspace_id: string;
  file_name: string;
  mime_type: string;
  byte_size: number;
  sha256_hash: string;
  modality: "pdf" | "docx" | "spreadsheet" | "audio" | "image" | "text" | "web";
  processing_status: "pending" | "processing" | "ready" | "failed";
  error_message?: string;
  doc_metadata: Record<string, any>;
  created_at: string;
}

export interface DocumentChunk {
  id: string;
  source_id: string;
  chunk_index: number;
  content: string;
  modality: string;
  page_number?: number;
  cell_range?: string;
  audio_start_ms?: number;
  audio_end_ms?: number;
  chunk_metadata: Record<string, any>;
  extraction_method: string;
  embedding_provider?: string;
  embedding_model?: string;
  embedding_dimension?: number;
  semantic_search_status: string;
  lexical_search_status: string;
}

export interface TableColumnStat {
  name: string;
  type: string;
  null_count: number;
  null_percentage: number;
  unique_count: number;
  sample_values: string[];
  min?: number | string;
  max?: number | string;
  mean?: number;
}

export interface TabularDataset {
  id: string;
  workspace_id: string;
  source_id: string;
  table_name: string;
  row_count: number;
  column_count: number;
  schema_definition: TableColumnStat[];
  created_at: string;
}

export interface TablePreview {
  table_name: string;
  row_count: number;
  column_count: number;
  columns: string[];
  sample_rows: Record<string, any>[];
  schema_definition: TableColumnStat[];
}

export interface AgentStep {
  id: string;
  step_number: number;
  step_type: "plan" | "tool_call" | "reflection" | "verification" | "synthesis";
  user_activity_summary: string;
  tool_name?: string;
  tool_input?: Record<string, any>;
  tool_output?: Record<string, any>;
  duration_ms: number;
  created_at: string;
}

export interface EpistemicClaim {
  claim_id: string;
  statement: string;
  epistemic_type: "fact" | "calculation" | "inference" | "assumption" | "recommendation";
  confidence_score: number | null;
  citations: string[];
  calculation_ids: string[];
  calculation_summary?: string;
  supporting_claims: string[];
  verification_status?: "VERIFIED" | "REJECTED";
  verification_errors?: string[];
}

export interface Inference {
  inference_id: string;
  statement: string;
  supporting_claim_ids: string[];
  verification_status?: "VERIFIED" | "REJECTED";
  verification_errors?: string[];
}

export interface Recommendation {
  recommendation_id: string;
  title: string;
  action: string;
  priority: "high" | "medium" | "low";
  supported_by_claims: string[];
  supporting_inference_ids: string[];
}

export interface InvestigationSession {
  id: string;
  workspace_id: string;
  user_id: string;
  objective: string;
  status: "planning" | "running" | "verifying" | "synthesizing" | "completed" | "failed" | "cancelled";
  current_state?: "created" | "planning" | "ready" | "executing" | "observing" | "verifying" | "replanning" | "synthesizing" | "completed" | "failed" | "cancelled";
  plan_version?: number;
  failure_code?: string;
  failure_message?: string;
  final_response?: {
    executive_summary: string;
    key_findings: Array<{ title: string; detail: string; claim_id?: string }>;
    claims: EpistemicClaim[];
    inferences: Inference[];
    recommendations: Recommendation[];
    rejected_proposals: Array<Record<string, any>>;
    missing_data_warnings?: string[];
    contradictions?: string[];
  };
  token_usage: Record<string, any>;
  error_message?: string;
  created_at: string;
  completed_at?: string;
  steps?: AgentStep[];
}

export interface EvidenceItem {
  id: string;
  session_id: string;
  source_id: string;
  source_name?: string;
  source_modality?: string;
  chunk_id?: string;
  page_number?: number;
  cell_range?: string;
  audio_start_ms?: number;
  audio_end_ms?: number;
  exact_quote?: string;
  coordinates?: Record<string, any>;
  confidence_score: number | null;
  created_at: string;
}

export interface CalculationRecord {
  id: string;
  session_id: string;
  calculation_type: string;
  formula_or_code: string;
  input_values: Record<string, any>;
  computed_output: any;
  reproducibility_hash: string;
  created_at: string;
}

export interface LineageNode {
  id: string;
  type: string;
  label: string;
  data: Record<string, any>;
}

export interface LineageEdge {
  source: string;
  target: string;
  relation: string;
}

export interface EvidenceLineageGraph {
  session_id: string;
  nodes: LineageNode[];
  edges: LineageEdge[];
  claims_count: number;
  citations_count: number;
  calculations_count: number;
}
