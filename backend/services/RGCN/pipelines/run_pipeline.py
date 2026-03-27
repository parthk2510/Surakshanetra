# -*- coding: utf-8 -*-
"""
Convenient wrapper that runs the full pipeline from step 1 → step 6.
"""

import argparse
import subprocess
import sys
from pathlib import Path

# Resolve the directory that contains this script (backend/services/rgcn/)
BASE_DIR = Path(__file__).resolve().parent

# Mapping of step → script file (relative to BASE_DIR)
STEPS = [
    ("Step 1 – Preprocess",          "pipelines/step1_preprocess.py"),
    ("Step 2 – Isolation Forest",    "pipelines/step2_isolation_forest.py"),
    ("Step 3 – Graph construction", "pipelines/step3_graph_construction.py"),
    ("Step 4 – RGCN training",       "pipelines/step4_rgcn_training.py"),
    ("Step 5 – Score merging",       "pipelines/step5_score_merging.py"),
    ("Step 6 – PKL serialization",  "pipelines/step6_pkl_serialization.py"),
]


def run_step(script_path: Path, dataset: str = None):
    cmd = [sys.executable, str(script_path)]
    if dataset and script_path.name == "step1_preprocess.py":
        cmd.append(dataset)
    result = subprocess.run(cmd, cwd=BASE_DIR, capture_output=False)
    if result.returncode != 0:
        raise RuntimeError(
            f"{script_path.name} failed (exit {result.returncode})")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dataset",
        default=str(BASE_DIR / "data" / "transactions.parquet"),
        help="Path to the raw transaction file (.parquet or .csv)",
    )
    parser.add_argument(
        "--from-step",
        type=int,
        default=1,
        help="Start execution at this step (1‑6)",
    )
    args = parser.parse_args()

    print("\n" + "="*60)
    print("   UPI Fraud Detection – Full RGCN Pipeline")
    print("="*60 + "\n")

    for i, (name, script) in enumerate(STEPS, start=1):
        if i < args.from_step:
            print(f"[SKIP] {name}")
            continue
        script_path = BASE_DIR / script
        print(f"\n{'='*60}\n[{i}] {name}\n{'='*60}")
        run_step(script_path, args.dataset)

    print("\n" + "="*60)
    print("✅ Pipeline finished – you can now start the API")
    print("   uvicorn backend.services.rgcn.api.router:app --reload --port 8000")
    print("="*60)


if __name__ == "__main__":
    main()
