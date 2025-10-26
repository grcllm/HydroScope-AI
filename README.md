# DPWH Agentic Web (Gemini)

ADK web app for analytics on DPWH flood control projects. The ADK entrypoint is `dpwh_web_agent.agent:root_agent` and the project is designed to use the Gemini Developer API (set `GOOGLE_API_KEY` in your `.env`).

## Quick start (Windows CMD)

Prereqs:
- Python 3.10+ (the project works on 3.13)
- Git
- GNU Make (optional; on Windows you can use WSL, Git Bash, or run commands manually)

1) Create a venv and install dependencies (preferred):

```bat
python -m venv .venv
.venv\Scripts\activate
make install-timeout   # recommended on flaky networks; or `make install`
```

If you prefer manual pip commands, run:

```bat
.venv\Scripts\python.exe -m pip install -r requirements.txt --default-timeout=120 --retries=10
```

2) Create a `.env` file in the repo root (do not commit it). A minimal `.env`:

```env
GOOGLE_API_KEY=your_api_key_here
GEMINI_MODEL=gemini-2.5-flash
# Optional: use Vertex AI instead of Gemini Developer API
# GOOGLE_GENAI_USE_VERTEXAI=1
# GOOGLE_CLOUD_PROJECT=your-project
# GOOGLE_CLOUD_LOCATION=your-location
```

An example `.env.example` is included in the repo for reference.

3) Run the ADK Web UI (preferred):

```bat
adk web run dpwh_web_agent.agent:root_agent
```

Fallback (without ADK CLI):

```bat
.venv\Scripts\python.exe adk_app\dpwh_web_agent\agent.py
```

## Makefile targets (convenience)

This repo includes a `Makefile` with common tasks. Useful targets:

- `make venv` — create `.venv` if missing
- `make install` — install `requirements.txt` into `.venv`
- `make install-timeout` — install with longer timeout and retries (helpful when pip times out)
- `make install-mirror` — install using a PyPI mirror (tunable)
- `make test-imports` — quick import sanity check for core deps
- `make run-agent` — run `python adk_app\dpwh_web_agent\agent.py` (fallback)
- `make run-adk` — run ADK via `adk` CLI (if installed)
- `make download-wheelhouse` — download wheels for offline installs
- `make wheelhouse-install` — install using a local `wheelhouse`

See `Makefile` for exact commands. On Windows, you can run these commands from Git Bash, WSL, or execute the underlying `python`/`pip` commands using `.venv\Scripts\python.exe` and `.venv\Scripts\pip.exe`.

## Troubleshooting: pip timeouts / network issues

If `pip install -r requirements.txt` fails with a connection timeout to `pypi.org`, try one of the following:

- Increase timeout and retries (recommended):

```bat
.venv\Scripts\python.exe -m pip install -r requirements.txt --default-timeout=120 --retries=10
```

- Use a PyPI mirror (example: Tsinghua mirror) if your region has an available mirror:

```bat
.venv\Scripts\python.exe -m pip install -r requirements.txt --index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

- If you're behind a corporate proxy, set `HTTP_PROXY` / `HTTPS_PROXY` environment variables before running pip.

- Offline install: on a machine with internet, run `pip download -r requirements.txt -d wheelhouse`, copy `wheelhouse/` to this machine, then run `pip install --no-index --find-links=wheelhouse -r requirements.txt`.

If you still have trouble, run the pip command with `--default-timeout=120 --retries=10 --trusted-host pypi.org --trusted-host files.pythonhosted.org` and paste the last 50 lines of output here.

## Dataset and data loading

- Datasets are expected in `adk_app/dpwh_web_agent/dpwh_agent/data/` or the repo-level `data/` folder. The data loader will search common locations — see `agent1_fetch.agent1_run()`.
- The sample dataset filename used by default is `normalized_dpwh_flood_control_projects.csv`. You can set `DATA_DIR` in your `.env` to point to a custom folder.

## Code layout

- `adk_app/dpwh_web_agent/agent.py` — ADK entrypoint wiring the root agent and sub-agents
- `adk_app/dpwh_web_agent/dpwh_agent/agents/` — agent implementations (agent1_fetch, agent2_process, agent3_answer)
- `adk_app/dpwh_web_agent/dpwh_agent/agentic/tools.py` — callable tools exposed to the Gemini SDK
- `adk_app/dpwh_web_agent/dpwh_agent/shared.py` — shared helpers (column resolution, formatting)
- `adk_app/dpwh_web_agent/dpwh_agent/utils/` — utilities (schema, text normalization, storage)

## Development notes

- The analytics core is `agent3_answer.agent3_run()`; `agentic/tools.py` provides stable tool wrappers (some thin wrappers call `agent3_run`, others perform small, explicit DataFrame operations). Shared helpers live in `shared.py` to reduce duplication.
- Pagination state for follow-up questions is kept in-memory for the ADK process lifetime.

## Ask for help

If you hit problems running the app, paste the last error text here and I'll help debug. If pip times out, include the pip output (last 40–60 lines).

