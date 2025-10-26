import pandas as pd

PATH = r"c:\GhostBusters\dpwh-agentic-project\data\normalized_cleaned_dpwh_flood_control_projects.csv"

def main():
    df = pd.read_csv(PATH)
    mask = df['province'].astype(str).str.contains('Davao', case=False, na=False) | df['municipality'].astype(str).str.contains('Davao', case=False, na=False)
    subset = df[mask]
    print('Total rows with Davao in muni/prov:', len(subset))
    print('Unique provinces:', sorted(subset['province'].dropna().astype(str).unique()))
    muni_unique = sorted(list(subset['municipality'].dropna().astype(str).unique()))
    print('Unique municipalities (count):', len(muni_unique))
    print('Sample municipalities:', muni_unique[:50])
    print('Unique regions for these rows:', sorted(subset['region'].dropna().astype(str).unique()))

if __name__ == '__main__':
    main()
