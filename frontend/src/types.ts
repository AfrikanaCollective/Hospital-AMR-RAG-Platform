// Shared types — kept aligned with the backend OpenAPI schema (ARCH-010).
// Phase 5 generates these from /api/openapi.json; this is the hand-written seed.

export type ObservedOutcome =
  | "well_supported"
  | "missing_info"
  | "no_guideline"
  | "escalated";

export type SegmentType = "claim" | "framing";

export interface Citation {
  citation_id: string;
  document_id: string;
  document_title: string;
  version_label: string;
  version_status: "active" | "superseded" | "withdrawn";
  chunk_id: string;
  section_number?: string | null;
  section_path?: string | null;
  page_start: number;
  page_end: number;
  char_start: number;
  char_end: number;
  quote: string;
}

export interface AnswerSegment {
  type: SegmentType;
  text: string;
  citation_ids: string[];
  grounding_note?: string | null;
}

export interface EscalationInfo {
  escalation_id: string;
  trigger_code: string;
  message: string;
}

export interface QueryResponse {
  conversation_id: string;
  message_id: string;
  observed_outcome: ObservedOutcome;
  scope_label: string;
  segments: AnswerSegment[];
  citations: Citation[];
  escalation?: EscalationInfo | null;
  disclaimer: string; // always present (ARCH-037)
}

// Rubric (rank mode) — 11 domains, 5-point Likert (PRD-040).
export interface RubricDomain {
  code: string;
  ordinal: number;
  name: string;
  definition: string;
  anchor_1: string;
  anchor_2: string;
  anchor_3: string;
  anchor_4: string;
  anchor_5: string;
  required: boolean;
}

export type AcceptAction = "full_accept" | "partial_accept" | "reject";
