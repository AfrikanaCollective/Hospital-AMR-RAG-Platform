import * as RadioGroup from "@radix-ui/react-radio-group";
import type { AcceptAction, AcceptAxisValue } from "../types";
import { ACCEPT_ACTIONS, ACCEPT_REASON_REQUIRED } from "../acceptAxis";

const CARD_COPY: Record<AcceptAction, { label: string; description: string }> = {
  full_accept: {
    label: "Full accept",
    description: "Fully supported — release the answer as-is.",
  },
  partial_accept: {
    label: "Partial accept",
    description: "Keep the supported content; rewrite or remove the rest.",
  },
  reject: {
    label: "Reject",
    description: "Withhold this answer entirely.",
  },
  out_of_scope: {
    label: "Out of scope",
    description: "This request should never have reached synthesis.",
  },
};

const DESTRUCTIVE: AcceptAction[] = ["reject", "out_of_scope"];

// Accept axis (PRD-032, ARCH §13.2): full accept / partial accept / reject /
// out of scope. A pure controlled fieldset — no form/submit of its own — so
// it can be composed into either of its two real call sites: RubricForm
// (combined rank+accept submission — a ranker's task is exactly the rubric
// plus this pick, no reason text, `requireReason={false}`, DEVIATIONS #100)
// and ReviewPage's EscalationDecisionForm (standalone escalation
// resolution, where a reason is still required — the default). The edited-
// answer textarea is always optional in both, never required for
// `partial_accept` (DEVIATIONS #101).
//
// Rendered as large tappable cards, not a dropdown or bare radio row
// (DEVIATIONS #133 — this is a single higher-stakes decision, not one of
// eleven repeated ratings). `reject`/`out_of_scope` are the only cards that
// use the danger color, per the audit's "red reserved for destructive
// actions only" direction; selection is never color-only — each card also
// shows a checkmark + "Selected" text once picked.
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
    <div className="grid gap-4">
      <RadioGroup.Root
        value={value.action}
        onValueChange={(a) => onChange({ ...value, action: a as AcceptAction })}
        className="grid grid-cols-1 gap-3 sm:grid-cols-2"
      >
        {ACCEPT_ACTIONS.map((a) => {
          const selected = value.action === a;
          const destructive = DESTRUCTIVE.includes(a);
          return (
            <RadioGroup.Item
              key={a}
              value={a}
              className={`group flex flex-col items-start gap-1 rounded-xl border-2 p-4 text-left transition-colors
                ${
                  selected
                    ? destructive
                      ? "border-danger bg-danger/5"
                      : "border-accent-strong bg-accent-strong/5"
                    : "border-border bg-surface hover:bg-surface-alt"
                }`}
            >
              <span className="flex w-full items-center justify-between">
                <span className="text-[15px] font-semibold text-ink">{CARD_COPY[a].label}</span>
                <RadioGroup.Indicator asChild>
                  <span
                    className={`text-xs font-semibold ${destructive ? "text-danger" : "text-accent-strong"}`}
                  >
                    ✓ Selected
                  </span>
                </RadioGroup.Indicator>
              </span>
              <span className="text-[13px] leading-snug text-ink-muted">
                {CARD_COPY[a].description}
              </span>
            </RadioGroup.Item>
          );
        })}
      </RadioGroup.Root>

      {value.action === "partial_accept" && (
        <label className="grid gap-1 text-[13px] text-ink-muted">
          Edited answer (optional — keep supported content, remove/rewrite the rest)
          <textarea
            value={value.editedAnswer}
            onChange={(e) => onChange({ ...value, editedAnswer: e.target.value })}
            rows={6}
            className="w-full rounded-lg border border-border bg-surface p-2 text-[15px] leading-relaxed text-ink"
          />
        </label>
      )}
      {needsReason && (
        <label className="grid gap-1 text-[13px] text-ink-muted">
          Reason code (required)
          <input
            value={value.reasonCode}
            onChange={(e) => onChange({ ...value, reasonCode: e.target.value })}
            className="w-full rounded-lg border border-border bg-surface p-2 text-[15px] text-ink"
          />
        </label>
      )}
    </div>
  );
}
