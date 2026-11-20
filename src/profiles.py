"""Which synthetic stall to build / analyse, and where its files live.

    STALL_PROFILE=chai  (default)  campus chai stall, 26 items        -> data/raw, data/answer_key, eval/
    STALL_PROFILE=redi             real redi menu (photo), 62 items   -> data/redi/..., eval/redi/

Both stalls share the campus, calendar, weather and customers; only the menu
(and what follows from it: combos, remarks, suppliers) differs, so their
evaluation scores can be compared directly.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFILE = os.environ.get("STALL_PROFILE", "chai").strip().lower()
if PROFILE not in ("chai", "redi"):
    raise ValueError(f"STALL_PROFILE must be 'chai' or 'redi', got {PROFILE!r}")

DATA = ROOT / "data" if PROFILE == "chai" else ROOT / "data" / PROFILE
RAW, KEY = DATA / "raw", DATA / "answer_key"
EVAL_OUT = ROOT / "eval" if PROFILE == "chai" else ROOT / "eval" / PROFILE


def load_env(path=ROOT / ".env"):
    """Read KEY=VALUE lines from the project's .env file (API keys) into the environment.
    Values already set in the shell win. .env is git-ignored, so keys are never committed."""
    try:
        lines = Path(path).read_text().splitlines()
    except OSError:
        return
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.replace("export ", "").strip()
        os.environ.setdefault(k, v.strip().strip('"').strip("'"))


load_env()
