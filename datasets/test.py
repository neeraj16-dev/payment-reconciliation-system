import pandas as pd

df = pd.read_csv("expected_discrepancies_ground_truth_manifest.csv")
print(df["transaction_date"].head(10))