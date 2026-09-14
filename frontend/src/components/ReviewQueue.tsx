import type { QueueResult } from "../types";

// Open review queue (PRD-042, PRD-047; rank mode). Lists results with < 3
// distinct raters, visible to any reviewer. Shows provenance (auto_generated /
// clinician_submitted) and, for auto-generated items, the expected-outcome
// label. Hard/adversarial cases appear in this same list.
export default function ReviewQueue({
  items,
  selectedId,
  onSelect,
}: {
  items: QueueResult[];
  selectedId: string | null;
  onSelect: (resultId: string) => void;
}) {
  if (!items.length) {
    return <p style={{ color: "#999", fontSize: 13 }}>No results currently open for rating.</p>;
  }
  return (
    <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
      <thead>
        <tr>
          <th style={{ textAlign: "left" }}>Result</th>
          <th style={{ textAlign: "left" }}>Provenance</th>
          <th style={{ textAlign: "left" }}>Expected outcome</th>
          <th style={{ textAlign: "left" }}>Observed outcome</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {items.map((r) => (
          <tr
            key={r.result_id}
            style={{
              borderTop: "1px solid #eee",
              background: r.result_id === selectedId ? "#eef6ff" : "transparent",
            }}
          >
            <td>
              <code>{r.result_id.slice(0, 8)}</code>
            </td>
            <td>{r.provenance}</td>
            <td>{r.expected_outcome ?? "—"}</td>
            <td>{r.observed_outcome ?? "—"}</td>
            <td>
              <button type="button" onClick={() => onSelect(r.result_id)}>
                {r.result_id === selectedId ? "Selected" : "Rate this"}
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
