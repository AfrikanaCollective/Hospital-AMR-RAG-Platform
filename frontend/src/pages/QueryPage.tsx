import { useState } from "react";
import QueryPanel from "../components/QueryPanel";
import AnswerView from "../components/AnswerView";
import type { QueryResponse } from "../types";
import { api, ApiError } from "../api/client";

// Query interface (PRD-107, SCOPE-1.1/2.1/2.2). Turns within one conversation
// share a conversation_id (PRD-NG-011: at most one patient per conversation)
// so a follow-up question stays in context; starting a new conversation means
// reloading (kept deliberately simple for MVP — no "new conversation" button
// managing multiple concurrent threads).
export default function QueryPage() {
  const [resp, setResp] = useState<QueryResponse | null>(null);
  const [conversationId, setConversationId] = useState<string | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  return (
    <section>
      <h2 style={{ fontSize: 16 }}>Ask a guideline question</h2>
      <QueryPanel
        busy={busy}
        onSubmit={async (q) => {
          setError(null);
          setBusy(true);
          try {
            const result = await api.submitQuery({ ...q, conversation_id: conversationId });
            setResp(result);
            setConversationId(result.conversation_id);
          } catch (e) {
            setError(e instanceof ApiError ? e.message : String(e));
          } finally {
            setBusy(false);
          }
        }}
      />
      {error && <p style={{ color: "#c0392b" }}>{error}</p>}
      {resp && (
        <div style={{ marginTop: 16 }}>
          <AnswerView resp={resp} />
        </div>
      )}
      {conversationId && (
        <p style={{ fontSize: 12, color: "#999", marginTop: 24 }}>
          Conversation {conversationId} — follow-up questions stay in this conversation.{" "}
          <button
            type="button"
            onClick={() => {
              setConversationId(undefined);
              setResp(null);
            }}
          >
            Start a new conversation
          </button>
        </p>
      )}
    </section>
  );
}
