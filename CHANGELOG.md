# Changelog

All notable changes to this project are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

Nothing yet. See [ROADMAP.md](ROADMAP.md) for what is planned.

## [0.1.0] — 2026-07-29

First release. Everything below is implemented and covered by tests; see the
status table in the README for what is deliberately *not* claimed.

### Added

- **Extraction** for PDF, DOCX, PPTX, XLSX, HTML and Markdown behind a single
  registry, emitting labelled sections (`page 3`, `slide 2`, `sheet Sales`) so
  citations can name a place in the document.
  - DOCX headings become section labels; tables are read rather than skipped.
  - PPTX includes speaker notes.
  - XLSX repeats the header onto every row and reads formulas as cached values.
- **Section-aware chunking** that never spans two sections, falling back
  paragraph → sentence → hard window in that order, with backward overlap.
- **Hashing embedder** (offline, deterministic, sub-token hashed) and an OpenAI
  embedder behind the same interface.
- **Two vector stores** — Qdrant in embedded mode and an exact in-memory
  reference — held to one shared contract test suite.
- **BM25 lexical index** with conservative stemming, so "charged for seats"
  matches "per-seat licence charges".
- **Hybrid retrieval** fusing dense and lexical results with Reciprocal Rank
  Fusion rather than score normalisation.
- **Reranking** on content-term coverage and phrase adjacency.
- **Grounded answering** with citations, and a refusal path when nothing clears
  the relevance threshold.
- **Intent router** over four handlers (answer, lookup, summarise, inventory).
- **FastAPI** REST API with OpenAPI docs and meaningful status codes.
- **SQLAlchemy** metadata store (SQLite by default, any URL supported).
- Multi-stage non-root **Docker** image, Compose stack, Makefile.
- 116 tests at 94% coverage; CI on Python 3.11 and 3.12 including a boot smoke
  test and a Docker run check.

### Fixed during development

Found by the tests in this release rather than shipped and patched later:

- Stopword overlap let an out-of-corpus question clear the refusal threshold.
- HTML headings ran into body text (`"SetupInstall the agent"`).
- Missing BM25 stemming made plural/verb forms unmatchable.
- `dimensions or 384` silently converted an explicit `0` to the default.
- SQLite `:memory:` needed `StaticPool`; without it every connection saw an
  empty database.
- Qdrant accepted a zero query vector where the reference store refused it.
- A `coverage` `omit` and a Codecov `ignore` entry both used `file:Symbol`
  syntax. Both take path globs, so the lines did nothing while appearing
  deliberate; the network-dependent classes are excluded with
  `# pragma: no cover` instead, which works.
- `build_llm` and `build_reranker` had no test for an unknown backend name,
  surfaced by an unreached `raise` in the coverage report.
- The documented Postgres path could not work: SQLAlchemy ships no driver and
  none was declared, so a `postgresql://` URL failed at import with
  `ModuleNotFoundError: No module named 'psycopg'`. Added a `[postgres]` extra
  so the path is installable, and said so in the README and deployment docs.

[Unreleased]: https://github.com/saianthireddy/ai-doctor/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/saianthireddy/ai-doctor/releases/tag/v0.1.0
