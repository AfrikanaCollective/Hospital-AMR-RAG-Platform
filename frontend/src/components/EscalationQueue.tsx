import type { EscalationSummary } from "../types";
import Button from "./ui/Button";

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
    return <p className="text-[13px] text-ink-muted">No open escalations.</p>;
  }
  return (
    <>
      {/* Stacked card below `sm` — see the matching comment in
          ReviewQueue.tsx (DEVIATIONS #135). */}
      <div className="grid gap-2 sm:hidden">
        {items.map((e) => (
          <div
            key={e.id}
            className={`rounded-lg border p-3 ${e.id === selectedId ? "border-accent-strong bg-accent/10" : "border-border"}`}
          >
            <div className="flex items-center justify-between gap-2 text-xs text-ink-muted">
              <code>{e.id.slice(0, 8)}</code>
              <span>{e.state}</span>
            </div>
            <div className="mt-1 text-[13px] text-ink">
              <div>Trigger: {e.trigger_code}</div>
              <div>Opened: {new Date(e.created_at).toLocaleString()}</div>
            </div>
            <Button type="button" onClick={() => onSelect(e.id)} className="mt-2 w-full">
              {e.id === selectedId ? "Selected" : "Open"}
            </Button>
          </div>
        ))}
      </div>

      <table className="hidden w-full border-collapse text-[13px] text-ink sm:table">
        <thead>
          <tr>
            <th className="text-left">Escalation</th>
            <th className="text-left">Trigger</th>
            <th className="text-left">State</th>
            <th className="text-left">Opened</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {items.map((e) => (
            <tr
              key={e.id}
              className={`border-t border-border ${e.id === selectedId ? "bg-accent/10" : ""}`}
            >
              <td>
                <code>{e.id.slice(0, 8)}</code>
              </td>
              <td>{e.trigger_code}</td>
              <td>{e.state}</td>
              <td>{new Date(e.created_at).toLocaleString()}</td>
              <td className="py-1">
                <Button type="button" onClick={() => onSelect(e.id)}>
                  {e.id === selectedId ? "Selected" : "Open"}
                </Button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}
