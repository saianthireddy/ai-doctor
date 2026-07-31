"""Retrieval evaluation: labelled set, metrics, ablations, refusal measurement."""

from aidoctor.evaluation.dataset import (
    DatasetError,
    EvalQuestion,
    load_questions,
    validate_against,
)
from aidoctor.evaluation.metrics import (
    RefusalScores,
    RetrievalScores,
    score_retrieval,
)
from aidoctor.evaluation.runner import (
    IndexTooSmall,
    build_variants,
    evaluate_refusal,
    evaluate_variant,
    guard_index_size,
    section_key,
)

__all__ = [
    "DatasetError",
    "EvalQuestion",
    "IndexTooSmall",
    "RefusalScores",
    "RetrievalScores",
    "build_variants",
    "evaluate_refusal",
    "evaluate_variant",
    "guard_index_size",
    "load_questions",
    "score_retrieval",
    "section_key",
    "validate_against",
]
