import type { AcceptAction, AcceptAxisValue } from "./types";

// Accept axis (PRD-032, ARCH §13.2) constants/helpers — pulled out of
// components/AcceptAxisControls.tsx (which stays component-only, so React
// Fast Refresh can keep working there) but documented alongside its two real
// call sites, which now genuinely differ on whether a reason is asked for:
//  - RubricForm: the rank-mode rating_round, where BOTH axes are captured in
//    ONE combined submission (ARCH §13.2 "Both axes together"). A ranker's
//    task is exactly two things — the 11-domain rubric and the accept-axis
//    pick — nothing more: no reason/justification text is collected, and
//    submitting a rating never creates or touches a `hitl.escalation`
//    (DEVIATIONS.md #100, correcting #99's carried-over `requireReason`
//    default). Passes `requireReason={false}`.
//  - ReviewPage's EscalationDecisionForm: resolving a `hitl.escalation`
//    directly — a different, single-item, accountability-bearing workflow
//    where a reason code is still required for reject/partial_accept/
//    out_of_scope, matching the backend's `HitlDecisionRequest`. Uses the
//    default (`requireReason={true}`).
//
// Effects on state are defined server-side:
//  - full_accept   : answer released as-is; provisional context -> reviewer_accepted
//  - partial_accept: reviewer-edited version canonical; only retained context kept
//  - reject        : answer withheld/retracted; ALL provisional context rolled back
//  - out_of_scope  : same rollback as reject, but judges the REQUEST, not the
//                    attempted answer (DEVIATIONS.md #84) — this should never
//                    have reached synthesis/escalation at all
//
// `partial_accept` uses `edited_answer` (a full-text rewrite), not span-level
// `span_actions`: the source answer text (an escalation's stored
// `candidate_answer`, or a rank-mode result's `answer`) is already flattened
// to plain text by the time it's persisted — the original per-segment
// citation_ids/type structure doesn't survive — so a faithful span-index
// editor isn't buildable against what the API actually returns. Neither the
// ranker nor a reviewer resolving an escalation is ever required to provide
// it, though (DEVIATIONS.md #101): it's optional in both workflows — the
// accepted-context split alone is a complete, valid `partial_accept`.
export const ACCEPT_ACTIONS: AcceptAction[] = [
  "full_accept",
  "partial_accept",
  "reject",
  "out_of_scope",
];
export const ACCEPT_REASON_REQUIRED: AcceptAction[] = ["reject", "partial_accept", "out_of_scope"];

export function defaultAcceptAxisValue(candidateAnswer?: string | null): AcceptAxisValue {
  return { action: "full_accept", editedAnswer: candidateAnswer ?? "", reasonCode: "" };
}

// No edited-answer check here (DEVIATIONS.md #101) — `partial_accept` is
// always valid without one, in both workflows.
export function isAcceptAxisValueValid(value: AcceptAxisValue, requireReason = true): boolean {
  if (requireReason && ACCEPT_REASON_REQUIRED.includes(value.action) && !value.reasonCode.trim()) {
    return false;
  }
  return true;
}
