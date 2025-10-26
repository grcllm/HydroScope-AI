# DPWH Agentic Web (Gemini)

ADK web app for analytics on DPWH flood control projects. The ADK entrypoint is `dpwh_web_agent.agent:root_agent` and uses the Gemini Developer API (GOOGLE_API_KEY).

## Quick start (Windows CMD)

1) Create a venv and install deps:
```bat
python -m venv .venv
.venv\Scripts\activate
 pip install -r requirements.txt
```

2) Configure your environment in `.env` (repo root):
```
GOOGLE_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.5-flash
```

3) Run the ADK Web UI (preferred):
```bat
adk web run dpwh_web_agent.agent:root_agent
```

Alternative (without ADK CLI):
```bat
python adk_app\dpwh_web_agent\agent.py
```

## Project layout

- `adk_app/dpwh_web_agent/agent.py` – main ADK entry
- `adk_app/dpwh_web_agent/sub_agents/` – data prep and analytics sub-agents
- `adk_app/dpwh_web_agent/dpwh_agent/` – co-located core logic (agents, utils, tools)
- `dpwh_agent/data/` – CSV dataset files (kept as data-only)

Legacy code (CLI orchestrator and old ADK-style shim) has been removed/deprecated in favor of the ADK web app. Top-level `dpwh_agent` package is now a stub that raises an ImportError to prevent accidental imports; use `dpwh_web_agent.dpwh_agent` instead.

## Notes

- Tools cover counts, budgets, top contractors, and project lookups. The model auto-selects tools when answering.
- A parquet snapshot may be written during processing to speed up reloads (optional if pyarrow installed).
- `.env` is git-ignored. Don’t commit secrets.

