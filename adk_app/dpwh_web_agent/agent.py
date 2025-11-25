from __future__ import annotations

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
    
load_dotenv(dotenv_path=_REPO_ROOT / ".env", override=True)



from google.adk.agents import Agent  # type: ignore

from . import prompt
from .sub_agents.data_prep.data_prep_agent import data_prep_agent
from .sub_agents.analytics.analytics_agent import analytics_agent
from .tools.memory import _load_precreated_dataset


root_agent = Agent(
    model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
    name="root_agent",
    description="DPWH analytics agent using multiple sub-agents, Always greet the user first with a friendly welcome message.",
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
