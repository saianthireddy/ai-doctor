# Evaluation

## There is no headline metric, on purpose

This project publishes **no** Precision@1, no nDCG, no answer-accuracy number.

That is not an oversight. There is no labelled evaluation set yet, and a retrieval
metric computed without one is theatre. The specific trap: with a small corpus and
a generous `top_k`, a benchmark can return everything you indexed and report a
perfect score — a benchmark that *cannot fail* also cannot detect a regression.

So instead of a number, here is the harness that would produce an honest one, and
what would make it trustworthy.

## What a trustworthy set needs

**Held-out phrasings, not held-out renderings.** If a question is generated from
the same template as the indexed passage, retrieval is matching a template, not
answering a question. Partition phrasings *before* generating queries.

**Shared vocabulary across topics.** If every topic has unique keywords, any
retriever scores perfectly and you learn nothing. The sample corpus deliberately
reuses `seat`, `licence`, `queue` and `reset` across sections.

**Deliberately unanswerable questions.** This is the one most sets omit, and for
this project it is the most important. The refusal path is a headline feature, so
**false-answer rate on unanswerable questions** is the metric it should be judged
on.

**Confusable pairs.** Billing vs licensing, password-reset vs account-access.
Residual error should concentrate there; if it does not, the set is too easy.

## Metrics worth reporting

| Metric | Answers |
|---|---|
| Precision@1 | Is the top passage right? |
| Recall@k | Is the right passage anywhere in the context window? |
| MRR | How far down is it, on average? |
| nDCG@k | Are the good ones near the top? |
| **False-answer rate** | How often does it answer something it should refuse? |
| **Refusal precision** | When it refuses, was it right to? |

The last two matter more here than the first four. A system with 0.85
Precision@1 that never refuses is worse for a support desk than one at 0.75 that
declines cleanly, because a confident wrong answer costs more than a gap.

## Ablations that could embarrass the design

An evaluation only earns trust if it could show a component is not pulling its
weight. These are the comparisons to run:

- **Dense only vs lexical only vs hybrid.** If hybrid does not beat both, RRF is
  complexity for nothing.
- **Reranker on vs off.** The lexical reranker might be adding little over fusion.
- **`lexical-overlap` vs a real cross-encoder.** If the cheap one is close, that is
  a genuinely useful finding. If it is far behind, that belongs in the README.
- **`MIN_RELEVANCE` sweep.** Plot false-answer rate against refusal rate and pick
  the threshold deliberately rather than leaving it at the default 0.12, which was
  chosen by inspection.

Whichever way those land, they get published. An ablation you only report when it
flatters you is not an ablation.

## What *is* measured today

Behaviour, not quality — 114 tests asserting that the pipeline does what it claims:

- Out-of-corpus questions are refused (3 questions, plus the empty query)
- Every answer sentence is traceable to a retrieved passage
- Qdrant and exact cosine agree on ranking
- Re-ingest replaces rather than duplicates
- Reranking promotes full coverage over a single rare-term match
- The same corpus and question give the same answer across runs

That is a floor: it proves the system is not broken. It does not prove the answers
are good. Those are different claims and this project only makes the first one.
