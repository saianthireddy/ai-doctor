"""Loading and validating the labelled question set.

Labels are ``"<filename>#<section label>"`` rather than chunk ids. Chunk ids are
content hashes, so editing one word in a document would silently invalidate the
whole label file with no error — the ids would simply stop matching and every
score would fall to zero, looking like a retrieval regression. Filename and
section label survive edits to the prose inside a section.

``validate_against`` closes the remaining gap: a label naming a section that no
longer exists is a broken label, and the harness refuses to run rather than
quietly scoring it as a miss.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class EvalQuestion:
    id: str
    question: str
    relevant: frozenset[str]
    note: str = ""

    @property
    def answerable(self) -> bool:
        return bool(self.relevant)


class DatasetError(Exception):
    """Raised when the label file cannot be trusted."""


def load_questions(path: Path) -> list[EvalQuestion]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw = payload["questions"]
    questions = [
        EvalQuestion(
            id=item["id"],
            question=item["question"],
            relevant=frozenset(item["relevant"]),
            note=item.get("note", ""),
        )
        for item in raw
    ]

    seen: set[str] = set()
    for question in questions:
        if question.id in seen:
            raise DatasetError(f"duplicate question id: {question.id}")
        seen.add(question.id)
    return questions


def validate_against(questions: list[EvalQuestion], available: set[str]) -> None:
    """Every label must name a section that exists in the indexed corpus."""
    unknown = sorted({key for question in questions for key in question.relevant} - available)
    if unknown:
        raise DatasetError("labels reference sections that are not in the corpus: " + ", ".join(unknown))
