# Evaluation

An earlier version of this file said there was no headline metric *on purpose*,
because there was no labelled set and a metric without one is theatre. It listed
the ablations that "could embarrass the design" and promised to publish them
whichever way they landed.

They have been run. One of them did embarrass the design, and it is below.

Reproduce with:

```bash
python scripts/make_corpus.py     # regenerate the sample corpus
python scripts/evaluate.py        # print the tables on this page
```

## The corpus had to be fixed before anything could be measured

The first attempt was abandoned. The sample corpus held **8 chunks** while
`candidate_k` was **12**, so every query returned the entire index. Recall@10
would have been 1.00 as a matter of arithmetic and Precision@1 a coin toss over
eight items.

That is the failure this project most wants to avoid: *a benchmark that cannot
fail cannot detect a regression either*. The corpus was expanded to **67 chunks**
across 12 documents in 6 formats before a single number was recorded.

Two guards keep it honest:

- `guard_index_size()` raises `IndexTooSmall` and refuses to print scores when
  the index is not larger than the ranking depth.
- `test_the_benchmark_can_fail` scores a saboteur retriever that ignores the
  query and returns the same chunks every time. The real retriever must beat it
  by a wide margin. If they ever converge, the benchmark is measuring nothing
  and the suite fails.

## The set

`examples/evaluation/questions.json` — **52 questions**: 46 answerable, 6
unanswerable. Labelled by `filename#section` rather than chunk id, because chunk
ids are content hashes: editing one word inside a section would invalidate every
label at once and look like a retrieval regression rather than a broken file.

The corpus is adversarial by construction (`scripts/make_corpus.py`):

- **Shared vocabulary.** `password`, `seat`, `licence`, `queue` and `restart`
  each appear in at least three documents.
- **Near-miss sections.** `security-policy.docx` covers password *rules*; only
  `handbook.docx` covers how to *reset* one.
- **Sibling error codes.** `ERR_LOCK_TIMEOUT`, `ERR_LOCK_CONFLICT` and
  `ERR_QUEUE_FULL` all exist, so exact-token matching is not enough.
- **Plausible unanswerable questions**, not only absurd ones.

## Retrieval results

Ranking depth 10, averaged over the 46 answerable questions.

| Strategy | P@1 | P@5 | R@5 | R@10 | MRR | nDCG@10 |
|---|---:|---:|---:|---:|---:|---:|
| dense only | 0.522 | 0.174 | 0.696 | 0.790 | 0.616 | 0.641 |
| lexical only (BM25) | 0.543 | 0.196 | 0.761 | 0.833 | 0.669 | 0.686 |
| hybrid (RRF) | 0.543 | 0.191 | 0.761 | 0.822 | 0.650 | 0.676 |
| **hybrid + rerank** | **0.674** | **0.209** | **0.801** | **0.844** | **0.748** | **0.752** |

### Hybrid retrieval does not beat BM25 alone here

This is the result that embarrasses the design, and it stays published. On this
corpus, fusing dense and lexical is **slightly worse** than lexical alone:
MRR 0.650 vs 0.669, nDCG 0.676 vs 0.686, R@10 0.822 vs 0.833.

The honest reading is that the embedder is the problem, not the fusion. The
offline default is a *hashing* embedder — deterministic, dependency-free and
semantically blind. It has no notion that "undo a bad deployment" relates to
"rollback". Fusing a weak dense list into a decent lexical one drags it down a
little. RRF is doing its job on poor input.

That is a testable prediction, and it is the first thing to check when the
OpenAI embedder is exercised: **if hybrid still does not overtake lexical with
real embeddings, the fusion is not earning its place and should be removed.**
Saying so in advance is the point.

### Reranking clearly earns its place

Reranking lifts P@1 from 0.543 to **0.674** and MRR from 0.650 to **0.748** — the
largest improvement in the table, from the cheapest component. Locked in by
`test_reranking_beats_plain_hybrid_on_this_corpus`, so a regression fails the
build rather than quietly making this page untrue.

## Refusal

The number this project should be judged on.

| Relevance floor | False-answer rate | Wrongly-refused rate |
|---:|---:|---:|
| 0.10 | 0.500 | 0.000 |
| **0.15 (default)** | **0.333** | **0.000** |
| 0.20 | 0.333 | 0.065 |
| 0.25 | 0.167 | 0.196 |
| 0.35 | 0.167 | 0.370 |
| 0.60 | 0.000 | 0.739 |

Both columns are reported together deliberately. Any system can drive false
answers to zero by refusing everything — the last row does exactly that, while
refusing 74% of the questions it could have answered.

`MIN_RELEVANCE` moved from 0.12 to **0.15**, which the sweep shows is free: it
cuts the false-answer rate by a third and wrongly refuses *nothing* that 0.12
answered. Past 0.15 the trade stops being free, so it stops there. The previous
default was chosen by inspection; this one was chosen by measurement.

### What still gets through

At the default, 2 of 6 unanswerable questions are answered:

- *"what is the parental leave policy"* — answered at confidence **0.56** from
  the handbook's **annual** leave section. This is the dangerous case: plausible
  question, topically adjacent section, high confidence. No threshold below 0.5
  catches it, and 0.5 would refuse most real questions.
- *"how do I export my data to CSV"* — answered at 0.225 from release notes that
  mention a billing-portal export.

Both are semantic near-misses that a lexical relevance floor cannot separate.
Fixing them needs an embedder that knows "parental leave" is not "annual leave",
which is the strongest argument in this repo for the OpenAI path or a real
cross-encoder.

Worth noting what the gate *does* catch: `who won the 1998 world cup`, `what is
the airspeed velocity of an unladen swallow`, `which cloud provider do we host
on`, and `what is our quarterly revenue forecast for next year` are all refused.

## Metrics, and why these

| Metric | Answers |
|---|---|
| Precision@1 | Is the top passage right? |
| Recall@k | Is the right passage anywhere in the context window? |
| MRR | How far down is the first hit, on average? |
| nDCG@k | Are the good ones near the top? |
| **False-answer rate** | How often does it answer what it should refuse? |
| **Wrongly-refused rate** | How much does that caution cost? |

The last two matter more here than the first four. A system at 0.85 Precision@1
that never refuses is worse for a support desk than one at 0.75 that declines
cleanly, because a confident wrong answer costs more than a gap.

nDCG is included because MRR only sees the first hit: with three relevant
sections it cannot distinguish "all three in the top three" from "one at rank
one and the rest at rank forty".

## Limitations

- **One corpus, 12 synthetic documents.** These numbers describe this corpus.
  They do not predict performance on real technical documentation.
- **Binary relevance.** A section is relevant or not; there is no graded
  judgement, so nDCG here is coarser than usual.
- **Labelled by the author.** One person wrote the corpus and the questions,
  which is a real bias. Questions were written against a dump of section keys
  rather than from memory, which helps slightly and does not remove it.
- **Answer text is not scored**, only retrieval and the refusal decision. Answer
  quality under the extractive default remains unmeasured.
- **Not yet run against the OpenAI embedder or a cross-encoder**, which is where
  the hybrid-vs-lexical question gets settled.
