"""Pack results/app_data.json into the single-page app at app/index.html.

Usage: python3 scripts/build_app.py   (after scripts/optimize.py)
"""
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "results/app_data.json"
TEMPLATE = ROOT / "app/template.html"
OUT = ROOT / "app/index.html"


def background_by_building():
    """Other students in each first-year building, per weekday and hour 09-21."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import optimize as o
    import even_week as e
    sections = o.load_sections()
    with open(o.CURRICULA, encoding="utf-8") as f:
        courses = {c for r in csv.DictReader(f) for c in r["courses"].split()}
    options = o.section_options(sections, courses)
    blocks = o.load_blocks(options)
    _, report = o.year1_quota(blocks, options)
    times = {crn: s.meetings for crn, s in sections.items()}
    bg = e.background_load(sections, options, report, times)
    used = {e.building_of(mt) for kinds in options.values() for secs in kinds.values()
            for sec in secs for mt in sec.meetings if mt.venues}
    return {k: [[bg.get((k, d, h), 0) for h in range(9, 22)] for d in range(5)] for k in sorted(used)}


def main():
    data = json.loads(DATA.read_text())
    meetings, index = [], {}

    def ids(week):
        out = []
        for m in week:
            key = json.dumps(m)
            if key not in index:
                index[key] = len(meetings)
                meetings.append(m)
            out.append(index[key])
        return out

    majors = sorted({s["major"] for s in data["students"]})
    groups, students = {}, []
    for s in data["students"]:
        groups.setdefault(s["group"], ids(s["optimized"]))
        students.append({"m": majors.index(s["major"]), "e": s["english"], "c": s["courses"],
                         "r": ids(s["random"]), "f": ids(s["fcfs"]),
                         "n": ids(s["fcfs_no_clash"]), "g": s["group"]})
    packed = {"summary": data["summary"], "majors": majors, "meetings": meetings,
              "background": background_by_building(),
              "groups": {str(k): v for k, v in groups.items()}, "students": students}
    html = TEMPLATE.read_text().replace("/*APP_DATA*/null", json.dumps(packed, separators=(",", ":")))
    OUT.write_text(html)
    print(f"{len(students)} students, {len(groups)} groups, {len(meetings)} meetings "
          f"-> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
