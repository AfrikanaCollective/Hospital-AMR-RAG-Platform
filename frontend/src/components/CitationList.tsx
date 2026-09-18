import type { Citation } from "../types";

// Citation display (PRD-107, PRD-011). Shows document + version + section/page +
// the verbatim quote. A "superseded"/"withdrawn" badge is shown for old versions.
export default function CitationList({ citations }: { citations: Citation[] }) {
  if (!citations.length) return null;
  return (
    <ol className="grid gap-2 text-[13px] text-ink">
      {citations.map((c) => (
        <li key={c.citation_id} id={`cite-${c.citation_id}`}>
          <strong>{c.document_title}</strong> (v{c.version_label}
          {c.version_status !== "active" ? `, ${c.version_status}` : ""})
          {c.section_number ? `, §${c.section_number}` : ""}, p.{c.page_start}
          {c.page_end !== c.page_start ? `–${c.page_end}` : ""}
          <blockquote className="mt-1 border-l-[3px] border-border pl-2 text-ink">
            {c.quote}
          </blockquote>
          <small className="text-ink-muted">
            chunk {c.chunk_id} · chars {c.char_start}–{c.char_end}
          </small>
        </li>
      ))}
    </ol>
  );
}
