# The router

## What this is, and what it is not

This is a **router plus four handlers**. It is not ten autonomous agents, and it
is described that way on purpose.

Naming a forty-line function an "agent" inflates the architecture diagram and
invites a question the code cannot answer. What is here is small, real, and does
something measurable: classify the request, dispatch to the handler that knows how
to serve it, and report which one ran.

## The handlers

| Intent | Handler | What it changes |
|---|---|---|
| `answer` | `grounded-answer` | Default: retrieve, rerank, generate, cite |
| `lookup` | `exact-lookup` | Narrows context to 2 passages |
| `summarise` | `summariser` | Widens context to 8 passages |
| `inventory` | `inventory` | Answers from the metadata store; no retrieval |

The differences are deliberate and small:

- **Lookup** narrows the window. An error code has one right answer; extra context
  dilutes it.
- **Summarise** widens it. A summary needs breadth or it is just an answer.
- **Inventory** does not retrieve at all. "What documents do you have?" is a
  question about the metadata store, and routing it through the vector index would
  produce a semantically-similar wrong answer.

## Classification

Rule-based, ordered most-specific-first. First match wins.

```python
_RULES = [
    (INVENTORY, ...),   # "what documents do you have"
    (SUMMARISE, ...),   # "summarise", "overview", "key points"
    (LOOKUP,    ...),   # ALL_CAPS_TOKENS, "error code", "invoice 123"
    (ANSWER,    ...),   # catch-all
]
```

Rule-based is a legitimate choice at this scale: deterministic, debuggable, free,
and it never needs training data. `classify()` is the seam where a learned
classifier would slot in without touching a handler.

The ordering is load-bearing. "Summarise the ERR_LOCK_TIMEOUT section" contains an
all-caps token, so a lookup-first ordering would narrow the context window on a
request that needs it widened.

## The bug in temporarily widening context

`_from_answer` mutates `answerer.context_k` for the summariser, then restores it in
a `finally` block:

```python
original = self.answerer.context_k
if context_k:
    self.answerer.context_k = context_k
try:
    answer = self.answerer.answer(query)
finally:
    self.answerer.context_k = original
```

Without the restore, one summary request would silently widen the context window
for every subsequent question in the process — a slow, invisible quality change.
`test_router_restores_context_k_after_widening` guards it.

## What would justify calling these agents

Nothing here plans, uses tools, or loops. A handler that could decide to search
again with a reformulated query, or call an external tool and incorporate the
result, would earn the name. That is on the roadmap; until then, the honest word
is handler.
