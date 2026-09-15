import type { AnswerSegment, Citation } from "./types";

// Citation display renumbering (PRD-107, PRD-011).
//
// The backend labels a citation by its RETRIEVAL RANK position (`c1` is the
// top-ranked retrieved chunk, `c2` the second, ...), not by order of use in
// the answer — a claim segment can cite `c1`, `c2`, and `c7` while `c3`-`c6`
// never appear at all, because the model simply didn't use those retrieved-
// but-unused chunks. That's correct, real data (retrieval-rank labels are
// useful for tracing an answer back to retrieval logs), but reads as broken
// to anyone looking at the rendered answer — footnotes [c1] [c2] [c7] look
// like two citations went missing, not like three were genuinely used out of
// up to eight retrieved.
//
// `renumberForDisplay` remaps citation labels to sequential order of first
// appearance in the released segments (1, 2, 3, ...) for rendering only —
// it never touches the backend response, the audit trail, or anything the
// API returns; call it once, right before rendering, and use its output in
// place of `resp.segments`/`resp.citations`.
export function renumberForDisplay(
  segments: AnswerSegment[],
  citations: Citation[],
): { segments: AnswerSegment[]; citations: Citation[] } {
  const displayId = new Map<string, string>();
  for (const seg of segments) {
    for (const cid of seg.citation_ids) {
      if (!displayId.has(cid)) displayId.set(cid, `c${displayId.size + 1}`);
    }
  }

  const remappedSegments = segments.map((seg) => ({
    ...seg,
    citation_ids: seg.citation_ids.map((cid) => displayId.get(cid) ?? cid),
  }));
  const remappedCitations = citations
    .filter((c) => displayId.has(c.citation_id))
    .map((c) => ({ ...c, citation_id: displayId.get(c.citation_id) as string }))
    .sort((a, b) => a.citation_id.localeCompare(b.citation_id, undefined, { numeric: true }));

  return { segments: remappedSegments, citations: remappedCitations };
}
