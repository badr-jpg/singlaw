"""Download-free step 2: convert the Hugging Face SSO statutes parquet files to JSONL.

    cd backend
    uv run --with pandas --with pyarrow python ../scripts/prepare_sso_statutes.py

Reads  data/corpus/sso_statutes/{sections,documents}.parquet
Writes data/corpus/sso_statutes/{sections,documents}.jsonl  (the loader reads JSONL,
so the project needs no parquet dependency) and prints a sample to check the format.
"""
from pathlib import Path

import pandas as pd

DIR = Path(__file__).resolve().parents[1] / "data" / "corpus" / "sso_statutes"

for name in ("sections", "documents"):
    df = pd.read_parquet(DIR / f"{name}.parquet")
    df.to_json(DIR / f"{name}.jsonl", orient="records", lines=True, force_ascii=False)
    print(f"\n{name}: {df.shape[0]:,} rows · columns {list(df.columns)}")
    if "doc_type" in df.columns:
        print("doc_type values:", df["doc_type"].value_counts().to_dict())
    for _, r in df.head(3).iterrows():
        print({k: (str(v)[:120] + "…" if len(str(v)) > 120 else v) for k, v in r.items()})
print(f"\nwritten to {DIR}")
