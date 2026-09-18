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
      <div className="text-[16px] leading-relaxed text-ink">
        {renumbered.segments.map((seg, i) => (
          <span key={i} className={seg.type === "framing" ? "" : "bg-accent/10"}>
            {seg.text}
            {seg.citation_ids.map((cid) => (
              <sup key={cid}>
                <a className="text-accent-strong hover:underline" href={`#cite-${cid}`}>
                  [{cid}]
                </a>
              </sup>
            ))}
            {seg.grounding_note ? (
              <em className="text-[#8a5000]"> ({seg.grounding_note})</em>
            ) : null}{" "}
          </span>
        ))}
      </div>
      <h4 className="mt-3 mb-1 text-[14px] font-semibold text-ink">Citations</h4>
      <CitationList citations={renumbered.citations} />
    </div>
  );
}
