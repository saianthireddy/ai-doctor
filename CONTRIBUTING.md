# Contributing

Thanks for considering a contribution.

## Getting set up

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
make test
```

No API keys, no services, no network. If a change requires any of those to
*test*, that is a signal the change needs an interface and a fake.

## Before you open a PR

```bash
make lint     # ruff
make test     # 114 tests
make cov      # coverage must not fall
```

## What a good PR looks like here

**Tests that can fail.** A test asserting `assert result is not None` proves
almost nothing. Assert the specific behaviour, and where practical assert the
thing that would break if the logic were wrong — see
`test_qdrant_and_memory_agree_on_ranking` for the pattern.

**Comments that explain *why*, not *what*.** The codebase deliberately records
the reasoning behind non-obvious choices (why RRF and not score normalisation,
why headers are repeated onto spreadsheet rows). Match that.

**Honesty about scope.** If you add a backend you cannot test, mark it 🟡 in the
README status table rather than ✅. A claim nothing verifies is a liability, and
the status table is the most valuable thing in this README.

**One concern per PR.** A retrieval change and a Docker change are two PRs.

## Adding a new extractor

1. Implement the `Extractor` protocol in `src/aidoctor/extractors/`.
2. Register it in `_registry()` in `extractors/base.py`.
3. Add a fixture to `tests/conftest.py` that **generates a real file** of that
   format — do not mock the parsing library.
4. Add tests for the happy path, an unreadable file, and an empty file.

## Adding a vector store backend

Implement the `VectorStore` protocol and add your backend to the `store` fixture
parametrisation in `tests/vectorstore/test_stores.py`. The whole contract suite
will then run against it, including ranking parity with the exact reference
store. If it cannot pass that suite, it is not a drop-in.

## Commit messages

Explain the reasoning, not just the diff. `Fix reranker` is unhelpful;
`Exclude stopwords from coverage so out-of-corpus questions are refused` tells a
reviewer why the change exists.

## Reporting bugs

Use the issue templates. A reproduction — ideally a failing test — is worth more
than a description.
