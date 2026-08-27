import { useEffect, useState } from "react";
import type { RubricDomain } from "../types";
import { api } from "../api/client";

// Rank mode (PRD-031, PRD-040): 11 domains, 5-point Likert each. Structured
// data only. Independent of the accept axis (AcceptAxisControls).
export default function RubricForm({
  onSubmit,
}: {
  onSubmit: (scores: Record<string, number>, comment: string) => void;
}) {
  const [domains, setDomains] = useState<RubricDomain[]>([]);
  const [scores, setScores] = useState<Record<string, number>>({});
  const [comment, setComment] = useState("");

  useEffect(() => {
    api.getRubricDomains().then(setDomains).catch(() => setDomains([]));
  }, []);

  const complete = domains.length > 0 && domains.every((d) => scores[d.code]);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(scores, comment);
      }}
    >
      <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left" }}>Domain</th>
            <th>1</th><th>2</th><th>3</th><th>4</th><th>5</th>
          </tr>
        </thead>
        <tbody>
          {domains.map((d) => (
            <tr key={d.code} style={{ borderTop: "1px solid #eee" }}>
              <td title={d.definition}>
                {d.ordinal}. {d.name}
                {d.required ? " *" : ""}
              </td>
              {[1, 2, 3, 4, 5].map((v) => (
                <td key={v} style={{ textAlign: "center" }}>
                  <input
                    type="radio"
                    name={d.code}
                    checked={scores[d.code] === v}
                    onChange={() => setScores((s) => ({ ...s, [d.code]: v }))}
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <label style={{ display: "block", marginTop: 8 }}>
        Comment (optional adjunct — not a substitute for scores)
        <textarea value={comment} onChange={(e) => setComment(e.target.value)} rows={2} style={{ width: "100%" }} />
      </label>
      <button type="submit" disabled={!complete}>
        Submit rating
      </button>
    </form>
  );
}
