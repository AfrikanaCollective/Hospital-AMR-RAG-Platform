import { useEffect, useState } from "react";
import EscalationQueue from "../components/EscalationQueue";
import AcceptAxisControls from "../components/AcceptAxisControls";
import { defaultAcceptAxisValue, isAcceptAxisValueValid } from "../acceptAxis";
import type { AcceptAxisValue, EscalationDetail, EscalationSummary } from "../types";
import { api, ApiError } from "../api/client";
import Button from "../components/ui/Button";

// Standalone accept-axis workflow (ARCH §13.2, DEVIATIONS.md #97): resolving
// a `hitl.escalation` directly — a single urgent, held-answer resolution,
// not a multi-rater rank-mode evaluation pass (that's ReviewPage.tsx, a
// different backend entity, `eval.result`, with its own accept-axis picker
// built into the rubric form). Split onto its own page (DEVIATIONS.md #120)
// so it no longer renders stacked directly under a rank-mode review task
// with a confusingly identical "Accept axis" heading.
export default function EscalationsPage() {
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
    <section>
      <h2 className="text-base font-semibold text-ink">Escalations</h2>
      <p className="text-[13px] text-ink-muted">
        Open escalations awaiting a full accept / partial accept / reject / out-of-scope
        decision (a single held-answer resolution — not a multi-rater rank-mode
        pass). Opening one marks it in review.
      </p>
      <EscalationQueue items={items} selectedId={selectedId} onSelect={select} />

      {error && <p className="text-[13px] text-danger">{error}</p>}
      {notice && <p className="text-[13px] text-accent-strong">{notice}</p>}

      {detail && (
        <div className="mt-4 rounded-md border border-border p-3">
          <h4 className="mt-0 text-sm font-semibold text-ink">
            Escalation {detail.id.slice(0, 8)} — {detail.trigger_code}
          </h4>
          {detail.candidate_answer ? (
            <p className="whitespace-pre-wrap text-ink">{detail.candidate_answer}</p>
          ) : (
            <p className="text-ink-muted">No candidate answer was held for this escalation.</p>
          )}
          {Object.keys(detail.trigger_detail).length > 0 && (
            <details className="text-xs text-ink-muted">
              <summary>Trigger detail</summary>
              <pre className="whitespace-pre-wrap">
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
    </section>
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
      className="mt-3 grid gap-3"
    >
      <AcceptAxisControls value={accept} onChange={setAccept} />
      <Button
        type="submit"
        variant="primary"
        disabled={!isAcceptAxisValueValid(accept) || busy}
        className="justify-self-start"
      >
        {busy ? "Submitting…" : "Submit decision"}
      </Button>
    </form>
  );
}
