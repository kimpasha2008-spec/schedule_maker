"""Pack results/app_data.json into the single-page app at app/index.html.

Usage: python3 scripts/build_app.py   (after scripts/optimize.py)
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "results/app_data.json"
TEMPLATE = ROOT / "app/template.html"
OUT = ROOT / "app/index.html"


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
              "groups": {str(k): v for k, v in groups.items()}, "students": students}
    html = TEMPLATE.read_text().replace("/*APP_DATA*/null", json.dumps(packed, separators=(",", ":")))
    OUT.write_text(html)
    print(f"{len(students)} students, {len(groups)} groups, {len(meetings)} meetings "
          f"-> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
