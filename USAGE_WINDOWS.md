## Run on Windows (CMD)

Prereqs:
- Python 3.10+ (works on 3.13)
- pip
- Google ADK installed (provides the `adk` CLI)

Setup once:
- python -m venv .venv
- .venv\Scripts\activate
- pip install -r requirements.txt

Environment:
- Create `.env` in the repo root and set at least:
  - GOOGLE_API_KEY=your_api_key_here
  - GEMINI_MODEL=gemini-2.5-flash

Launch the ADK Web UI (preferred):
```bat
adk web run dpwh_web_agent.agent:root_agent
```

Alternative (without ADK CLI):
```bat
python adk_app\dpwh_web_agent\agent.py
```

Notes:
- This project now runs from the ADK app entrypoint `dpwh_web_agent.agent:root_agent`.
- Legacy scripts and the old `dpwh_agent.orchestrator` are deprecated and removed in favor of the web UI.
- To use Vertex AI instead of the Gemini Developer API, set GOOGLE_GENAI_USE_VERTEXAI, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION in .env.

Suppressing startup prints / quiet mode
------------------------------------

If you'd like to silence the small startup prints (for example the
`[dpwh_web_agent] Dataset ready: ...` line), you have two easy options on
Windows/CMD:

- Quick (no code changes): redirect stdout/stderr to NUL when running:

```bat
REM Run fallback entry silently
python adk_app\dpwh_web_agent\agent.py > NUL 2>&1

REM Or when using the adk CLI
adk web run dpwh_web_agent.agent:root_agent > NUL 2>&1
```

- Permanent (change source): replace `print(...)` calls with logging at DEBUG
  level so they no longer appear under default INFO. The two places to edit are:

  - `adk_app/dpwh_web_agent/tools/memory.py` — replace the `print(f"[dpwh_web_agent] Dataset ready: {csv_path}")` with a `logger.debug(...)` call.
  - `adk_app/dpwh_web_agent/dpwh_agent/agents/agent1_fetch.py` — remove or lower verbosity of the `print(f"\nSuccess! Dataset ready at: {path}")` in the `__main__` test block.

  Example snippet:

  ```py
  import logging
  logger = logging.getLogger(__name__)
  logger.debug(f"Dataset ready: {csv_path}")
  ```

  After making this change you can control visibility by configuring the root logging
  level in your entrypoint (for example in `agent.py`) or by setting environment-based
  logging configuration.