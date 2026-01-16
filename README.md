# DPWH Agentic Analytics Platform

An intelligent conversational analytics platform for querying and analyzing Department of Public Works and Highways (DPWH) flood control project data using natural language. Built with Google's Gemini AI and Flask, this system provides an intuitive chat interface that understands context, remembers conversation history, and delivers precise insights about infrastructure projects across the Philippines.

## What It Does

This platform transforms complex CSV datasets into an interactive Q&A experience. Users can ask natural language questions like "What's the total budget for projects in Manila?" or "Who are the top contractors in Region 3?" and receive accurate, data-driven answers. The system intelligently handles follow-up questions, maintains conversation context across sessions, and provides paginated results for large datasets.

**Key Capabilities:**
- 🗣️ **Natural Language Queries**: Ask questions in plain English about projects, budgets, contractors, and locations
- 🧠 **Conversation Memory**: SQLite-based context system remembers your conversation and applies relevant context to follow-up questions
- 🔄 **Smart Follow-ups**: Handles implicit references like "show me more", "what's the total budget?", or "who is the contractor?"
- 📊 **Advanced Analytics**: Count projects, sum budgets, find top contractors, filter by location/year, calculate averages
- 🎯 **Entity Recognition**: Automatically extracts cities, regions, contractors, years, and project IDs from questions and responses
- 📄 **Pagination Support**: Browse large result sets with "more projects" or "next page" commands
- 🔍 **Fuzzy Matching**: Tolerant of misspellings and variations in location/contractor names
- 🌐 **Dual Interface**: Web chat UI (Flask) and ADK Web UI for testing

## How It Works

The system uses a multi-agent architecture powered by Google's Gemini API:

1. **Root Agent**: Orchestrates the conversation, understands user intent, and delegates to specialized sub-agents
2. **Analytics Agent**: Parses natural language queries into structured filters (location, year, contractor, action)
3. **Data Processing Agent**: Loads and normalizes DPWH CSV datasets, handles fuzzy matching
4. **Context System**: Extracts entities from questions/responses and applies them to follow-up queries automatically

**Technical Architecture:**
```
User Question → Root Agent → Analytics Engine → Data Processor → Response
                     ↓                               ↓
              Context Extractor → SQLite Database ← Session Manager
```

The conversation context system stores:
- **Sessions**: Unique user sessions with timestamps
- **Conversations**: Full Q&A history with parsed actions
- **Context Store**: Active entities (locations, contractors, project IDs, years)

This enables natural conversations like:
```
User: "What are the top projects in Manila?"
Bot: [Lists Manila projects]
User: "What's the total budget?"
Bot: [Calculates total for Manila projects - context applied automatically]
User: "Show me Quezon City instead"
Bot: [Switches context to Quezon City - old context cleared]
```

## Technology Stack

- **AI/ML**: Google Gemini 2.5 Flash (via google-genai SDK)
- **Backend**: Python 3.10+, Flask web framework
- **Database**: SQLite3 (conversation context and session management)
- **Data Processing**: pandas, pyarrow (optional for parquet caching)
- **Fuzzy Matching**: rapidfuzz (location/contractor name matching)
- **Configuration**: python-dotenv for environment management
- **Architecture**: ADK (Agent Development Kit) framework with tool-based delegation

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

3) **Run the Flask Web App** (recommended for chat interface):
```bat
python app.py
```
Then open **http://localhost:3000** in your browser.

4) **Or run the ADK Web UI** (for direct agent testing):
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


## Project layout (Refactored - Clean Structure)

```
adk_app/
  dpwh_web_agent/              # Main package
    agent.py                   # ADK entry point
    prompt.py                  # Agent prompts
    
    core/                      # Core business logic
      shared.py                # Shared utilities
      agents/                  # Agent implementations
        dataset_loader.py      # Dataset loading & normalization
        data_processor.py      # Data processing & parsing
        analytics_engine.py    # Analytics & question answering
      utils/                   # Helper utilities
        schema.py              # Schema utilities
        text.py                # Text processing
      data/                    # CSV datasets
    
    sub_agents/                # ADK sub-agents
      analytics/
        analytics_agent.py     # Analytics sub-agent
      data_prep/
        data_prep_agent.py     # Data preparation sub-agent
    
    tools/                     # Tool functions
      analytics_tools.py       # Main analytics tools API
      memory.py                # Dataset initialization
```

**Key improvements:**
- ✅ Descriptive file names (what each does is clear)
- ✅ All imports use relative paths
- ✅ Flattened structure (removed nested redundancy)
- ✅ Easy navigation in IDE
- ✅ No import confusion during refactoring

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


- Minimum effort alternative: change the `print(...)` to `#` comment to simply mute the line if you prefer editing directly.

These options let you keep useful debugging messages during development while silencing the few prints in production or CI.

