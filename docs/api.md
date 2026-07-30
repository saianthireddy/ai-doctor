# API reference

Base path `/api/v1`. Interactive docs at `/docs`, schema at `/openapi.json`.

## Ingest a document

```bash
curl -F "file=@handbook.docx" localhost:8000/api/v1/ingest
```

```json
{
  "doc_id": "c365c541d927cd875ba86bc8797d3782",
  "filename": "handbook.docx",
  "source_type": "docx",
  "sections": 3,
  "chunks": 3,
  "replaced_chunks": 0
}
```

`replaced_chunks` is non-zero on re-ingest: chunk ids are content-derived, so
uploading the same file again **replaces** its chunks rather than adding a second
copy.

### Status codes

| Code | Meaning |
|---|---|
| `201` | Ingested |
| `400` | Empty file |
| `413` | Exceeds `MAX_UPLOAD_MB` |
| `415` | Unsupported extension — response names the supported set |
| `422` | Supported type, unreadable file (e.g. a scanned PDF with no text layer) |

`415` and `422` are genuinely different failures and are tested separately: the
first is the caller's format choice, the second is this particular file.

## Ask a question

```bash
curl -X POST localhost:8000/api/v1/ask \
  -H 'content-type: application/json' \
  -d '{"question":"how do I reset my password"}'
```

```json
{
  "question": "how do I reset my password",
  "answer": "To reset your password open Settings and choose Reset Password.",
  "grounded": true,
  "escalated": false,
  "confidence": 0.7,
  "citations": ["[handbook.docx, Password reset]"],
  "passages": [{ "citation": "...", "score": 0.7, "method": "reranked" }],
  "intent": "answer",
  "handler": "grounded-answer"
}
```

When the corpus does not contain the answer:

```json
{
  "escalated": true,
  "grounded": false,
  "confidence": 0.0,
  "citations": [],
  "answer": "I could not find this in the indexed documents..."
}
```

**Check `escalated`, not just `answer`.** A refusal is a successful `200` — the
request worked, the corpus simply did not have it.

## Search passages

```bash
curl -X POST localhost:8000/api/v1/search \
  -H 'content-type: application/json' \
  -d '{"query":"licence charges","mode":"lexical","limit":5}'
```

`mode` is `hybrid` (default), `dense` or `lexical`. Exposing all three is a
debugging affordance: when a hybrid answer looks wrong, compare the two paths to
see which one is responsible.

## Documents

```bash
curl localhost:8000/api/v1/documents
curl -X DELETE localhost:8000/api/v1/documents/{doc_id}
```

Deletion removes the record and every chunk from both the vector store and the
BM25 index. Returns `404` for an unknown id, and `removed_chunks` on success.

## System

```bash
curl localhost:8000/api/v1/health
curl localhost:8000/api/v1/metrics
```

`/health` reports the **active backends**, which is the fastest way to confirm a
deployment is using the configuration you intended:

```json
{
  "status": "ok", "version": "0.1.0",
  "vector_backend": "qdrant", "embedder": "hashing",
  "reranker": "lexical-overlap", "llm": "extractive",
  "documents": 4, "chunks": 7
}
```

## Not implemented

There is **no authentication** on any endpoint. See [SECURITY.md](../SECURITY.md).
