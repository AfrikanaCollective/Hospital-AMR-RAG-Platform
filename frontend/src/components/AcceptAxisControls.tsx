import type { AcceptAxisValue } from "../types";
import { ACCEPT_ACTIONS, ACCEPT_REASON_REQUIRED } from "../acceptAxis";

// Accept axis (PRD-032, ARCH §13.2): full accept / partial accept / reject /
// out of scope. A pure controlled fieldset — no form/submit of its own — so
// it can be composed into either of its two real call sites: RubricForm
// (combined rank+accept submission — a ranker's task is exactly the rubric
// plus this pick, no reason text, `requireReason={false}`, DEVIATIONS #100)
// and ReviewPage's EscalationDecisionForm (standalone escalation
// resolution, where a reason is still required — the default). The edited-
// answer textarea is always optional in both, never required for
// `partial_accept` (DEVIATIONS #101). See ../acceptAxis.ts for the shared
// constants/helpers and the full rationale.
export default function AcceptAxisControls({
  value,
  onChange,
  requireReason = true,
}: {
  value: AcceptAxisValue;
  onChange: (next: AcceptAxisValue) => void;
  requireReason?: boolean;
}) {
  const needsReason = requireReason && ACCEPT_REASON_REQUIRED.includes(value.action);

  return (
    <div style={{ display: "grid", gap: 6 }}>
      <div>
        {ACCEPT_ACTIONS.map((a) => (
          <label key={a} style={{ marginRight: 12 }}>
            <input
              type="radio"
              name="accept"
              checked={value.action === a}
              onChange={() => onChange({ ...value, action: a })}
            />{" "}
            {a.replace(/_/g, " ")}
          </label>
        ))}
      </div>
      {value.action === "partial_accept" && (
        <textarea
          placeholder="Edited answer (optional — keep supported content, remove/rewrite the rest)"
          value={value.editedAnswer}
          onChange={(e) => onChange({ ...value, editedAnswer: e.target.value })}
          rows={6}
        />
      )}
      {needsReason && (
        <input
          placeholder="Reason code (required)"
          value={value.reasonCode}
          onChange={(e) => onChange({ ...value, reasonCode: e.target.value })}
        />
      )}
    </div>
  );
}
