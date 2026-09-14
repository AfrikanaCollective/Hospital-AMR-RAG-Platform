import { useEffect, useState } from "react";
import ReviewQueue from "../components/ReviewQueue";
import EscalationQueue from "../components/EscalationQueue";
import RubricForm from "../components/RubricForm";
import AcceptAxisControls from "../components/AcceptAxisControls";
import { defaultAcceptAxisValue, isAcceptAxisValueValid } from "../acceptAxis";
import CitationList from "../components/CitationList";
import type {
  AcceptAxisValue,
  Citation,
  EscalationDetail,
  EscalationSummary,
  QueueResult,
  QueueResultDetail,
} from "../types";
import { api, ApiError } from "../api/client";

// Reviewer workflow (ARCH §13) has two sections, for two different real
// workflows:
//  - Rank mode: for each case a ranker reviews (an open `eval.result`), they
//    complete the 11-domain rubric AND pick an accept-axis option, TOGETHER,
//    in one submission (ARCH §13.2 "Both axes together", DEVIATIONS.md #99)
//    — `RubricForm` embeds `AcceptAxisControls` for exactly this reason.
//  - Accept axis (standalone): resolving a `hitl.escalation` directly (via
//    escalation discovery, DEVIATIONS.md #97) — a different workflow (a
//    single urgent, held-answer resolution, not a multi-rater evaluation
//    pass), reusing the same `AcceptAxisControls` fieldset on its own.
// The two sections operate on different backend entities (`eval.result` vs
// `hitl.escalation`) with no cross-reference between them yet, so a result
// being rated here and an escalation being resolved below are never
// (necessarily) the same item.
export default function ReviewPage() {
  return (
    <section>
      <h2 style={{ fontSize: 16 }}>Review queue</h2>

      <RankModeSection />

      <hr style={{ margin: "32px 0" }} />

      <AcceptAxisSection />
    </section>
  );
}

function RankModeSection() {
  const [items, setItems] = useState<QueueResult[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<QueueResultDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const refreshQueue = () => {
    api
      .getReviewQueue()
      .then(setItems)
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  };

  useEffect(refreshQueue, []);

  useEffect(() => {
    if (!selectedId) return;
    api
      .getReviewQueueItem(selectedId)
      .then((d) => {
        setDetail(d);
        setError(null);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [selectedId]);

  const select = (resultId: string | null) => {
    setSelectedId(resultId);
    if (!resultId) setDetail(null);
  };

  return (
    <div>
      <h3 style={{ fontSize: 15 }}>Rank mode</h3>
      <p style={{ fontSize: 13, color: "#666" }}>
        For each case: the 11-domain rubric AND an accept-axis decision, submitted
        together. Results stay in this queue until 3 distinct reviewers have rated
        them, then are archived with a per-domain IRR score.
      </p>
      <ReviewQueue items={items} selectedId={selectedId} onSelect={select} />

      {error && <p style={{ color: "#c0392b", fontSize: 13 }}>{error}</p>}
      {notice && <p style={{ color: "#1a7a1a", fontSize: 13 }}>{notice}</p>}

      {detail && (
        <div style={{ marginTop: 16, border: "1px solid #ddd", borderRadius: 6, padding: 12 }}>
          <h4 style={{ fontSize: 14, marginTop: 0 }}>Result {detail.result_id.slice(0, 8)}</h4>
          {detail.answer ? (
            <p style={{ whiteSpace: "pre-wrap" }}>{detail.answer}</p>
          ) : (
            <p style={{ color: "#999" }}>No answer text recorded for this result.</p>
          )}
          <CitationList citations={(detail.citations as Citation[]) ?? []} />

          <RubricForm
            key={detail.result_id}
            candidateAnswer={detail.answer}
            busy={busy}
            onSubmit={async (submission) => {
              setBusy(true);
              setError(null);
              setNotice(null);
              try {
                await api.submitRating(detail.result_id, submission);
                setNotice(`Rating submitted (accept axis: ${submission.accept.action}).`);
                select(null);
                refreshQueue();
              } catch (e) {
                setError(e instanceof ApiError ? e.message : String(e));
              } finally {
                setBusy(false);
              }
            }}
          />
        </div>
      )}
    </div>
  );
}

function AcceptAxisSection() {
  const [items, setItems] = useState<EscalationSummary[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EscalationDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  const refreshQueue = () => {
    api
      .listEscalations()
      .then(setItems)
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  };

  useEffect(refreshQueue, []);

  useEffect(() => {
    if (!selectedId) return;
    api
      .getEscalation(selectedId)
      .then((d) => {
        setDetail(d);
        setError(null);
        // Opening the detail view pulled it into in_review server-side
        // (ARCH §12.2) — reflect that in the list without a full refetch.
        setItems((prev) => prev.map((e) => (e.id === d.id ? { ...e, state: d.state } : e)));
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [selectedId]);

  const select = (escalationId: string | null) => {
    setSelectedId(escalationId);
    if (!escalationId) setDetail(null);
  };

  return (
    <div>
      <h3 style={{ fontSize: 15 }}>Accept axis</h3>
      <p style={{ fontSize: 13, color: "#666" }}>
        Open escalations awaiting a full accept / partial accept / reject / out-of-scope
        decision (a single held-answer resolution — not a multi-rater rank-mode
        pass). Opening one marks it in review.
      </p>
      <EscalationQueue items={items} selectedId={selectedId} onSelect={select} />

      {error && <p style={{ color: "#c0392b", fontSize: 13 }}>{error}</p>}
      {notice && <p style={{ color: "#1a7a1a", fontSize: 13 }}>{notice}</p>}

      {detail && (
        <div style={{ marginTop: 16, border: "1px solid #ddd", borderRadius: 6, padding: 12 }}>
          <h4 style={{ fontSize: 14, marginTop: 0 }}>
            Escalation {detail.id.slice(0, 8)} — {detail.trigger_code}
          </h4>
          {detail.candidate_answer ? (
            <p style={{ whiteSpace: "pre-wrap" }}>{detail.candidate_answer}</p>
          ) : (
            <p style={{ color: "#999" }}>No candidate answer was held for this escalation.</p>
          )}
          {Object.keys(detail.trigger_detail).length > 0 && (
            <details style={{ fontSize: 12, color: "#666" }}>
              <summary>Trigger detail</summary>
              <pre style={{ whiteSpace: "pre-wrap" }}>
                {JSON.stringify(detail.trigger_detail, null, 2)}
              </pre>
            </details>
          )}

          <EscalationDecisionForm
            key={detail.id}
            candidateAnswer={detail.candidate_answer}
            busy={busy}
            onSubmit={async (accept) => {
              setBusy(true);
              setError(null);
              setNotice(null);
              try {
                await api.submitHitlDecision(detail.id, {
                  action: accept.action,
                  edited_answer:
                    accept.action === "partial_accept"
                      ? accept.editedAnswer || undefined
                      : undefined,
                  reason_code: accept.reasonCode || undefined,
                });
                setNotice(`Decision recorded: ${accept.action}.`);
                select(null);
                refreshQueue();
              } catch (e) {
                setError(e instanceof ApiError ? e.message : String(e));
              } finally {
                setBusy(false);
              }
            }}
          />
        </div>
      )}
    </div>
  );
}

// Owns its own accept-axis form state, reset by the parent mounting this
// with `key={detail.id}` per newly selected escalation (same pattern as
// RubricForm) rather than resetting state via an effect.
function EscalationDecisionForm({
  candidateAnswer,
  busy,
  onSubmit,
}: {
  candidateAnswer?: string | null;
  busy?: boolean;
  onSubmit: (accept: AcceptAxisValue) => void;
}) {
  const [accept, setAccept] = useState<AcceptAxisValue>(defaultAcceptAxisValue(candidateAnswer));

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(accept);
      }}
      style={{ display: "grid", gap: 6 }}
    >
      <AcceptAxisControls value={accept} onChange={setAccept} />
      <button type="submit" disabled={!isAcceptAxisValueValid(accept) || busy}>
        {busy ? "Submitting…" : "Submit decision"}
      </button>
    </form>
  );
}
