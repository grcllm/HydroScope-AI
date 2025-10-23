import os
import sys
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("DATA_DIR", str(ROOT / "dpwh_agent" / "data"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dpwh_agent.agents.agent1_fetch import agent1_run
from dpwh_agent.agents.agent2_process import agent2_run
from dpwh_agent.agents.agent3_answer import detect_filters, apply_filters, _apply_time_filters, find_column


def main():
    path = agent1_run()
    df = agent2_run(path)
    q = "highest approved budget in NCR"
    filters = detect_filters(q, df)
    sub = apply_filters(df, filters)
    sub = _apply_time_filters(sub, None)
    budget_col = find_column(sub, ['approved_budget_num', 'approved_budget_for_contract', 'approvedbudgetforcontract', 'approved_budget', 'budget', 'contractcost', 'approved budget for contract'])
    sub = sub.copy()
    sub[budget_col] = pd.to_numeric(sub[budget_col], errors='coerce')
    valid = sub.dropna(subset=[budget_col])
    row = valid.loc[valid[budget_col].idxmax()]
    # Determine columns
    pid_col = None
    for name in ['project_id','projectid','ProjectID']:
        if name in valid.columns:
            pid_col = name
            break
    print("Chosen columns:")
    print(" project_id_col:", pid_col)
    muni_col = find_column(valid, ['municipality','city'])
    prov_col = find_column(valid, ['province'])
    dist_col = find_column(valid, ['legislative_district','legislativedistrict'])
    loc_col = find_column(valid, ['project_location','location'])
    print(" municipality_col:", muni_col)
    print(" province_col:", prov_col)
    print(" district_col:", dist_col)
    print(" project_location_col:", loc_col)
    print()
    print("Row preview:")
    print(" pid:", row.get(pid_col))
    print(" municipality:", row.get(muni_col))
    print(" province:", row.get(prov_col))
    print(" district:", row.get(dist_col))
    print(" project_location:", row.get(loc_col))


if __name__ == "__main__":
    main()
