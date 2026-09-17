import { useEffect, useState } from "react";
import ReviewQueue from "../components/ReviewQueue";
import RubricForm from "../components/RubricForm";
import AnswerSegments from "../components/AnswerSegments";
import CitationList from "../components/CitationList";
import type { QueueResult, QueueResultDetail } from "../types";
import { api, ApiError } from "../api/client";

// Reviewer rank-mode workflow (ARCH §13): for each case a ranker reviews (an
// open `eval.result`), they complete the 11-domain rubric AND pick an
// accept-axis option, TOGETHER, in one submission (ARCH §13.2 "Both axes
// together", DEVIATIONS.md #99) — `RubricForm` embeds `AcceptAxisControls`
// for exactly this reason. Standalone escalation resolution (a different
// workflow, on a different backend entity, `hitl.escalation`) lives on its
// own page (`EscalationsPage.tsx`) — moved out of here so it no longer
// appears stacked under a rank-mode task with a confusingly identical
// "Accept axis" heading (DEVIATIONS.md #120).
export default function ReviewPage() {
  return (
    <section>
      <h2 style={{ fontSize: 16 }}>Review queue</h2>

      <RankModeSection />
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
          {detail.question && (
            <p style={{ fontStyle: "italic", color: "#444" }}>
              <strong>Generated query:</strong> {detail.question}
            </p>
          )}
          {detail.segments ? (
            <AnswerSegments segments={detail.segments} citations={detail.citations} />
          ) : detail.answer ? (
            // A result written before segments were persisted (DEVIATIONS.md
            // #120) — no per-segment citation_ids to link inline, only the
            // flat answer text plus the same citation list, unlinked.
            <>
              <p style={{ whiteSpace: "pre-wrap" }}>{detail.answer}</p>
              <CitationList citations={detail.citations} />
            </>
          ) : (
            <p style={{ color: "#999" }}>No answer text recorded for this result.</p>
          )}

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
