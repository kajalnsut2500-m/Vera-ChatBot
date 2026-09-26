# Vera — magicpin AI Challenge

A stateful merchant WhatsApp assistant. FastAPI + SQLite, deterministic rule-based composer, no LLM dependency in core paths.

## Requirements

- Python 3.11
- No external services required for tests

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env   # edit if needed
```

## Run

```bash
uvicorn app.main:app --port 8080
```

## Test

```bash
pytest -q          # 63 tests, all in-process, no network
```

## Simulator

```bash
# 1. Start the bot
uvicorn app.main:app --port 8080 &

# 2. Edit judge_simulator.py: set LLM_API_KEY and LLM_PROVIDER
# 3. Run
python judge_simulator.py
```

## Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | /v1/healthz | DB status per scope |
| GET | /v1/metadata | Team / version info |
| POST | /v1/context | Push merchant/category/trigger context |
| POST | /v1/tick | Generate outbound actions |
| POST | /v1/reply | Route inbound merchant reply |
| POST | /v1/teardown | Wipe all DB state |

## Deploy to Railway

### One-time setup

1. Push this branch to GitHub (already done).
2. Go to [railway.app](https://railway.app) → **New Project** → **Deploy from GitHub repo** → select `Vera-ChatBot`.
3. Railway detects the `Dockerfile` automatically.

### Persistent volume

4. In the Railway dashboard, open your service → **Volumes** → **Add Volume**.
5. Mount path: `/data`
6. Railway re-deploys with the volume attached.

### Environment variables

7. In the service → **Variables**, add:

| Variable | Value |
|----------|-------|
| `VERA_DB_PATH` | `/data/vera.db` |
| `VERA_GEMINI_API_KEY` | *(optional)* your Gemini API key |

Do **not** commit API keys to the repo.

### Public domain

8. Service → **Settings** → **Networking** → **Generate Domain**.
   Copy the URL (e.g. `https://vera-chatbot-production.up.railway.app`).

### Health check

- Path: `/v1/healthz`
- Railway uses `healthcheckPath = "/v1/healthz"` from `railway.toml` automatically.

### Replicas

- Keep **numReplicas = 1** (set in `railway.toml`). SQLite does not support concurrent writers across multiple instances.

### Verify

```bash
curl https://<your-domain>/v1/healthz
```

Expected: `{"status":"ok","uptime_seconds":...,"contexts_loaded":{}}`

## Optional: Gemini copy-polish

Set `VERA_GEMINI_API_KEY=<your-key>` in `.env` to enable engagement rewrites on `/v1/tick`. If the key is absent, the service times out, or the response is invalid, the deterministic draft is used unchanged.

## Known Limitations

- Composer is deterministic/rule-based; no LLM in the message path
- `submission.jsonl` not included (canonical 30 test pairs not provided)
- Hindi-English mix detection is heuristic (checks `identity.languages`)
