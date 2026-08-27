import type { Citation } from "../types";

// Citation display (PRD-107, PRD-011). Shows document + version + section/page +
// the verbatim quote. A "superseded"/"withdrawn" badge is shown for old versions.
export default function CitationList({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;
  return (
    <ol style={{ fontSize: 13 }}>
      {citations.map((c) => (
        <li key={c.citation_id} id={`cite-${c.citation_id}`} style={{ marginBottom: 8 }}>
          <strong>{c.document_title}</strong> (v{c.version_label}
          {c.version_status !== "active" ? `, ${c.version_status}` : ""})
          {c.section_number ? `, §${c.section_number}` : ""}, p.{c.page_start}
          {c.page_end !== c.page_start ? `–${c.page_end}` : ""}
          <blockquote style={{ margin: "4px 0 0", color: "#333", borderLeft: "3px solid #ccc", paddingLeft: 8 }}>
            {c.quote}
          </blockquote>
          <small style={{ color: "#888" }}>
            chunk {c.chunk_id} · chars {c.char_start}–{c.char_end}
          </small>
        </li>
      ))}
    </ol>
  );
}
