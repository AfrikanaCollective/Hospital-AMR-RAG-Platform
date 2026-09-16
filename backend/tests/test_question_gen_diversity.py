"""Diversity filter (ARCH §15.1 step 7; DEVIATIONS.md #67, #113)."""

from __future__ import annotations

from app.eval.question_gen.diversity import cosine_similarity, is_near_duplicate


def test_cosine_similarity_identical_vectors_is_one() -> None:
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0


def test_cosine_similarity_orthogonal_vectors_is_zero() -> None:
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_cosine_similarity_zero_vector_is_zero_not_a_crash() -> None:
    assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0


def test_is_near_duplicate_true_above_threshold() -> None:
    accepted = [[1.0, 0.0]]
    assert is_near_duplicate([0.99, 0.01], accepted, threshold=0.9)


def test_is_near_duplicate_false_below_threshold() -> None:
    accepted = [[1.0, 0.0]]
    assert not is_near_duplicate([0.0, 1.0], accepted, threshold=0.9)


def test_is_near_duplicate_false_when_nothing_accepted_yet() -> None:
    assert not is_near_duplicate([1.0, 0.0], [], threshold=0.9)
