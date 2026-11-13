"""Pack results/explorer/data.json into app/explorer.html (the interactive explorer).

Usage: python3 scripts/citywide_majors.py && python3 scripts/build_explorer.py
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAG = os.environ.get("TAG", "")


def drop_fcfs(x):
    """The explorer compares the planner with today's random picks only."""
    if isinstance(x, dict):
        return {k: drop_fcfs(v) for k, v in x.items() if k != "fcfs"}
    return [drop_fcfs(v) for v in x] if isinstance(x, list) else x


data = json.dumps(drop_fcfs(json.loads((ROOT / f"results/explorer{TAG}/data.json").read_text())),
                  separators=(",", ":"))
html = (ROOT / f"app/explorer{TAG}_template.html").read_text().replace("/*DATA*/null", data)
(ROOT / f"app/explorer{TAG}.html").write_text(html)
print(f"app/explorer{TAG}.html ({len(html) // 1024} KB)")
