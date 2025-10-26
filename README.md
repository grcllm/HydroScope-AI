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

## First steps after clone

After cloning the repository, the quickest way to get started on Windows (CMD) is:

```bat
REM Clone the repo (replace <your-repo-url> with the project URL)
git clone <your-repo-url>
cd dpwh-agentic-project

REM Create venv and bootstrap (creates .venv, installs deps, and writes a .env template)
python -m venv .venv
.venv\Scripts\activate
make bootstrap

REM Edit .env to set your GOOGLE_API_KEY and other values, then run the web UI
adk web run dpwh_web_agent.agent:root_agent
```

If you don't have `make` on Windows, you can perform the same steps manually:

```bat
python -m venv .venv
.venv\Scripts\activate
.venv\Scripts\pip.exe install -r requirements.txt
copy .env.example .env
REM Edit .env with your API key
python adk_app\dpwh_web_agent\agent.py
```

## Key Python dependencies / imports

This project targets Python 3.10+ and depends on a small set of packages listed in `requirements.txt`.
Here are the main packages used at runtime:

- python-dotenv — environment variable loading from `.env`
- google-genai — Gemini / Google GenAI client used by the ADK integration
- pandas — data processing for the DPWH CSV datasets
- pyarrow — optional, used for faster parquet snapshots if available
- rapidfuzz — fuzzy matching utilities used by the agent

You can install these with `pip install -r requirements.txt` (the `bootstrap` Makefile target does this for you).


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

## Suppressing startup prints / quiet mode

If you want to avoid the small number of startup prints (for example:
`[dpwh_web_agent] Dataset ready: C:\...\normalized_...csv`), you have a few options:

- Quick (no code changes): redirect stdout/stderr to NUL when running from CMD:

```bat
REM Run ADK fallback entry silently
python adk_app\dpwh_web_agent\agent.py > NUL 2>&1

REM Or when using the adk CLI
adk web run dpwh_web_agent.agent:root_agent > NUL 2>&1
```

- Permanent (edit source): replace the `print(...)` calls with a logging call at DEBUG level so they no longer appear under default INFO logging.
	- File: `adk_app/dpwh_web_agent/tools/memory.py` — replace the line:

		```py
		print(f"[dpwh_web_agent] Dataset ready: {csv_path}")
		```

		with something like:

		```py
		import logging
		logger = logging.getLogger(__name__)
		logger.debug(f"Dataset ready: {csv_path}")
		```

	- File: `adk_app/dpwh_web_agent/dpwh_agent/agents/agent1_fetch.py` (only when running as script) — remove or lower the verbosity of the `print(f"\nSuccess! Dataset ready at: {path}")` used in the `__main__` test block.

	After this change you can control visibility by configuring the logging level in your entrypoint (for example, in `agent.py` or before starting ADK).

- Minimum effort alternative: change the `print(...)` to `#` comment to simply mute the line if you prefer editing directly.

These options let you keep useful debugging messages during development while silencing the few prints in production or CI.

