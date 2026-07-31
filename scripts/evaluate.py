#!/usr/bin/env python3
"""Score retrieval on the labelled set and print the tables in the README.

Run: ``python scripts/evaluate.py``

No API key, no services. The numbers this prints are the numbers published; if
they stop matching, CI fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

from aidoctor.api.dependencies import build_container
from aidoctor.config.settings import Settings
from aidoctor.evaluation import (
    build_variants,
    evaluate_refusal,
    evaluate_variant,
    guard_index_size,
    load_questions,
    section_key,
    validate_against,
)

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "examples" / "corpus"
QUESTIONS = ROOT / "examples" / "evaluation" / "questions.json"
DEPTH = 10


def main() -> int:
    if not CORPUS.exists():
        print(f"No corpus at {CORPUS}", file=sys.stderr)
        return 1

    container = build_container(
        Settings(
            database_url="sqlite:///:memory:",
            embedding_dimensions=384,
            qdrant_collection="eval",
        )
    )
    for path in sorted(CORPUS.iterdir()):
        if path.is_file():
            container.ingest.ingest_path(path)

    guard_index_size(container.retriever, DEPTH)

    questions = load_questions(QUESTIONS)
    available = {section_key(c) for c in container.retriever.store.all_chunks()}
    validate_against(questions, available)

    answerable = [q for q in questions if q.answerable]
    print(f"corpus:    {container.retriever.size} chunks")
    print(f"questions: {len(answerable)} answerable, {len(questions) - len(answerable)} unanswerable")
    print()

    print("| Strategy | P@1 | P@5 | R@5 | R@10 | MRR | nDCG@10 |")
    print("|---|---:|---:|---:|---:|---:|---:|")
    for variant in build_variants(container.retriever):
        scores = evaluate_variant(variant, questions, depth=DEPTH)
        print(scores.as_row(variant.name))

    print()
    refusal = evaluate_refusal(container.router.route, questions)
    print("| Path | False-answer rate | Wrongly-refused rate |")
    print("|---|---:|---:|")
    print(refusal.as_row("router (end to end)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
