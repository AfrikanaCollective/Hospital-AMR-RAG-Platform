import { useState } from "react";
import type { AcceptAction } from "../types";

// Accept axis (PRD-032): full accept / partial accept / reject. Independent of
// rank mode. Effects on state are defined server-side (ARCH §13.2):
//  - full_accept : answer released as-is; provisional context -> reviewer_accepted
//  - partial_accept: reviewer-edited version canonical; only retained context kept
//  - reject      : answer withheld/retracted; ALL provisional context rolled back
export default function AcceptAxisControls({
  onSubmit,
}: {
  onSubmit: (a: {
    action: AcceptAction;
    edited_answer?: string;
    reason_code?: string;
  }) => void;
}) {
  const [action, setAction] = useState<AcceptAction>("full_accept");
  const [edited, setEdited] = useState("");
  const [reason, setReason] = useState("");

  const needsReason = action === "reject" || action === "partial_accept";

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          action,
          edited_answer: action === "partial_accept" ? edited : undefined,
          reason_code: needsReason ? reason : undefined,
        });
      }}
      style={{ display: "grid", gap: 6 }}
    >
      <div>
        {(["full_accept", "partial_accept", "reject"] as AcceptAction[]).map((a) => (
          <label key={a} style={{ marginRight: 12 }}>
            <input type="radio" name="accept" checked={action === a} onChange={() => setAction(a)} />{" "}
            {a.replace("_", " ")}
          </label>
        ))}
      </div>
      {action === "partial_accept" && (
        <textarea
          placeholder="Edited answer (keep supported segments, remove/rewrite the rest)"
          value={edited}
          onChange={(e) => setEdited(e.target.value)}
          rows={4}
        />
      )}
      {needsReason && (
        <input
          placeholder="Reason code (required)"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      )}
      <button type="submit" disabled={needsReason && !reason.trim()}>
        Submit decision
      </button>
    </form>
  );
}
