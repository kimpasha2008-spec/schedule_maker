"""Turn results/citywide_summary.json into the report's data files.

Writes results/report/{scenarios,effects,real,population}.json, each
{"rows": [...], "meta": [...]}: averages over the bootstrap populations, with
the lowest and highest population value, and the paired-bootstrap intervals.

Usage: python3 scripts/citywide_report.py
"""
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "results/citywide_summary.json"
OUT = ROOT / "results/report"
LABELS = {"random": "Random clash-free (today)", "fcfs": "First come, best pick",
          "planner": "Planner", "actual": "Real timetables"}
METRICS = ["gap_hours", "unevenness", "longest_day", "days_on_campus", "saturday_hours",
           "share_with_3h_plus_gaps", "share_with_no_gaps", "worst_10pct_gap_hours",
           "share_missing_a_course"]
LOAD = ["peak_students_in_class", "hourly_load_std", "building_peak_sum"]


def avg(values):
    return round(statistics.fmean(values), 3)


def main():
    runs = json.loads(SRC.read_text())
    code = Path(__file__).read_text()
    meta = [{"label": "citywide_report.py", "value": code, "type": "code", "lang": "python"},
            {"label": "Input", "value": "results/citywide_summary.json from scripts/citywide.py"},
            {"label": "Populations", "value": str(len(runs))}]
    OUT.mkdir(exist_ok=True)

    rows = []
    for key in ("random", "fcfs", "planner"):
        row = {"scenario": key, "label": LABELS[key]}
        for m in METRICS + LOAD:
            vals = [r["all_students"][key][m] for r in runs]
            row[m], row[m + "_min"], row[m + "_max"] = avg(vals), min(vals), max(vals)
        rows.append(row)
    write("scenarios", rows, meta)

    rows = []
    for comp, field in (("planner_vs_random", "Planner vs random (all students)"),
                        ("planner_vs_fcfs", "Planner vs first come (all students)"),
                        ("real_planner_vs_actual", "Planner vs real timetables (real students)")):
        for m in runs[0][comp]:
            vals = [r[comp][m] for r in runs]
            rows.append({"comparison": comp, "label": field, "metric": m,
                         "change": avg(v[0] for v in vals),
                         "lo": min(v[1] for v in vals), "hi": max(v[2] for v in vals)})
    write("effects", rows, meta)

    rows = []
    for key in ("actual", "fcfs", "planner"):
        row = {"scenario": key, "label": LABELS[key]}
        for m in METRICS:
            row[m] = avg(r["real_students"][key][m] for r in runs)
        rows.append(row)
    write("real", rows, meta)

    rows = [{"seed": r["seed"], **r["population"]} for r in runs]
    write("population", rows, meta)
    print(f"{len(runs)} populations -> {OUT}")


def write(name, rows, meta):
    (OUT / f"{name}.json").write_text(json.dumps({"rows": rows, "meta": meta}, indent=1) + "\n")


if __name__ == "__main__":
    main()
