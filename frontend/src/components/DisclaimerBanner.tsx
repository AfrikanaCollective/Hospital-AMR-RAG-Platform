// Non-removable disclaimer (ARCH-037, PRD-087). Rendered persistently on any
// view that can show an answer. The text also arrives on every QueryResponse.
// Colors verified at ~8:1 (AAA) — DEVIATIONS #133 — kept exactly as-is.
export default function DisclaimerBanner() {
  return (
    <div
      role="note"
      className="my-3 rounded-md border border-disclaimer-border bg-disclaimer-bg p-2.5 text-[13px] text-disclaimer-text"
    >
      Reported guideline content for clinician reference only. This is not medical
      advice and does not constitute an independent clinical recommendation.
      Clinical judgement remains with the treating clinician.
    </div>
  );
}
