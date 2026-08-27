// Non-removable disclaimer (ARCH-037, PRD-087). Rendered persistently on any
// view that can show an answer. The text also arrives on every QueryResponse.
export default function DisclaimerBanner() {
  return (
    <div
      role="note"
      style={{
        border: "1px solid #c9a227",
        background: "#fdf6e3",
        color: "#5b4a00",
        padding: "8px 12px",
        borderRadius: 6,
        margin: "12px 0",
        fontSize: 13,
      }}
    >
      Reported guideline content for clinician reference only. This is not medical
      advice and does not constitute an independent clinical recommendation.
      Clinical judgement remains with the treating clinician.
    </div>
  );
}
