import type { QueryResponse } from "../types";
import AnswerSegments from "./AnswerSegments";

// Renders a released answer (segments + citations) OR an escalation notice.
// Never renders an ungrounded answer (backend guarantees this — PRD-NFR-2).
export default function AnswerView({ resp }: { resp: QueryResponse }) {
  if (resp.escalation) {
    return (
      <div style={{ border: "1px solid #c0392b", borderRadius: 6, padding: 12 }}>
        <strong>Sent for clinician review</strong>
        <p style={{ margin: "6px 0" }}>{resp.escalation.message}</p>
        <small style={{ color: "#888" }}>
          trigger: {resp.escalation.trigger_code} · outcome: {resp.observed_outcome}
        </small>
      </div>
    );
  }

  if (resp.observed_outcome === "no_guideline") {
    return (
      <div style={{ border: "1px solid #999", borderRadius: 6, padding: 12 }}>
        No matching guideline was retrieved for this question. The system does not
        answer from general knowledge.
      </div>
    );
  }

  return <AnswerSegments segments={resp.segments} citations={resp.citations} />;
}
