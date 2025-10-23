## Run on Windows (CMD)

Prereqs:
- Python 3.10+ (works on 3.13)
- pip

Setup once:
- python -m venv .venv
- .venv\Scripts\activate
- pip install -r dpwh_agent/requirements.txt

Environment:
- Copy .env.example to .env and set GOOGLE_API_KEY, or
- In CMD for the session:
  - set GOOGLE_API_KEY=your_api_key_here
  - set AGENTIC_MODE=1
  - set GEMINI_MODEL=gemini-2.5-flash

Deterministic baseline (no API key required):
- python scripts\quick_check.py

Agentic non-interactive smoke test (requires GOOGLE_API_KEY):
- python scripts\agentic_smoketest.py

Interactive orchestrator (agentic):
- python -m dpwh_agent.orchestrator
  - Type a question, e.g. "highest approved budget in NCR" or "top 3 highest approved budget in NCR"
  - Type exit to quit

Notes:
- To force deterministic mode, set AGENTIC_MODE=0
- To use Vertex AI instead of the Gemini Developer API, set GOOGLE_GENAI_USE_VERTEXAI, GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION in .env