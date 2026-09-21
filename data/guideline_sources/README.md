# Guideline sources — archival full publications (not ingested)

This directory holds the **full, original publication** a partial-page-range
extract in `data/excerpt_guidelines/` was pulled from (ARCH-038 / DEVIATIONS.md
#166/#167) — e.g. the complete 100-page guideline that only 4 pages were
extracted out of for `data/excerpt_guidelines/`.

**No ingestion code path *discovers* content here.**
`scripts/prepare_sample_guidelines.py` (and any future corpus-wide scan) only
ever walks `SAMPLE_GUIDELINES_DIR` (`data/excerpt_guidelines/` by default) —
a file placed only here is invisible to new ingestion by construction, not by
convention alone, so there is no way to accidentally double-ingest a
100-page original that was only meant as a reference copy. This is a
deliberate design choice over nesting an "archival" subfolder inside
`excerpt_guidelines/`, which would need scanner exclusion logic to get the
same guarantee.

This directory **is** bind-mounted (read-only) into the `api`/`worker`
containers, so a specific, already-known `Document.source_uri` that points
here — e.g. a document ingested in full, later superseded by a `source_pages`
excerpt of the same publication (DEVIATIONS.md #170/#173) — remains
resolvable if that exact `document_version` is ever deliberately reprocessed.
That is a narrow, `:ro` exception for one already-known row's own recorded
path, not a discovery path: nothing walks this directory looking for new
files to ingest.

**Why keep the full document at all**, if it's never ingested: so a reviewer
can verify an extract's `source_pages` attestation against the real
publication (confirm page 42 of the extract really is page 42 of the
original), and so the extract can be re-derived later with a different page
range if the topic scope changes, without re-sourcing the original document.

**Naming convention**: same base name as the extract(s) it backs, e.g.

```
data/guideline_sources/
  national_guidelines_sbi_FULL.pdf              <- the complete 100-page publication
data/excerpt_guidelines/
  kenya_sbi_guideline_sbi_pages_42_45.pdf        <- the 4-page extract, actually ingested
  manifest.json                                  <- "source_pages": [42, 43, 44, 45] for the extract above
```

**Same gitignore treatment as `excerpt_guidelines/`**: large and licensed —
never committed. Only this `README.md` and `.gitkeep` are tracked.
