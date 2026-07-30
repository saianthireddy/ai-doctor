# Examples

## `corpus/`

Four documents in four formats, used by `make demo` and by the integration tests
as a realistic mixed corpus:

| File | Format | Contains |
|---|---|---|
| `handbook.docx` | DOCX | Password reset, billing, troubleshooting sections |
| `licence.pdf` | PDF | Two pages on licence terms and volume pricing |
| `sales.xlsx` | XLSX | A small regional sales sheet |
| `runbook.md` | Markdown | Deployment and rollback notes |

They deliberately **share vocabulary** — `seat`, `licence`, `queue` — so no
question is answerable by keyword uniqueness alone.

## Try it

```bash
make demo
```

Ingests all four, then asks five questions. The last one
(*"who won the 1998 world cup"*) is **not** in the corpus and is refused — that is
the behaviour being demonstrated, not a bug.
