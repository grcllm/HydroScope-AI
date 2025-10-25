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