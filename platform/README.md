# Platform

Phase 0 task pool service — FastAPI + SQLite + Ed25519 verification.

## Run

```bash
uvicorn agentswarm_platform.main:app --app-dir src --reload
```

## Test

```bash
python -m pytest -q tests
```

## Documentation

- [Architecture](../docs/architecture.md)
- [API reference](../docs/api.md)
- [ADR 0004 — Stack choice](../docs/adr/0004-stack-choice.md)
- [OpenAPI spec](../docs/protocol/openapi.yaml)

Interactive docs: http://127.0.0.1:8000/docs
