import type { EscalationSummary } from "../types";

// HITL escalation discovery list (accept axis; DEVIATIONS.md #97). Opening a
// row (GET /hitl/escalations/{id}) transitions it open -> in_review server-side
// (ARCH §12.2 "reviewer pulls") — this component just lists/selects.
export default function EscalationQueue({
  items,
  selectedId,
  onSelect,
}: {
  items: EscalationSummary[];
  selectedId: string | null;
  onSelect: (escalationId: string) => void;
}) {
  if (!items.length) {
    return <p style={{ color: "#999", fontSize: 13 }}>No open escalations.</p>;
  }
  return (
    <table style={{ width: "100%", fontSize: 13, borderCollapse: "collapse" }}>
      <thead>
        <tr>
          <th style={{ textAlign: "left" }}>Escalation</th>
          <th style={{ textAlign: "left" }}>Trigger</th>
          <th style={{ textAlign: "left" }}>State</th>
          <th style={{ textAlign: "left" }}>Opened</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {items.map((e) => (
          <tr
            key={e.id}
            style={{
              borderTop: "1px solid #eee",
              background: e.id === selectedId ? "#eef6ff" : "transparent",
            }}
          >
            <td>
              <code>{e.id.slice(0, 8)}</code>
            </td>
            <td>{e.trigger_code}</td>
            <td>{e.state}</td>
            <td>{new Date(e.created_at).toLocaleString()}</td>
            <td>
              <button type="button" onClick={() => onSelect(e.id)}>
                {e.id === selectedId ? "Selected" : "Open"}
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
