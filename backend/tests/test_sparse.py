"""BM25-style sparse vector construction (ARCH §6 "Sparse / BM25";
DEVIATIONS.md #48 — stable-hash indices, IDF applied server-side by Qdrant)."""

from __future__ import annotations

from app.retrieval.sparse import analyze, doc_sparse_vector, query_sparse_vector


def test_analyzer_lowercases_keeps_hyphens_and_numbers_drops_stopwords() -> None:
    tokens = analyze("The patient received co-amoxiclav 500mg/125mg for 5 days.")
    assert "the" not in tokens
    assert "for" not in tokens
    assert "co-amoxiclav" in tokens
    assert "500mg/125mg" in tokens
    assert "5" in tokens


def test_doc_sparse_vector_counts_term_frequency() -> None:
    vec = doc_sparse_vector("sepsis sepsis neonatal sepsis")
    assert len(vec["indices"]) == len(vec["values"]) == 2  # {sepsis, neonatal}
    assert max(vec["values"]) == 3.0  # "sepsis" appears 3x


def test_same_term_always_hashes_to_same_index() -> None:
    v1 = doc_sparse_vector("neonatal sepsis")
    v2 = doc_sparse_vector("sepsis in a neonatal patient")
    # "sepsis" and "neonatal" appear in both -> shared indices
    assert set(v1["indices"]).issubset(set(v2["indices"]))


def test_different_terms_hash_to_different_indices() -> None:
    v = doc_sparse_vector("sepsis jaundice hypothermia")
    assert len(set(v["indices"])) == 3


def test_query_sparse_vector_is_term_presence_only() -> None:
    qvec = query_sparse_vector("blood cultures blood")
    assert set(qvec["values"]) == {1.0}
    assert len(qvec["indices"]) == 2  # {blood, cultures} — dedup'd
