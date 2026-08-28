# Opportunity OS

Open-source opportunity discovery, matching and application preparation system with explainable scoring and human approval.

## V0.1 status

The first slice exposes a minimal FastAPI service and a stable health contract. Opportunity ingestion, matching, persistence, and profile handling are introduced incrementally in later slices.

Opportunity OS is intentionally **not** an auto-apply bot. It does not submit CVs, send messages, bypass CAPTCHAs, or automate restricted employment platforms.

## Local development

Requires Python 3.12+.

```bash
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Health check:

```text
GET /health
```

Expected response:

```json
{"status":"ok","service":"opportunity-os"}
```

Run tests:

```bash
python -m pytest -v
```

## Design

The V0.1 design and implementation plan live under `docs/superpowers/`.

## License

MIT
