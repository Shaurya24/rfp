"""Create the SQLite database and seed sample evaluation criteria.

Usage:  python scripts/seed_db.py [--reset]
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src import db  # noqa: E402

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="re-seed the default criteria")
    args = ap.parse_args()
    db.init_db(reset_criteria=args.reset)
    print(f"Database ready at {db.DEFAULT_DB}")
    for c in db.get_criteria(active_only=False):
        print(f"  [{c['criterion_id']}] {c['name']:<24} weight={c['weight']:>5}  max={c['max_score']}  active={c['is_active']}")
