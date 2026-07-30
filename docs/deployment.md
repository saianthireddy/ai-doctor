# Deployment

## What is verified

CI builds the Docker image, **boots it**, and probes `/api/v1/health` — a build
that compiles but cannot serve is a green check that lies. It also boots the app
with uvicorn directly and hits it over real HTTP, because the test suite uses
`TestClient` and never exercises the ASGI server itself.

What CI does **not** verify: Postgres, and Qdrant in server mode. Both are
declared in `docker-compose.yml` behind the `production` profile and documented
here, but nothing proves them. They are 🟡 in the README status table.

## Single container

```bash
docker build -t ai-doctor .
docker run -p 8000:8000 -v aidoctor-data:/app/data ai-doctor
```

The image is multi-stage — the wheel is built with tooling the runtime never sees
— and runs as a **non-root** user (uid 10001). The `HEALTHCHECK` calls the app's
own health endpoint, so an unhealthy container is one that cannot answer, not
merely one whose process is alive.

Data lives in `/app/data` (SQLite plus any embedded Qdrant state). Mount a volume
or lose it on restart.

## Compose

Default stack — AI Doctor alone, no services to provision:

```bash
docker compose up
```

With Postgres and a Qdrant server (**unverified path**):

```bash
docker compose --profile production up
```

Then point the app at them:

```bash
DATABASE_URL=postgresql+psycopg://aidoctor:aidoctor@postgres:5432/aidoctor
QDRANT_URL=http://qdrant:6333
```

Install the driver first — SQLAlchemy does not ship one, and without it a
`postgresql://` URL fails at import with `ModuleNotFoundError: No module named
'psycopg'` before any connection is attempted:

```bash
pip install -e ".[postgres]"
```

## Configuration

Every setting has a working default. See [.env.example](../.env.example).

The settings worth thinking about in production:

| Variable | Consider |
|---|---|
| `EMBEDDER=openai` | The default hashing embedder is not semantic. This is the single biggest quality lever. |
| `LLM=openai` | The default generator is extractive — it cannot paraphrase. |
| `MIN_RELEVANCE` | Raise it to refuse more and answer less. Tune against your own corpus. |
| `MAX_UPLOAD_MB` | Enforced before parsing, so it is a real memory bound. |
| `DATABASE_URL` | Point at Postgres for anything multi-process. |

## Scaling notes, honestly

- **The BM25 index is in-process and not persisted.** Two API replicas have two
  independent lexical indexes, and a restart requires re-ingestion to restore
  lexical search. This is the first thing to fix before running more than one
  replica.
- **Ingestion is synchronous.** A large PDF blocks its request. There is no
  background queue.
- **Embedded Qdrant is per-process.** For multiple replicas you need Qdrant in
  server mode — which is exactly the path CI does not yet verify.

Given those three, this deploys correctly as a **single replica**. Anything more
needs the 0.4.0 roadmap items first.

## No auth

There is no authentication layer. Put this behind your own ingress auth, and read
[SECURITY.md](../SECURITY.md) before exposing it anywhere.
