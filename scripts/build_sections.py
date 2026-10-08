"""Flatten the CityU Schedule Builder catalogue JSON into data/sections.csv.

Source: https://cityu-schedule.xmzr.dev/courses.json (a public mirror of the AIMS
Master Class Schedule), saved under data/raw/. One output row per weekly meeting:
a section that meets on several days, or in several time/room blocks, gets
several rows sharing the same CRN.

Usage: python3 scripts/build_sections.py [raw_json] [out_csv]
"""
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data/raw/xmzr_courses_semA_2026-27_scraped_2026-08-23.json"
OUT = ROOT / "data/sections.csv"
CAPACITY = ROOT / "data/cityuhk_course_offerings_capacity.csv"

# First letter of the AIMS section code. C/T/L/S are CityU's standard
# lecture/tutorial/lab/seminar prefixes; the rest are rare and left generic.
SECTION_TYPES = {"C": "lecture", "T": "tutorial", "L": "lab", "S": "seminar"}
DAY_CODES = "MTWRFSU"  # Mon..Sun, AIMS uses R for Thursday and U for Sunday
TIME_RE = re.compile(r"^(\d\d:\d\d) - (\d\d:\d\d)$")

FIELDS = [
    "term", "subject", "course", "title", "credits", "level", "crn", "section",
    "type", "day", "start", "end", "venue", "instructor", "date_from", "date_to",
    "cap", "avail", "restrict", "note",
]


def meeting_rows(day_field, time_field):
    """Yield (day, start, end, note) for one AIMS meeting entry."""
    m = TIME_RE.match(time_field)
    start, end = m.groups() if m else ("", "")
    if not day_field and not time_field:
        yield "", "", "", "no fixed time (TBA / arranged)"
    elif day_field and all(ch in DAY_CODES for ch in day_field):
        for day in day_field:
            yield day, start, end, ""
    else:
        yield "", start, end, f"unparsed day field: {day_field!r}"


def main(raw=RAW, out=OUT):
    data = json.loads(Path(raw).read_text(encoding="utf-8"))
    term = data["term"]
    rows = []
    for c in data["courses"]:
        for s in c["sections"]:
            for day_field, time_field, venue, instructor, dates in s["m"]:
                date_from, _, date_to = dates.partition(" - ")
                for day, start, end, note in meeting_rows(day_field, time_field):
                    rows.append({
                        "term": term, "subject": c["subj"], "course": c["code"],
                        "title": c["title"], "credits": c["cu"], "level": c["level"],
                        "crn": s["crn"], "section": s["sec"],
                        "type": SECTION_TYPES.get(s["sec"][:1], "other"),
                        "day": day, "start": start, "end": end, "venue": venue,
                        "instructor": instructor, "date_from": date_from,
                        "date_to": date_to, "cap": s["cap"], "avail": s["avail"],
                        "restrict": "; ".join(s.get("restrict", [])), "note": note,
                    })
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    n_sections = sum(len(c["sections"]) for c in data["courses"])
    print(f"{term} (scraped {data['scraped']}): {len(data['courses'])} courses, "
          f"{n_sections} sections, {len(rows)} meeting rows -> {out}")
    validate(data)


def validate(data):
    """Check that each course's sections add up to the AIMS course-level Cap.

    Students take one section per type (e.g. one lecture + one tutorial), so the
    caps are compared per section type; a course matches if any type sums to Cap.
    """
    if not CAPACITY.exists():
        return
    with open(CAPACITY, encoding="utf-8-sig") as f:
        course_cap = {r["course_code"]: int(r["cap"]) for r in csv.DictReader(f)}
    matched, mismatched, missing = 0, [], []
    for c in data["courses"]:
        if c["code"] not in course_cap:
            missing.append(c["code"])
            continue
        by_type = defaultdict(int)
        for s in c["sections"]:
            by_type[s["sec"][:1]] += int(s["cap"] or 0)
        if course_cap[c["code"]] in by_type.values():
            matched += 1
        else:
            mismatched.append((c["code"], course_cap[c["code"]], dict(by_type)))
    print(f"Validation vs {CAPACITY.name}: {matched} courses match, "
          f"{len(mismatched)} differ, {len(missing)} not in capacity file")
    for code, cap, by_type in mismatched[:10]:
        print(f"  {code}: course cap {cap}, section caps by type {by_type}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
