# Docker assets

The Dockerfiles live at the repository root so build context is the whole project
without needing `-f` gymnastics:

- `../Dockerfile` — multi-stage production image, non-root, healthchecked
- `../Dockerfile.dev` — editable install with `--reload`
- `../docker-compose.yml` — default stack, plus an opt-in `production` profile
  with Postgres and a Qdrant server

See [../docs/deployment.md](../docs/deployment.md).
