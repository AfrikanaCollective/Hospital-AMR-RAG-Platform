// Minimal API client (ARCH-010). Phase 5 replaces with a generated client.
import type { QueryResponse, RubricDomain } from "../types";

const BASE = "/api";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return (await res.json()) as T;
}

export const api = {
  submitQuery: (body: {
    question: string;
    conversation_id?: string;
    patient_id?: string;
    hospital_constraint?: string;
  }) =>
    req<QueryResponse>("/query", {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "X-Purpose-Of-Use": "treatment" },
    }),

  getRubricDomains: () => req<RubricDomain[]>("/rubric/domains"),

  getReviewQueue: () => req<unknown[]>("/review-queue"),
};
