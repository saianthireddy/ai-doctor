"""Intent router over a small set of handlers.

This is a router plus four handlers — not "ten autonomous agents". The
distinction is deliberate: naming a 40-line function an agent inflates the
architecture diagram and invites a question the code cannot answer. What is here
is real and does something: classify the request, dispatch to the handler that
knows how to serve it, and report which one ran.

Classification is rule-based and ordered most-specific-first. That is a
legitimate engineering choice at this scale — it is deterministic, debuggable and
free — and the ``classify`` seam is where a learned classifier would slot in.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field

from aidoctor.models.document import ScoredChunk
from aidoctor.services.answerer import Answerer


class Intent(str):
    pass


ANSWER = "answer"
SUMMARISE = "summarise"
LOOKUP = "lookup"
INVENTORY = "inventory"

# Ordered: the first pattern to match wins, so the specific cases are listed
# before the general question form.
_INVENTORY_RE = (
    r"\b(what (documents|files|sources)|which documents"
    r"|list (the )?(documents|files)|what do you (have|know))\b"
)
_SUMMARISE_RE = r"\b(summar(y|ise|ize)|overview|tl;?dr|key points|main points)\b"
_LOOKUP_RE = r"\b([A-Z][A-Z0-9_]{4,}|error code|sku|invoice \d+)\b"

_RULES: list[tuple[str, re.Pattern]] = [
    (INVENTORY, re.compile(_INVENTORY_RE, re.I)),
    (SUMMARISE, re.compile(_SUMMARISE_RE, re.I)),
    (LOOKUP, re.compile(_LOOKUP_RE)),
    (ANSWER, re.compile(r".", re.S)),
]


def classify(query: str) -> str:
    for intent, pattern in _RULES:
        if pattern.search(query):
            return intent
    return ANSWER


@dataclass
class RouterResult:
    intent: str
    handler: str
    text: str
    citations: list[str] = field(default_factory=list)
    passages: list[ScoredChunk] = field(default_factory=list)
    escalated: bool = False
    confidence: float = 0.0


class Router:
    """Dispatches to exactly one handler and reports which."""

    def __init__(self, answerer: Answerer, inventory: Callable[[], list[str]] | None = None) -> None:
        self.answerer = answerer
        self._inventory = inventory or (lambda: [])
        self.handlers: dict[str, Callable[[str], RouterResult]] = {
            ANSWER: self._answer,
            LOOKUP: self._lookup,
            SUMMARISE: self._summarise,
            INVENTORY: self._inventory_handler,
        }

    def route(self, query: str) -> RouterResult:
        intent = classify(query)
        return self.handlers[intent](query)

    def _from_answer(
        self, intent: str, handler: str, query: str, *, context_k: int | None = None
    ) -> RouterResult:
        original = self.answerer.context_k
        if context_k:
            self.answerer.context_k = context_k
        try:
            answer = self.answerer.answer(query)
        finally:
            self.answerer.context_k = original
        return RouterResult(
            intent=intent,
            handler=handler,
            text=answer.text,
            citations=answer.citations,
            passages=answer.passages,
            escalated=answer.escalated,
            confidence=answer.confidence,
        )

    def _answer(self, query: str) -> RouterResult:
        return self._from_answer(ANSWER, "grounded-answer", query)

    def _lookup(self, query: str) -> RouterResult:
        # Exact-token queries need fewer, tighter passages: an error code has one
        # right answer and extra context only dilutes it.
        return self._from_answer(LOOKUP, "exact-lookup", query, context_k=2)

    def _summarise(self, query: str) -> RouterResult:
        # Summaries need breadth, so widen the context window.
        return self._from_answer(SUMMARISE, "summariser", query, context_k=8)

    def _inventory_handler(self, query: str) -> RouterResult:
        names = self._inventory()
        if not names:
            return RouterResult(
                intent=INVENTORY,
                handler="inventory",
                text="No documents are indexed yet.",
                escalated=True,
            )
        return RouterResult(
            intent=INVENTORY,
            handler="inventory",
            text=f"{len(names)} document(s) indexed: " + ", ".join(sorted(names)),
        )
