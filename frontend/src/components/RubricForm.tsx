import { useEffect, useState } from "react";
import type { AcceptAxisValue, RatingSubmission, RubricDomain } from "../types";
import { api } from "../api/client";
import AcceptAxisControls from "./AcceptAxisControls";
import { defaultAcceptAxisValue, isAcceptAxisValueValid } from "../acceptAxis";

const ANCHOR_KEYS = ["anchor_1", "anchor_2", "anchor_3", "anchor_4", "anchor_5"] as const;

// Rank mode (PRD-031, PRD-040), combined with the accept axis in ONE
// submission (ARCH §13.2 "Both axes together"): for each case a ranker
// reviews, they do exactly two tasks — complete the 11-domain rubric AND
// pick an accept-axis option — together, not as two independent actions,
// and nothing more: no reason/justification text is asked for, and
// submitting never creates an escalation (DEVIATIONS #100, correcting #99's
// carried-over reason-code requirement). The parent mounts this with
// `key={resultId}` so React gives it fresh local state for each newly
// selected result, rather than resetting state via an effect.
export default function RubricForm({
  candidateAnswer,
  onSubmit,
  busy,
}: {
  candidateAnswer?: string | null;
  onSubmit: (submission: RatingSubmission) => void;
  busy?: boolean;
}) {
  const [domains, setDomains] = useState<RubricDomain[]>([]);
  const [scores, setScores] = useState<Record<string, number>>({});
  const [comment, setComment] = useState("");
  const [accept, setAccept] = useState<AcceptAxisValue>(defaultAcceptAxisValue(candidateAnswer));

  useEffect(() => {
    api.getRubricDomains().then(setDomains).catch(() => setDomains([]));
  }, []);

  const scoresComplete = domains.length > 0 && domains.every((d) => scores[d.code]);
  const complete = scoresComplete && isAcceptAxisValueValid(accept, false);

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({ scores, comment, accept });
      }}
    >
      <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left" }}>Domain</th>
            <th>1</th>
            <th>2</th>
            <th>3</th>
            <th>4</th>
            <th>5</th>
          </tr>
        </thead>
        <tbody>
          {domains.map((d) => (
            <tr key={d.code} style={{ borderTop: "1px solid #eee" }}>
              <td title={d.definition}>
                {d.ordinal}. {d.name}
                {d.required ? " *" : ""}
              </td>
              {[1, 2, 3, 4, 5].map((v, i) => (
                <td key={v} style={{ textAlign: "center" }} title={d[ANCHOR_KEYS[i]]}>
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
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          rows={2}
          style={{ width: "100%" }}
        />
      </label>

      <h5 style={{ marginBottom: 4 }}>Accept axis (required for every case)</h5>
      <AcceptAxisControls value={accept} onChange={setAccept} requireReason={false} />

      <button type="submit" disabled={!complete || busy} style={{ marginTop: 8 }}>
        {busy ? "Submitting…" : "Submit rating"}
      </button>
    </form>
  );
}
