import { useState } from "react";

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
      style={{ display: "grid", gap: 8 }}
    >
      <label>
        Question (guideline lookup — e.g. &ldquo;what does the guideline recommend for a
        patient presenting with X, Y, Z?&rdquo;)
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={3}
          style={{ width: "100%" }}
        />
      </label>
      <label>
        Patient ID (optional; one patient per session)
        <input value={patientId} onChange={(e) => setPatientId(e.target.value)} />
      </label>
      <label>
        Local constraint (optional; only surfaces an alternative already in the
        retrieved guideline text)
        <input value={constraint} onChange={(e) => setConstraint(e.target.value)} />
      </label>
      <button type="submit" disabled={!question.trim() || busy}>
        {busy ? "Submitting…" : "Submit"}
      </button>
    </form>
  );
}
