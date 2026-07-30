"""LLM interface plus a deterministic offline generator.

``ExtractiveLLM`` is the default: it composes an answer from the retrieved
passages themselves rather than generating prose. That makes the whole platform
runnable and testable with no API key, and it has a property a real model does
not — it cannot hallucinate, because every sentence it emits came from a
retrieved chunk.

It is therefore a *floor*, not a substitute. It cannot paraphrase, reconcile
contradictions, or answer a question whose answer is implied across two passages.
``OpenAIChatLLM`` is the production path.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from aidoctor.embeddings.base import tokenize
from aidoctor.models.document import ScoredChunk

_SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class Completion:
    text: str
    model: str
    grounded: bool


class LLM(Protocol):
    name: str

    def complete(self, question: str, passages: list[ScoredChunk]) -> Completion: ...


class ExtractiveLLM:
    """Selects the sentences from the passages that best answer the question."""

    name = "extractive"

    def __init__(self, max_sentences: int = 3) -> None:
        self.max_sentences = max_sentences

    def complete(self, question: str, passages: list[ScoredChunk]) -> Completion:
        if not passages:
            return Completion(text="", model=self.name, grounded=False)

        terms = set(tokenize(question))
        scored: list[tuple[float, str]] = []
        for rank, passage in enumerate(passages, start=1):
            for sentence in _SENTENCE.split(passage.chunk.text):
                sentence = " ".join(sentence.split())
                if len(sentence) < 20:
                    continue
                overlap = len(terms & set(tokenize(sentence)))
                if not overlap:
                    continue
                # Favour overlap, then earlier-ranked passages.
                scored.append((overlap + 1.0 / rank, sentence))

        if not scored:
            return Completion(text="", model=self.name, grounded=False)
        scored.sort(key=lambda pair: -pair[0])

        chosen: list[str] = []
        for _, sentence in scored:
            if sentence not in chosen:
                chosen.append(sentence)
            if len(chosen) >= self.max_sentences:
                break
        return Completion(text=" ".join(chosen), model=self.name, grounded=True)


class OpenAIChatLLM:  # pragma: no cover - requires network + key
    """Production generator, instructed to refuse rather than invent."""

    name = "openai"

    SYSTEM = (
        "You answer strictly from the provided context. If the context does not "
        "contain the answer, say so plainly and do not speculate. Cite the source "
        "label for each claim."
    )

    def __init__(
        self, model: str = "gpt-4o-mini", temperature: float = 0.0, api_key: str | None = None
    ) -> None:
        self.model = model
        self.temperature = temperature
        self._api_key = api_key

    def complete(self, question: str, passages: list[ScoredChunk]) -> Completion:
        from openai import OpenAI

        if not passages:
            return Completion(text="", model=self.model, grounded=False)
        context = "\n\n".join(f"[{p.chunk.citation}]\n{p.chunk.text}" for p in passages)
        client = OpenAI(api_key=self._api_key) if self._api_key else OpenAI()
        response = client.chat.completions.create(
            model=self.model,
            temperature=self.temperature,
            messages=[
                {"role": "system", "content": self.SYSTEM},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
            ],
        )
        return Completion(text=response.choices[0].message.content or "", model=self.model, grounded=True)


def build_llm(name: str = "extractive", **kwargs) -> LLM:
    if name == "extractive":
        return ExtractiveLLM(**kwargs)
    if name == "openai":
        return OpenAIChatLLM(**kwargs)
    raise ValueError(f"Unknown LLM {name!r}. Available: extractive, openai")
