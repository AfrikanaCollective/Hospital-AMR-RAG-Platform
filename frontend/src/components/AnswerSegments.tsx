import type { AnswerSegment, Citation } from "../types";
import CitationList from "./CitationList";
import { renumberForDisplay } from "../citations";

// Shared segment + inline-citation rendering (PRD-107, PRD-011), used by
// both a live /query answer (AnswerView.tsx) and a review-queue item
// (ReviewPage.tsx) so the two never drift into two different citation
// presentations for the same underlying `segments`/`citations` shape
// (DEVIATIONS.md #120).
export default function AnswerSegments({
  segments,
  citations,
}: {
  segments: AnswerSegment[];
  citations: Citation[];
}) {
  // Backend citation_ids are retrieval-rank labels (c1 = top-ranked chunk),
  // not order-of-use — renumbered here, for display only, to sequential
  // order of first appearance (see ../citations.ts).
  const renumbered = renumberForDisplay(segments, citations);

  return (
    <div>
      <div style={{ lineHeight: 1.5 }}>
        {renumbered.segments.map((seg, i) => (
          <span key={i} style={{ background: seg.type === "framing" ? "transparent" : "#eef6ff" }}>
            {seg.text}
            {seg.citation_ids.map((cid) => (
              <sup key={cid}>
                <a href={`#cite-${cid}`}>[{cid}]</a>
              </sup>
            ))}
            {seg.grounding_note ? <em style={{ color: "#a15c00" }}> ({seg.grounding_note})</em> : null}{" "}
          </span>
        ))}
      </div>
      <h4>Citations</h4>
      <CitationList citations={renumbered.citations} />
    </div>
  );
}
