// API client (ARCH-010). Attaches `Authorization: Bearer` from localStorage
// (see ../auth.ts) to every call; a 401 clears the stored token and sends the
// user back to /login (a full reload — simplest reliable way to reset all
// React state for an MVP tool, not worth a pub-sub layer for).
import type {
  DevLoginResponse,
  EscalationDetail,
  EscalationSummary,
  HitlDecisionResponse,
  QueryJobAccepted,
  QueryJobStatus,
  QueryResponse,
  QueueResult,
  QueueResultDetail,
  RatingRoundSubmitResponse,
  RatingSubmission,
  RubricDomain,
} from "../types";
import { clearStoredAuth, getStoredAuth } from "../auth";

const BASE = "/api";

// Every patient-scoped/answer-producing call in this app is for direct
// clinical use of the reported guideline content (ARCH-034 purpose-of-use).
// No other purpose value is exercised anywhere in this system yet.
const PURPOSE = "clinical_care";

class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const auth = getStoredAuth();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(auth ? { Authorization: `Bearer ${auth.token}` } : {}),
    ...((init?.headers as Record<string, string>) ?? {}),
  };
  const res = await fetch(`${BASE}${path}`, { ...init, headers });
  if (res.status === 401) {
    clearStoredAuth();
    if (window.location.pathname !== "/login") window.location.href = "/login";
    throw new ApiError(401, "session expired");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) detail = body.detail;
    } catch {
      /* body wasn't JSON; keep statusText */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  devLogin: (email: string) =>
    req<DevLoginResponse>("/auth/dev-login", { method: "POST", body: JSON.stringify({ email }) }),

  submitQuery: (body: {
    question: string;
    conversation_id?: string;
    patient_id?: string;
    hospital_constraint?: string;
  }) =>
    req<QueryResponse>("/query", {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "X-Purpose-Of-Use": PURPOSE },
    }),

  submitQueryAsync: (body: {
    question: string;
    conversation_id?: string;
    patient_id?: string;
    hospital_constraint?: string;
  }) =>
    req<QueryJobAccepted>("/query/async", {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "X-Purpose-Of-Use": PURPOSE },
    }),

  getQueryJob: (jobId: string) => req<QueryJobStatus>(`/query/jobs/${jobId}`),

  getRubricDomains: () => req<RubricDomain[]>("/rubric/domains"),

  getReviewQueue: () => req<QueueResult[]>("/review-queue"),

  getReviewQueueItem: (resultId: string) =>
    req<QueueResultDetail>(`/review-queue/${resultId}`),

  // Both HITL axes, one submission (ARCH §13.2 "Both axes together"): every
  // rank-mode rating includes an accept-axis decision. Exactly two tasks —
  // no reason code is sent (that's only required by the separate
  // `submitHitlDecision` escalation-resolution call below), matching
  // `RatingRoundRequest`'s schema (DEVIATIONS #100). `accept_edited_answer`
  // is always optional, sent only if the ranker chose to write one
  // (DEVIATIONS #101) — never required for `partial_accept`.
  submitRating: (resultId: string, submission: RatingSubmission) =>
    req<RatingRoundSubmitResponse>(`/rubric/results/${resultId}/ratings`, {
      method: "POST",
      body: JSON.stringify({
        scores: Object.entries(submission.scores).map(([domain_code, score]) => ({
          domain_code,
          score,
        })),
        comment: submission.comment || undefined,
        accept_action: submission.accept.action,
        accept_edited_answer:
          submission.accept.action === "partial_accept"
            ? submission.accept.editedAnswer || undefined
            : undefined,
      }),
    }),

  listEscalations: (state?: string) =>
    req<EscalationSummary[]>(`/hitl/escalations${state ? `?state=${state}` : ""}`),

  getEscalation: (escalationId: string) =>
    req<EscalationDetail>(`/hitl/escalations/${escalationId}`),

  submitHitlDecision: (
    escalationId: string,
    body: { action: string; edited_answer?: string; reason_code?: string },
  ) =>
    req<HitlDecisionResponse>(`/hitl/escalations/${escalationId}/decision`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
};

export { ApiError };
