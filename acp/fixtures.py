"""Synthetic fixtures, fixed seed 41, no network or vendor data."""
import json
import random
from pathlib import Path
from .prices import DEFAULT

MISSIONS = ("research", "triage", "summarise", "index", "expensive-search", "expensive-planning")

def generate_rows():
    rng = random.Random(41)
    rows = []
    for mission in MISSIONS:
        for index in range(20):
            expensive = mission.startswith("expensive")
            rows.append(dict(agent=("alpha", "beta", "gamma")[index % 3], mission=mission,
                tokens_in=(2000000 if mission == "expensive-planning" else 1000000) if expensive else rng.randint(100, 2000),
                tokens_out=rng.randint(100, 1000), api_calls=rng.randint(1, 4), wall_s=float(rng.randint(10, 100)),
                outcome=None if index % 5 == 0 else ("failed" if index % 4 == 0 else "success"),
                ts=f"2026-09-30T00:{len(rows):02d}:00Z"))
    # Valid ISO timestamps spanning two hours.
    for i, row in enumerate(rows):
        row["ts"] = f"2026-09-30T{i // 60:02d}:{i % 60:02d}:00Z"
    return rows

def write_fixtures(out):
    directory = Path(out)
    directory.mkdir(parents=True, exist_ok=True)
    runs = "# SYNTHETIC run logs; seed 41; no real measured usage\n"
    runs += "".join(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in generate_rows())
    (directory / "runs.jsonl").write_text(runs, encoding="utf-8", newline="\n")
    prices = dict(DEFAULT, _header="SYNTHETIC fixture price table")
    (directory / "prices.json").write_text(json.dumps(prices, sort_keys=True, indent=2) + "\n", encoding="utf-8", newline="\n")
