# DPWH Agentic Project (Agentic AI with Gemini 2.5 Pro)

This project answers questions about DPWH flood control projects and now includes an agentic mode powered by Gemini 2.5 Pro with function-calling and streaming output. Deterministic mode (regex + pandas) remains available as a fallback.

## Getting Started

### Setup Environment

You only need to create one virtual environment for all examples in this course. Follow these steps to set it up:

```bash
# Create virtual environment in the root directory
python -m venv .venv
# Windows CMD:
.venv\Scripts\activate.bat

# Install dependencies
pip install -r requirements.txt

# Configure environment (copy and edit as needed)
# Ensure .env is NOT committed; rotate any exposed keys
setx GOOGLE_API_KEY "<your_gemini_api_key>"
setx GOOGLE_GENAI_USE_VERTEXAI "FALSE"
setx AGENTIC_MODE "1"
setx MAX_MEMORY_TURNS "5"

# Optional data/session dirs
setx DATA_DIR ".\\data"
setx SESSION_DIR ".\\sessions"

### Run

Activate your venv and start the CLI:

```bash
python -m dpwh_agent.orchestrator
```

- Agentic mode streams responses and uses Gemini tool-calling to execute analytics.
- Set `AGENTIC_MODE=0` to use the deterministic parser only.

### Notes

- Tools: The agent exposes callable tools (count, budgets, top contractors, lookups) and a generic `answer_dpwh_question` tool. The model selects tools automatically.
- Parquet fast-path: Processing stage may emit a Parquet snapshot; the loader prefers Parquet when available.
- Privacy: `.env` is ignored via `.gitignore`. Rotate any keys that were shared previously.
```

