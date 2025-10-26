import sys
from pathlib import Path
import unittest

_HERE = Path(__file__).resolve()
_REPO_ROOT = _HERE.parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pandas as pd

from dpwh_web_agent.dpwh_agent.agents.agent3_answer import agent3_run, _PAGINATION_STATE
from dpwh_web_agent.dpwh_agent.agentic.tools import set_dataframe, top_projects_for_contractor


class PaginationTests(unittest.TestCase):
    def setUp(self):
        # Build a small DataFrame with many projects for the same contractor to exercise pagination
        rows = []
        contractor = "LEGACY CONSTRUCTION CORPORATION"
        for i in range(1, 13):
            rows.append({
                "project_id": f"P{100000 + i}LZ",
                "contractor": contractor,
                "approved_budget_num": 300000000 - i * 10000000,
                "municipality": "Testville",
            })
        df = pd.DataFrame(rows)
        # Ensure project id column name is recognized by the helper (common names)
        df = df.rename(columns={"project_id": "project_id"})
        self.df = df
        # Reset pagination state before each test
        _PAGINATION_STATE.update({"mode": None, "filters": None, "rows": None, "offset": 0, "header_ctx": ""})

    def test_nl_path_pagination(self):
        q = "list the top 5 with the highest approved budget for LEGACY CONSTRUCTION CORPORATION"
        resp1 = agent3_run(q, self.df)
        # First response should include top results and invite more when >5
        self.assertIn("Top", resp1)
        # If more are available, the reply should ask if user wants more
        if len(self.df) > 5:
            self.assertIn("Would you like 5 more", resp1)
        # Follow-up: request more
        resp2 = agent3_run("more", self.df)
        self.assertIn("More projects", resp2)

    def test_direct_tool_pagination(self):
        # Use the direct tool which should set pagination state
        set_dataframe(self.df)
        resp1 = top_projects_for_contractor("LEGACY CONSTRUCTION CORPORATION", 5)
        self.assertIn("Top", resp1)
        if len(self.df) > 5:
            self.assertIn("Would you like 5 more", resp1)
        # consume next page via agent3_run more
        resp2 = agent3_run("more", self.df)
        self.assertIn("More projects", resp2)


if __name__ == "__main__":
    unittest.main()
