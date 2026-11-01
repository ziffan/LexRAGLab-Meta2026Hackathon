# Testing

Purpose: how to run the test suites, what they need, and what CI runs and skips.
The README keeps a one-line summary.

## Run locally

```bash
uv sync --frozen && uv run pytest -q      # backend, tests in backend/tests
cd frontend && npm ci && npx tsc --noEmit && npx vitest run
```

Tests never call the Model API and need no `.env`; Model API behaviour is tested against stored runs.

## Requirements for the full backend suite

- **Tokenizer.** The Muse Spark Open tokenizer must be in the local Hugging Face cache: gated repo (accept the terms on Hugging Face), revision pinned in `config/tokenizer.toml`, only the three tokenizer files (`tokenizer.json`, `tokenizer_config.json`, `special_tokens_map.json`), no weights. Without it the loader silently falls back to `o200k_base` and tokenizer-dependent tests fail (API, replay, header, chunker, and measurement tests).
- **torch and bge-m3.** Dense-retrieval tests need torch and the `BAAI/bge-m3` weights (revision pinned in `config/retrieval.toml`); some skip without CUDA or bge-m3, and one grid-compare test fails without the weights.
- **Windows.** Clone with `git clone -c core.longpaths=true -c core.autocrlf=false`; some paths under `runs/` exceed the default Windows path-length limit, and line endings must stay LF.

## What CI runs

[`.github/workflows/ci.yml`](../.github/workflows/ci.yml), on every push to `main` and on manual dispatch:

- **Frontend:** `npm ci`, type check, and the full vitest suite.
- **Backend (light subset):** `uv sync --frozen` without torch and its CUDA packages, an empty Hugging Face cache, offline, and no secrets. pytest runs with the test files that need torch or the gated tokenizer ignored; the ignore list is in the workflow file.

CI does not run the tokenizer-dependent tests (API, replay, header B, most chunker tests, measurement) or the dense-retrieval tests. Those run only locally, on a machine with the tokenizer, torch, and bge-m3. A green CI badge therefore covers the frontend and the light backend subset, not the full backend suite.
