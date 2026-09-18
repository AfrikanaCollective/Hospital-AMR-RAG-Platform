import { useState } from "react";
import Button from "./ui/Button";

// Query interface (PRD-107). Optional patient_id + optional local constraint
// (SCOPE-2.5).
export default function QueryPanel({
  onSubmit,
  busy,
}: {
  onSubmit: (q: { question: string; patient_id?: string; hospital_constraint?: string }) => void;
  busy?: boolean;
}) {
  const [question, setQuestion] = useState("");
  const [patientId, setPatientId] = useState("");
  const [constraint, setConstraint] = useState("");

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit({
          question,
          patient_id: patientId || undefined,
          hospital_constraint: constraint || undefined,
        });
      }}
      className="grid gap-3"
    >
      <label className="grid gap-1 text-[13px] text-ink-muted">
        Question (guideline lookup — e.g. &ldquo;what does the guideline recommend for a
        patient presenting with X, Y, Z?&rdquo;)
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={3}
          className="w-full rounded-lg border border-border bg-surface p-2 text-[15px] leading-relaxed text-ink"
        />
      </label>
      <label className="grid gap-1 text-[13px] text-ink-muted">
        Patient ID (optional; one patient per session)
        <input
          value={patientId}
          onChange={(e) => setPatientId(e.target.value)}
          className="w-full rounded-lg border border-border bg-surface p-2 text-[15px] text-ink"
        />
      </label>
      <label className="grid gap-1 text-[13px] text-ink-muted">
        Local constraint (optional; only surfaces an alternative already in the
        retrieved guideline text)
        <input
          value={constraint}
          onChange={(e) => setConstraint(e.target.value)}
          className="w-full rounded-lg border border-border bg-surface p-2 text-[15px] text-ink"
        />
      </label>
      <Button type="submit" variant="primary" disabled={!question.trim() || busy} className="justify-self-start">
        {busy ? "Submitting…" : "Submit"}
      </Button>
    </form>
  );
}
