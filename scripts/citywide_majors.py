"""Per-programme results from the bootstrapped CityU population.

Reads results/citywide_students_seed*.json.gz (written by scripts/citywide.py)
and writes results/explorer/data.json for the interactive explorer.

Assumption: the populations carry no majors, so each student's programme is
inferred from the subject they take most, ignoring GE, PE (PED), language
(LC, CHIN) and service maths/science that most of them take
(MA, PHY, CHEM count only when nothing else does). Ties go to the subject with
the higher-level course. Subjects map to programme families in PROGRAMMES.

Usage: python3 scripts/citywide_majors.py
"""
import gzip
import os
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TAG = os.environ.get("TAG", "")  # e.g. "_compact" for the fewest-days objective
OUT = ROOT / f"results/explorer{TAG}"
SCEN = ("random", "fcfs", "planner")
IGNORE = {"GE", "PED", "LC", "CHIN"}
SERVICE = {"MA", "PHY", "CHEM", "CSCI"}
PROGRAMMES = {
    "CB": "Business (common core)", "AC": "Accountancy", "EF": "Economics & Finance",
    "IS": "Information Systems", "MKT": "Marketing", "MGT": "Management", "MS": "Management Sciences",
    "FB": "Economics & Finance", "CS": "Computer Science", "DSC": "Data Science",
    "MA": "Mathematics", "EE": "Electrical Engineering", "MNE": "Mechanical Engineering",
    "MSE": "Materials Science", "SYE": "Systems Engineering", "BME": "Biomedical Engineering",
    "CA": "Architecture & Civil Engineering", "SEE": "Energy & Environment",
    "CHEM": "Chemistry", "PHY": "Physics", "BMS": "Biomedical Sciences", "NS": "Biomedical Sciences",
    "VM": "Veterinary Medicine", "SM": "Creative Media", "COM": "Media & Communication",
    "EN": "English", "LT": "Linguistics", "CAH": "Chinese & History", "PIA": "Public & International Affairs",
    "SS": "Social & Behavioural Sciences", "LW": "Law", "CSCI": "Mathematics",
}
MIN_STUDENTS = 150  # smaller programme groups are merged into "Other"


def subject(course):
    return course[:len(course) - len(course.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))]


def programme(courses):
    subj = [subject(c) for c in courses if subject(c) not in IGNORE]
    main = [s for s in subj if s not in SERVICE] or subj
    if not main:
        return "First-year general education"
    count = Counter(main)
    top = max(count.values())
    level = {s: max(int(c[len(s)]) for c in courses if subject(c) == s) for s in count}
    best = max((s for s in count if count[s] == top), key=lambda s: (level[s], s))
    return PROGRAMMES.get(best, "Other")


def merge(week):
    """Union of the course masks; None (missing course) counts separately."""
    reg = [0] * 6
    missing = 0
    for masks in week.values():
        if masks is None:
            missing += 1
            continue
        for d in range(6):
            reg[d] |= masks[d]
    return reg, missing


def stats(reg, missing):
    hours = [m.bit_count() for m in reg]
    spans = [(m.bit_length() - ((m & -m).bit_length() - 1)) if m else 0 for m in reg]
    total = sum(hours)
    return {"gap": sum(spans) - total, "long": max(spans), "days": sum(1 for m in reg if m),
            "uneven": sum(abs(5 * hours[d] - total) for d in range(5)) / 25, "miss": missing,
            "hours": total}


def ci(diffs, rng, reps=600):
    means = sorted(statistics.fmean(rng.choices(diffs, k=len(diffs))) for _ in range(reps))
    return [round(statistics.fmean(diffs), 2), round(means[int(.025 * reps)], 2),
            round(means[int(.975 * reps)], 2)]


def grid(week):
    """Compact example timetable: [course, day, start hour, length] blocks."""
    out = []
    for c, masks in sorted(week.items()):
        if masks is None:
            out.append([c, -1, 0, 0])
            continue
        for d, m in enumerate(masks):
            h = 0
            while m >> h:
                if (m >> h) & 1:
                    start = h
                    while (m >> h) & 1:
                        h += 1
                    out.append([c, d, 9 + start, h - start])
                else:
                    h += 1
    return out


def main():
    rng = random.Random(3)
    files = sorted((ROOT / "results").glob(f"citywide_students{TAG}_seed*.json.gz"))
    people = []  # (seed, index, programme, is_real, stats per scenario, weeks)
    for f in files:
        data = json.load(gzip.open(f, "rt"))
        for i, s in enumerate(data["students"]):
            st = {k: stats(*merge(s[k])) for k in SCEN}
            if "actual" in s:
                st["actual"] = stats(*merge(s["actual"]))
            people.append({"seed": data["seed"], "prog": programme(s["c"]), "real": "actual" in s,
                           "st": st, "s": s})
    counts = Counter(p["prog"] for p in people if p["seed"] == people[0]["seed"])
    for p in people:
        if counts[p["prog"]] < MIN_STUDENTS:
            p["prog"] = "Other"
    nseeds = len(files)

    def summary(group):
        out = {"students": round(len(group) / nseeds)}
        for k in SCEN:
            out[k] = {m: round(statistics.fmean(p["st"][k][m] for p in group), 2)
                      for m in ("gap", "long", "days", "uneven", "hours")}
            out[k]["miss_share"] = round(sum(1 for p in group if p["st"][k]["miss"]) / len(group), 3)
            out[k]["gap3_share"] = round(sum(1 for p in group if p["st"][k]["gap"] >= 3) / len(group), 3)
        for m in ("gap", "long", "uneven", "days"):
            out["ci_" + m] = ci([p["st"]["planner"][m] - p["st"]["random"][m] for p in group], rng)
        out["gap_hist"] = {k: [sum(1 for p in group if min(p["st"][k]["gap"], 8) == g) for g in range(9)]
                           for k in SCEN}
        out["days_hist"] = {k: [sum(1 for p in group if p["st"][k]["days"] == d) for d in range(7)]
                            for k in SCEN}
        return out

    progs = defaultdict(list)
    for p in people:
        progs[p["prog"]].append(p)
    result = {"seeds": nseeds, "overall": summary(people), "programmes": {}}
    for name, group in sorted(progs.items(), key=lambda x: -len(x[1])):
        res = summary(group)
        # examples: seed-1 students with 4-7 courses who keep every course in both
        # timetables; first the biggest gap cut (then longest-day cut), then the median
        pool = [p for p in group if p["seed"] == group[0]["seed"] and 4 <= len(p["s"]["c"]) <= 7
                and p["st"]["random"]["miss"] == 0 and p["st"]["planner"]["miss"] == 0]
        if TAG == "_compact":  # biggest cut in days, then in gaps
            pool.sort(key=lambda p: (p["st"]["planner"]["days"] - p["st"]["random"]["days"],
                                     p["st"]["planner"]["gap"] - p["st"]["random"]["gap"]))
        else:
            pool.sort(key=lambda p: (p["st"]["planner"]["gap"] - p["st"]["random"]["gap"],
                                     p["st"]["planner"]["long"] - p["st"]["random"]["long"]))
        examples = []
        for q in (0.0, 0.5):  # the biggest improvement, then a typical student
            if pool:
                p = pool[int(q * (len(pool) - 1))]
                examples.append({"courses": p["s"]["c"], "real": p["real"],
                                 **{k: {"blocks": grid(p["s"][k]), **p["st"][k]} for k in SCEN}})
        res["examples"] = examples
        result["programmes"][name] = res
    real = [p for p in people if p["real"] and p["seed"] == people[0]["seed"]]
    result["real"] = {"students": len(real),
                      **{k: {m: round(statistics.fmean(p["st"][k][m] for p in real), 2)
                             for m in ("gap", "long", "days", "uneven")} for k in ("actual",) + SCEN}}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "data.json").write_text(json.dumps(result, separators=(",", ":")))
    for name, r in result["programmes"].items():
        print(f"{name:34} {r['students']:6}  days {r['random']['days']:.2f} -> {r['planner']['days']:.2f}"
              f"  gaps {r['random']['gap']:.2f} -> {r['planner']['gap']:.2f}"
              f"  longest {r['random']['long']:.1f} -> {r['planner']['long']:.1f}")


if __name__ == "__main__":
    main()
