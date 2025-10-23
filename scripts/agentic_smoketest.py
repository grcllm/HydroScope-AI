import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Ensure project root is on sys.path and DATA_DIR is set BEFORE importing modules
ROOT = Path(__file__).resolve().parents[1]
# Load .env from project root so GOOGLE_API_KEY and other vars are available
load_dotenv(dotenv_path=ROOT / ".env")
os.environ.setdefault("DATA_DIR", str(ROOT / "dpwh_agent" / "data"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dpwh_agent.agents.agent1_fetch import agent1_run
from dpwh_agent.agents.agent2_process import agent2_run
from dpwh_agent.agentic import tools as agentic_tools
from dpwh_agent.agentic.gemini_client import build_client, default_config, DEFAULT_MODEL


def run_agentic(prompt: str) -> str:
    """Run a single non-interactive agentic call using Gemini tools and return final text."""
    # Prepare data
    dataset_path = agent1_run()
    df = agent2_run(dataset_path)

    # Register tools with the current dataframe
    agentic_tools.set_dataframe(df)
    tool_callables = agentic_tools.tools_list()

    # Build client and config
    client = build_client()
    cfg = default_config(tools=tool_callables)

    # Non-streaming call for simplicity; SDK handles automatic function calling
    resp = client.models.generate_content(
        model=DEFAULT_MODEL,
        contents=prompt,
        config=cfg,
    )
    # Return the final text if present, otherwise join parts text
    if getattr(resp, "text", None):
        return resp.text
    parts = getattr(resp, "parts", None)
    if parts:
        return "".join([getattr(p, "text", "") for p in parts if getattr(p, "text", None)])
    return "(no text in response)"


def main():
    prompts = [
        "highest approved budget in NCR",
        "top 3 highest approved budget in NCR",
        "highest approved budget in region 2",
        "highest approved budget in region 4",
    ]
    for p in prompts:
        print(f"\n=== Prompt: {p}")
        try:
            out = run_agentic(p)
            print(out)
        except Exception as e:
            print(f"Agentic call failed; reason: {e}. Falling back to deterministic path.")
            # Fallback: run deterministic Agent 2 + Agent 3 quickly
            dataset_path = agent1_run()
            df = agent2_run(dataset_path)
            from dpwh_agent.agents.agent3_answer import agent3_run
            print(agent3_run(p, df))


if __name__ == "__main__":
    main()
