# Makefile for dpwh-agentic-project
# Targets support common developer workflows on Windows and *nix.
# Note: On Windows use the venv python/pip explicitly (.venv\Scripts\python.exe)

ifeq ($(OS),Windows_NT)
PY := .venv\\Scripts\\python.exe
PIP := .venv\\Scripts\\pip.exe
else
PY := .venv/bin/python
PIP := .venv/bin/pip
endif
REQS := requirements.txt
AGENT := adk_app/dpwh_web_agent/agent.py

.PHONY: help venv install install-timeout install-mirror test-imports run-agent run-adk \
	download-wheelhouse wheelhouse-install install-no-index bootstrap env-example

help:
	@echo "Makefile targets:"
	@echo "  make venv               -> create virtualenv (.venv)"
	@echo "  make install            -> install requirements from $(REQS) into .venv"
	@echo "  make install-timeout    -> install with longer timeout and retries (useful on flaky networks)"
	@echo "  make install-mirror     -> install using a PyPI mirror (TUNA example)"
	@echo "  make test-imports       -> quick import sanity check for core deps"
	@echo "  make run-agent          -> run ADK fallback entry (python $(AGENT))"
	@echo "  make run-adk            -> run ADK web (requires `adk` CLI)"
	@echo "  make bootstrap          -> create venv, install deps, and create .env template (quick start)"
	@echo "  make download-wheelhouse -> download wheels for offline install into ./wheelhouse"
	@echo "  make wheelhouse-install -> install from ./wheelhouse (offline install)"

venv:
	@echo "Creating virtualenv .venv (if missing)"
	@if [ ! -d .venv ]; then python -m venv .venv; echo "Created .venv"; else echo ".venv already exists"; fi

install: venv
	@echo "Installing requirements into .venv"
	@$(PIP) install -r $(REQS)


.PHONY: bootstrap
bootstrap: venv
	@echo "Bootstrapping project: creating venv and installing dependencies..."
	@$(PIP) install -r $(REQS)
	@if [ -f .env ]; then \
		echo ".env already exists"; \
	else \
		echo "GOOGLE_API_KEY=your_api_key_here" > .env; \
		echo "GEMINI_MODEL=gemini-2.5-flash" >> .env; \
		echo ".env created (edit with your credentials)"; \
	fi
	@echo "Bootstrap complete. Edit .env then run 'make run-adk' or 'make run-agent'."

.PHONY: env-example
env-example:
	@echo "Creating .env.example with placeholders"
	@printf "GOOGLE_API_KEY=your_api_key_here\nGEMINI_MODEL=gemini-2.5-flash\n" > .env.example
	@echo ".env.example created. Copy to .env and fill in your values."

install-timeout: venv
	@echo "Installing requirements with longer timeout and retries"
	@$(PY) -m pip install -r $(REQS) --default-timeout=120 --retries=10

install-mirror: venv
	@echo "Installing requirements using TUNA mirror (change if you prefer a different mirror)"
	@$(PY) -m pip install -r $(REQS) --index-url https://pypi.tuna.tsinghua.edu.cn/simple

test-imports: venv
	@echo "Running quick import check for key modules"
	@$(PY) - <<PY
import importlib
mods = ['dotenv','pandas','google.genai']
res = {}
for m in mods:
    try:
        importlib.import_module(m)
        res[m] = 'OK'
    except Exception as e:
        res[m] = f'ERR: {type(e).__name__}: {e}'
print(res)
PY

run-agent: venv
	@echo "Running ADK fallback entry: python $(AGENT)"
	@$(PY) $(AGENT)

run-adk:
	@echo "Run ADK Web UI using adk CLI (if installed): adk web run dpwh_web_agent.agent:root_agent"
	@adk web run dpwh_web_agent.agent:root_agent

download-wheelhouse:
	@echo "Downloading wheels for offline install into ./wheelhouse"
	@mkdir -p wheelhouse || true
	@python -m pip download -r $(REQS) -d wheelhouse

wheelhouse-install: venv
	@echo "Installing from local wheelhouse"
	@$(PY) -m pip install --no-index --find-links=wheelhouse -r $(REQS)

install-no-index: venv
	@echo "Install from wheelhouse (alias)"
	@$(MAKE) wheelhouse-install
