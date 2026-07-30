# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x | ✅ |

## Reporting a vulnerability

Please **do not open a public issue** for a security problem. Report it through
GitHub's [private vulnerability reporting](https://github.com/saianthireddy/ai-doctor/security/advisories/new),
or email the maintainer.

Expect an acknowledgement within a few days and an assessment shortly after.

## Known posture — read this before deploying

This is a portfolio project at `0.1.0`. Being direct about its limits is more
useful than a reassuring paragraph:

- **There is no authentication or authorisation.** Every endpoint is open. Do
  not expose this to the internet as-is; put it behind your own auth layer.
- **There is no multi-tenancy.** All ingested documents share one index. Anyone
  who can query can retrieve from any document that has been ingested.
- **Uploads are parsed by third-party libraries** (`pypdf`, `python-docx`,
  `python-pptx`, `openpyxl`). A malicious file is a risk those libraries own.
  Uploads are size-capped (`MAX_UPLOAD_MB`) and written to a temporary directory
  that is deleted after extraction, but they are not sandboxed.
- **No rate limiting.** Add it at your ingress.
- **Secrets come from the environment only.** No key is ever written to the
  database or logged. `.env` is gitignored.

## What is deliberately safe

- The Docker image runs as a **non-root** user (uid 10001).
- The SQL agent pattern is not present here — no user input reaches a database
  query; the metadata store is only ever written by the ingestion path.
- The offline default generator is **extractive**: it can only return sentences
  that appear in retrieved documents, so it cannot emit fabricated content.
- Uploads are rejected by extension *before* being written to disk, and by size
  *before* being parsed.
