import { useState } from "react";
import QueryPanel from "../components/QueryPanel";
import AnswerView from "../components/AnswerView";
import type { QueryResponse } from "../types";
import { api } from "../api/client";

export default function QueryPage() {
  const [resp, setResp] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  return (
    <section>
      <h2 style={{ fontSize: 16 }}>Ask a guideline question</h2>
      <QueryPanel
        onSubmit={async (q) => {
          setError(null);
          try {
            setResp(await api.submitQuery(q));
          } catch (e) {
            setError(String(e));
          }
        }}
      />
      {error && <p style={{ color: "#c0392b" }}>{error} (backend endpoint is a Phase 3 stub)</p>}
      {resp && (
        <div style={{ marginTop: 16 }}>
          <AnswerView resp={resp} />
        </div>
      )}
    </section>
  );
}
