import os
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent

MODEL_DIR = _BASE / "model"

DATA_DIR = _BASE / "data"

PIPELINE_PATH = str(MODEL_DIR / "fraud_pipeline.pkl")

LOG_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "logs"

LOG_FILE = str(LOG_DIR / "chainbreak.log")

RGCN_ENV_VAR = "RGCN_PIPELINE_PATH"

EPS = 1e-8

SEED = 42

RISK_THRESHOLDS = {
    "Critical": 0.80,
    "High": 0.60,
    "Medium": 0.35,
    "Low": 0.00,
}

DEFAULT_WEIGHTS = {
    "rgcn": 0.55,
    "community": 0.20,
    "traditional": 0.25,
}
