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
