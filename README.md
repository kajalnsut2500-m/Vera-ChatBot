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
pytest -q          # 50 tests, all in-process, no network
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

## Known Limitations

- Composer is deterministic/rule-based; no LLM in the message path
- `submission.jsonl` not included (canonical 30 test pairs not provided)
- Hindi-English mix detection is heuristic (checks `identity.languages`)
