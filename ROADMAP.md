# Roadmap

What is planned, and — more usefully — what is deliberately *not* here yet.

The [README status table](README.md#status--whats-real-what-isnt) is the source
of truth for what works today. This file is about direction.

## Principle

Nothing moves to ✅ in the status table until a test proves it. A capability that
cannot be tested in CI gets marked 🟡 and stays there. That rule is why this
roadmap is shorter than the feature list of a comparable project.

## 0.2.0 — measurement *(done, unreleased)*

The most valuable missing thing was not a feature, it was a number.
Results: **[docs/evaluation.md](docs/evaluation.md)**.

A prerequisite this roadmap originally missed: the corpus was too small to
measure anything. 8 chunks against a `candidate_k` of 12 meant every query
returned the whole index. It was expanded to 67 chunks first.

- [x] **A labelled evaluation set.** ~50 question/passage pairs over the sample
      corpus, including paraphrases and deliberately unanswerable questions.
- [x] **Retrieval metrics** — Precision@1, Recall@k, MRR, nDCG — with the harness
      published so the numbers are reproducible from a clean clone.
- [x] **A refusal metric.** False-answer rate on unanswerable questions is the
      number this project should be judged on, and it does not exist yet.
- [x] Ablations: dense only vs lexical only vs hybrid, reranker on vs off. Any of
      these could show a component is not earning its place.

## 0.3.0 — verifying the 🟡 rows

- [ ] Postgres exercised in CI via a service container, promoting it to ✅.
- [ ] Qdrant **server** mode exercised in CI alongside embedded.
- [ ] OpenAI paths behind a recorded-cassette test so they are covered without a
      live key.
- [ ] Cross-encoder reranking with a cached model, and a measured comparison
      against the lexical reranker. If it does not win, that gets published too.

## 0.4.0 — scale and safety

- [ ] Authentication and per-tenant document isolation. Until this exists the
      security posture in [SECURITY.md](SECURITY.md) stands.
- [ ] Background ingestion for large corpora, with a job API.
- [ ] Incremental re-ingest: detect unchanged files by content hash and skip them.
- [ ] Prune documents deleted from a watched folder.

## Later, maybe

Honest about uncertainty — these are interesting, not committed:

- **OCR** for scanned PDFs. Adds a heavy system dependency (Tesseract); worth it
  only if scanned documents turn out to be a real use case.
- **Knowledge graph** over extracted entities. Genuinely useful for multi-hop
  questions, and genuinely a lot of work to do well. Currently ❌, not 🟡.
- **Streaming answers** over SSE.
- **A web UI.** The API and `/docs` cover the current use cases.

## Explicitly not planned

- Connectors for Confluence, Notion, SharePoint, Slack, Jira and Drive. Each is a
  real integration with real auth, and listing them without building them is the
  thing this project is trying not to do.
- Kubernetes manifests and Terraform. Meaningless without a deployment that needs
  them; the Docker image and Compose file cover single-node.
