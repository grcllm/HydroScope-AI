from __future__ import annotations

import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]  # <root>/adk_app/dpwh_web_agent/agent.py -> parents[2] = <root>
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Load .env at repo root if present (GOOGLE_API_KEY, GEMINI_MODEL, etc.)
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_REPO_ROOT / ".env", override=True)
except Exception:
    pass

from google.adk.agents import Agent  # type: ignore

from dpwh_web_agent import prompt
from dpwh_web_agent.sub_agents.data_prep.agent import data_prep_agent
from dpwh_web_agent.sub_agents.analytics.agent import analytics_agent
from dpwh_web_agent.tools.memory import _load_precreated_dataset


root_agent = Agent(
    model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    name="root_agent",
    description="DPWH analytics agent using multiple sub-agents",
    instruction=prompt.ROOT_AGENT_INSTR,
    sub_agents=[
        data_prep_agent,
        analytics_agent,
    ],
    before_agent_callback=_load_precreated_dataset,
)


if __name__ == "__main__":
    # Try to start ADK Web UI using common entrypoints with graceful fallback.
    port = int(os.environ.get("PORT", "8000"))
    try:
        # Preferred API
        from google.adk.web import run  # type: ignore
        print(f"[dpwh_web_agent] Starting ADK Web UI on http://localhost:{port}")
        run(root_agent, port=port)
    except Exception:
        try:
            # Alternate API names to improve resilience across ADK versions
            from google.adk.webui import run as run_ui  # type: ignore
            print(f"[dpwh_web_agent] Starting ADK Web UI on http://localhost:{port}")
            run_ui(root_agent, port=port)
        except Exception as e:
            print("[dpwh_web_agent] Could not start ADK Web UI automatically.")
            print("Reason:", e)
            print(
                "If you have an ADK CLI, try: adk web run dpwh_web_agent.agent:root_agent"
            )
