"""Turn transcribed real timetables into anonymous section lists.

Input: data/real_timetables_transcribed.txt, one student per line, read by hand
from the screenshots students shared (CityUHK Mobile app or AIMS/banweb).
Each token is either
  CODE-SEC        a fully visible class code, e.g. CB2203-T08
  COURSE@DayHH    a code the app cut off ("MA1508-"), placed by its weekday
                  (M T W R F S) and start hour, e.g. MA1508@T09
Optical character recognition was tried first and dropped: orange-on-yellow
codes and phone photos of screens were read wrongly too often.

Output: data/real_students.csv (student, crn, course, section). Students get
running ids only; no names, student numbers or images are kept anywhere.

Usage: python3 scripts/read_screenshots.py
"""
import csv
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECTIONS = ROOT / "data/sections.csv"
SOURCE = ROOT / "data/real_timetables_transcribed.txt"
OUT = ROOT / "data/real_students.csv"
CODE = re.compile(r"^([A-Z]{2,4}\d{4}[A-Z]?)-([A-Z][A-Z0-9]{1,2})$")
SLOT = re.compile(r"^([A-Z]{2,4}\d{4}[A-Z]?)@([MTWRFS])(\d{2})$")


def load():
    by_code, starts = {}, defaultdict(set)
    with open(SECTIONS, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            by_code[r["course"], r["section"]] = r["crn"]
            if r["day"] and r["start"]:
                starts[r["course"], r["day"], int(r["start"][:2])].add((r["section"], r["crn"]))
    return by_code, starts


def resolve(tokens, by_code, starts):
    """CRNs for one student; slot tokens are matched after the explicit codes."""
    found, slots, missing = {}, [], []
    for t in tokens:
        m = CODE.match(t)
        if m and (m.group(1), m.group(2)) in by_code:
            found[m.group(1), m.group(2)] = by_code[m.group(1), m.group(2)]
        elif SLOT.match(t):
            slots.append(SLOT.match(t).groups())
        else:
            missing.append(t)
    for course, day, hour in slots:
        cands = starts.get((course, day, int(hour)), set())
        if not cands:
            missing.append(f"{course}@{day}{hour}")
            continue
        taken = {sec for c, sec in found if c == course}
        if any(sec in taken for sec, _ in cands):
            continue  # this slot belongs to a section already listed
        kinds = {sec[0] for sec in taken}
        groups = {sec[1] for sec in taken if len(sec) == 3 and sec[1].isalpha()}
        # prefer a section type the student doesn't have yet, then the
        # lecture/tutorial letter group they already belong to
        best = sorted(cands, key=lambda x: (x[0][0] in kinds,
                                            not (len(x[0]) == 3 and x[0][1] in groups), x[0]))
        sec, crn = best[0]
        found[course, sec] = crn
    return found, missing


def main():
    by_code, starts = load()
    lines = [ln.split() for ln in SOURCE.read_text().splitlines()
             if ln.strip() and not ln.startswith("#")]
    rows, unresolved = [], []
    for i, tokens in enumerate(lines, 1):
        found, missing = resolve(tokens, by_code, starts)
        unresolved += missing
        for (course, sec), crn in sorted(found.items()):
            rows.append((f"S{i:03d}", crn, course, sec))
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["student", "crn", "course", "section"])
        w.writerows(rows)
    print(f"{len(lines)} students, {len(rows)} sections -> {OUT}")
    if unresolved:
        print(f"{len(unresolved)} tokens not matched to the Sem A catalogue: {' '.join(unresolved)}")


if __name__ == "__main__":
    main()
