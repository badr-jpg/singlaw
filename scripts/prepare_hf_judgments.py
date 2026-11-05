"""Convert the badlaldh/singapore-judgments passages from Parquet to JSONL.

    cd backend
    uv run --with pandas --with pyarrow python ../scripts/prepare_hf_judgments.py

Reads  data/corpus/hf_judgments/train-00000-of-00001.parquet
Writes data/corpus/hf_judgments/passages.jsonl (the loader reads JSONL, so the
project needs no parquet dependency).
"""
from pathlib import Path

import pandas as pd

DIR = Path(__file__).resolve().parents[1] / "data" / "corpus" / "hf_judgments"

df = pd.read_parquet(DIR / "train-00000-of-00001.parquet")
df.to_json(DIR / "passages.jsonl", orient="records", lines=True, force_ascii=False)
print(f"{df.shape[0]:,} passages from {df['citation'].nunique()} judgments, written to {DIR}")
