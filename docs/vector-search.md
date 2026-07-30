# Hybrid retrieval

## Why not dense alone

Semantic embeddings are excellent at paraphrase and terrible at identifiers. An
embedding of `ERR_LOCK_TIMEOUT` lands near "something about errors and timeouts",
which is exactly wrong when the user wants the one passage containing that exact
token.

Enterprise corpora are full of identifiers: error codes, SKUs, invoice numbers,
licence keys, config flags. Those are the queries where lexical search wins
outright.

Observed on this project's own fixture corpus:

| Query | Dense top-1 | Lexical top-1 |
|---|---|---|
| `ERR_LOCK_TIMEOUT` | Troubleshooting (0.44) | Troubleshooting (2.74) |
| `how am I charged for seats` | Performance (0.06) ✗ | Billing (1.39) ✓ |

The second row is the interesting one: dense retrieval put the *wrong* section
first. The hashing embedder is not semantic, so this understates what a real
embedder would do — but it illustrates why one retriever is not enough.

## Why not score normalisation

The obvious fusion is: normalise both score distributions, add them, sort. It is
fragile.

BM25 scores are **unbounded** and depend on corpus statistics — idf shifts as
documents are added. Cosine similarity sits in **[-1, 1]**. Any min-max or z-score
normalisation across the two is a hidden weighting, and that weighting *drifts as
the corpus grows*. You tune it on 100 documents and it is wrong at 10,000.

## Reciprocal Rank Fusion

RRF throws away magnitudes and fuses **ranks**:

```
score(chunk) = Σ  weight_i / (k + rank_i(chunk))
```

- A chunk both retrievers rank highly wins.
- A chunk only one retriever found still places, if it ranks near the top there.
- `k` (default 60) damps the influence of the single top position, so rank 1 does
  not dominate rank 2 by an unreasonable margin.

`test_rrf_ignores_raw_score_magnitude` asserts the property directly: two ranked
lists with identical ordering but scores differing by five orders of magnitude
fuse to the same result.

## Stemming, and why only on the lexical side

BM25 terms are stemmed with conservative suffix stripping (`ing`, `ed`, `es`, `s`,
minimum stem length 3). Without it, "charged for seats" returns **nothing** against
text reading "per-seat licence charges" — observed before it was added.

Stemming is deliberately **not** applied to the embedder. Dense models benefit
from surface form; stripping suffixes discards signal the model can use. The
tokenizer is shared, the stemmer is not.

Error codes survive: `err_lock_timeout` is unchanged, because no listed suffix
matches.

## Reranking

Fusion cannot see one thing: whether a passage addresses *all* of the question or
just one rare word of it. A chunk matching a single high-idf term can outrank a
chunk matching every term.

The reranker scores content-term **coverage** (0.6), phrase **adjacency** (0.3) and
a rank **prior** (0.1). Two rules matter:

- **Stopwords are excluded** from coverage. Counting them made irrelevant passages
  score 0.25 on any question phrased as a question.
- **No content-term match means score zero**, so the rank prior alone cannot carry
  an irrelevant passage past a downstream threshold.

## Backend parity

Two vector stores implement one interface. The in-memory store does exact cosine,
so it serves as the **oracle**:

```python
def test_qdrant_and_memory_agree_on_ranking(small_embedder):
    ...
    assert [r.chunk.chunk_id for r in memory.search(query, 3)] == \
           [r.chunk.chunk_id for r in qdrant.search(query, 3)]
```

Both are also held to the same contract for idempotent upsert, scoped deletion,
payload round-tripping, and refusing a zero query vector. The last one was a real
divergence: Qdrant happily returned results for a zero vector where the reference
store returned none, so the guard was added to keep the contract honest.

## Qdrant point ids

Qdrant requires an unsigned integer or a UUID. Chunk ids here are 32-character
content hashes, converted via `uuid5` with a fixed namespace — deterministic, so
the same chunk always maps to the same point and upsert stays idempotent. The
original id lives in the payload, because that is what the rest of the system
uses.
