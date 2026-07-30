#!/usr/bin/env python3
"""Ingest the sample corpus and ask it questions. No API key, no services.

Run: python scripts/demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

from aidoctor.api.dependencies import build_container
from aidoctor.config.settings import Settings

QUESTIONS = [
    "how do I reset my password",
    "how am I charged for seats",
    "what does ERR_LOCK_TIMEOUT mean",
    "what documents do you have",
    "who won the 1998 world cup",
]


def main() -> int:
    examples = Path(__file__).resolve().parents[1] / "examples" / "corpus"
    if not examples.exists():
        print(f"No sample corpus at {examples}", file=sys.stderr)
        return 1

    container = build_container(
        Settings(database_url="sqlite:///:memory:", embedding_dimensions=384,
                 qdrant_collection="demo")
    )

    print("=" * 78)
    print("INGEST")
    print("=" * 78)
    for path in sorted(examples.iterdir()):
        if path.is_file():
            result = container.ingest.ingest_path(path)
            print(f"  {result.filename:22} {result.source_type:5} "
                  f"sections={result.sections:<3} chunks={result.chunks}")

    print()
    print("=" * 78)
    print("ASK")
    print("=" * 78)
    for question in QUESTIONS:
        result = container.router.route(question)
        verdict = "REFUSED " if result.escalated else "ANSWERED"
        print(f"\n  [{verdict}] intent={result.intent} confidence={result.confidence}")
        print(f"  Q: {question}")
        print(f"  A: {result.text[:180]}")
        if result.citations:
            print(f"  Sources: {', '.join(result.citations)}")

    print()
    print("The last question is refused on purpose: it is not in the corpus, and")
    print("guessing would be worse than saying so.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
