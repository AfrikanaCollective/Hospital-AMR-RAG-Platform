// Open review queue (PRD-042, PRD-047). Lists results with < 3 distinct raters,
// visible to any clinician. Shows provenance (auto_generated / clinician_submitted)
// and, for auto-generated items, the expected-outcome label. Hard/adversarial
// cases appear in this same list. Phase 5 wires data + selection.
export default function ReviewQueue() {
  return (
    <div>
      <p style={{ fontSize: 13, color: "#666" }}>
        Results awaiting their 3rd distinct clinician rater. Provenance and (for
        auto-generated items) the expected-outcome label are shown per row.
      </p>
      <table style={{ width: "100%", fontSize: 13 }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left" }}>Result</th>
            <th>Provenance</th>
            <th>Expected outcome</th>
            <th>Raters</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td colSpan={4} style={{ color: "#999" }}>
              (Phase 5 — no data yet)
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
