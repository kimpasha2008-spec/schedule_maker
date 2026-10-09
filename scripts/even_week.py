"""Even-week planner: OR-Tools CP-SAT with large-neighbourhood search.

Class times stay as published; the planner only picks sections. Each block
(up to 12 students of one cohort who share a timetable) is scored on

  gaps    idle hours between classes on the same day, and
  even    how far each day's class hours are from an even split of the week
          (Mon-Fri each get a fifth of the student's class hours; Saturday
          gets none),

  score = GAP_WEIGHT * 5 * gaps + sum over days |5 * day hours - week hours|
        (in fifths of an hour, so the even split stays in whole numbers).

Objective: sum over blocks of students * score, plus FAIR_WEIGHT times the worst
block's score, so nobody is sacrificed for the average. Hard rules as in
optimize.py: every course, no clashes week by week, seat caps, linked
sections, and Year 1 seat quotas that leave other years' seats free.

Because the score is per block, the search repeatedly frees a neighbourhood
of blocks (those sharing one course), keeps everyone else fixed, and re-solves
that piece to optimality or near it; a change is kept only if it lowers the
total. It starts from the last planner timetable.

It then compares the result with the saved random clash-free and
first-come-first-served registrations (metrics recomputed so the new evenness
measure covers every scenario) and updates results/ for the app.

Usage: python3 scripts/even_week.py [--minutes 20] [--seed 1]
"""
import argparse
import csv
import json
import random
import statistics
import time
from collections import defaultdict
from pathlib import Path

from ortools.sat.python import cp_model

import optimize as o

GAP_WEIGHT = 3  # gaps count 3x: one gap hour costs 15, one hour off the even split 5
FAIR_WEIGHT = 100
NEIGHBOURHOOD = 16  # blocks freed per step
WORST_IN_STEP = 3  # the worst-scoring blocks join every step, so fairness can improve
STEP_SECONDS = 10
WEEKDAYS = 5


def block_score(block, crns, times):
    """GAP_WEIGHT * 5 * gaps + sum |5 * day hours - week hours| on regular-week classes."""
    busy = defaultdict(set)
    for crn in crns:
        for mt in times[crn]:
            if mt.day < 6 and mt.regular:
                busy[mt.day].update(mt.hours())
    hours = [len(busy[d]) for d in range(len(o.DAYS))]
    total = sum(hours)
    gaps = sum(max(busy[d]) - min(busy[d]) + 1 - len(busy[d]) for d in busy if busy[d])
    even = sum(abs(5 * hours[d] - total) for d in range(WEEKDAYS)) + 5 * hours[5]
    return GAP_WEIGHT * 5 * gaps + even


def solve_piece(free, options, times, seats, quota, floor, hint, seconds):
    """Best assignment for the free blocks, given seats and quota left over."""
    m = cp_model.CpModel()
    y, slot_terms = {}, defaultdict(list)
    load, kind_load = defaultdict(list), defaultdict(list)
    for b in free:
        for c in b.courses:
            kinds = options[c]
            groups = o.linked_groups(kinds)
            pick = {g: m.NewBoolVar("") for g in groups} if groups else None
            if pick:
                m.AddExactlyOne(pick.values())
            for kind, secs in kinds.items():
                choice = []
                for s in secs:
                    if seats[s.crn] < b.size:
                        continue
                    v = y[b.id, s.crn] = m.NewBoolVar("")
                    choice.append(v)
                    load[s.crn].append(b.size * v)
                    kind_load[c, kind].append(b.size * v)
                    if pick:
                        m.AddImplication(v, pick[s.group])
                    for mt in times[s.crn]:
                        for h in mt.hours():
                            slot_terms[b.id, mt.day, h].append((v, mt.weeks))
                m.AddExactlyOne(choice)
    for crn, terms in load.items():
        m.Add(sum(terms) <= seats[crn])
    for key, terms in kind_load.items():
        m.Add(sum(terms) <= quota[key])

    hs = list(o.HOURS)
    worst = m.NewIntVar(floor, 10_000, "worst")
    total = []
    for b in free:
        occ = {}
        for d in range(len(o.DAYS)):
            for h in hs:
                terms = slot_terms.get((b.id, d, h), [])
                o.at_most_one_per_week(m, terms)
                occ[d, h] = o.occupancy(m, terms)
        gaps, day_hours = [], []
        for d in range(len(o.DAYS)):
            pre, suf = {}, {}
            for h in hs:
                pre[h] = m.NewBoolVar("")
                if h == hs[0]:
                    m.Add(pre[h] == 0)
                else:
                    m.Add(pre[h] >= pre[h - 1])
                    m.Add(pre[h] >= occ[d, h - 1])
            for h in reversed(hs):
                suf[h] = m.NewBoolVar("")
                if h == hs[-1]:
                    m.Add(suf[h] == 0)
                else:
                    m.Add(suf[h] >= suf[h + 1])
                    m.Add(suf[h] >= occ[d, h + 1])
            for h in hs:
                idle = m.NewBoolVar("")
                m.Add(idle >= pre[h] + suf[h] - 1 - occ[d, h])
                gaps.append(idle)
            day_hours.append(sum(occ[d, h] for h in hs))
        week = sum(day_hours)
        devs = []
        for d in range(WEEKDAYS):
            dev = m.NewIntVar(0, 5 * len(hs) * len(o.DAYS), "")
            m.Add(dev >= 5 * day_hours[d] - week)
            m.Add(dev >= week - 5 * day_hours[d])
            devs.append(dev)
        score = m.NewIntVar(0, 10_000, "")
        m.Add(score == GAP_WEIGHT * 5 * sum(gaps) + sum(devs) + 5 * day_hours[5])
        m.Add(worst >= score)
        total.append(b.size * score)
    m.Minimize(sum(total) + FAIR_WEIGHT * worst)
    for key, v in y.items():
        m.AddHint(v, key in hint)
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = seconds
    solver.parameters.num_workers = 4
    status = solver.Solve(m)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    return {key for key, v in y.items() if solver.Value(v)}


def objective(blocks, assign, times):
    crns = defaultdict(list)
    for bid, crn in assign:
        crns[bid].append(crn)
    scores = {b.id: block_score(b, crns[b.id], times) for b in blocks}
    return sum(b.size * scores[b.id] for b in blocks) + FAIR_WEIGHT * max(scores.values()), scores


def week_evenness(blocks, assign, times):
    """Std of class hours across Mon-Fri per student-week, averaged (hours)."""
    occ = defaultdict(set)
    for bid, crn in assign:
        for mt in times[crn]:
            if mt.day < 6:
                for w in mt.weeks & set(o.TEACHING_WEEKS):
                    occ[bid, w, mt.day].update(mt.hours())
    per_student = []
    for b in blocks:
        weeks = [statistics.pstdev([len(occ[b.id, w, d]) for d in range(WEEKDAYS)])
                 for w in o.TEACHING_WEEKS]
        per_student += [statistics.mean(weeks)] * b.size
    return round(statistics.mean(per_student), 2)


def read_assignment(path, key):
    with open(path, encoding="utf-8") as f:
        return {(int(r[key]), r["crn"]) for r in csv.DictReader(f)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=20, help="search time")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    rng = random.Random(args.seed)

    sections = o.load_sections()
    with open(o.CURRICULA, encoding="utf-8") as f:
        courses = {c for r in csv.DictReader(f) for c in r["courses"].split()}
    options = o.section_options(sections, courses)
    blocks = o.load_blocks(options)
    times = {crn: s.meetings for crn, s in sections.items()}
    quota, _ = o.year1_quota(blocks, options)
    caps = {s.crn: s.cap for kinds in options.values() for secs in kinds.values() for s in secs}
    kind_of = {s.crn: (s.course, s.kind) for kinds in options.values()
               for secs in kinds.values() for s in secs}

    assign = read_assignment(o.OUT_DIR / "planner_block_timetables.csv", "block")
    best, scores = objective(blocks, assign, times)
    print(f"start: objective {best}, worst block {max(scores.values())}", flush=True)

    takers = defaultdict(list)
    for b in blocks:
        for c in b.courses:
            takers[c].append(b)
    weights = [sum(b.size for b in takers[c]) for c in takers]
    deadline = time.time() + 60 * args.minutes
    step = 0
    while time.time() < deadline:
        step += 1
        course = rng.choices(list(takers), weights)[0]
        worst = sorted(blocks, key=lambda b: -scores[b.id])[:WORST_IN_STEP]
        pool = [b for b in takers[course] if b not in worst]
        free = worst + rng.sample(pool, min(NEIGHBOURHOOD - len(worst), len(pool)))
        if len(free) < NEIGHBOURHOOD:  # top up with random other blocks
            others = [b for b in blocks if b not in free]
            free += rng.sample(others, NEIGHBOURHOOD - len(free))
        free_ids = {b.id for b in free}
        fixed = {(bid, crn) for bid, crn in assign if bid not in free_ids}
        seats, left = dict(caps), dict(quota)
        for bid, crn in fixed:
            seats[crn] -= blocks[bid].size
            left[kind_of[crn]] -= blocks[bid].size
        floor = max(scores[b.id] for b in blocks if b.id not in free_ids)
        hint = {(bid, crn) for bid, crn in assign if bid in free_ids}
        piece = solve_piece(free, options, times, seats, left, floor, hint, STEP_SECONDS)
        if piece is None:
            continue
        candidate = fixed | piece
        value, new_scores = objective(blocks, candidate, times)
        if value < best:
            assign, best, scores = candidate, value, new_scores
        if step % 5 == 0:
            print(f"step {step}: objective {best}, worst block {max(scores.values())}", flush=True)
    print(f"done after {step} steps: objective {best}", flush=True)

    # Compare with the saved registrations on the same metrics.
    students = [o.Block(i, b.major, b.english, 1, b.courses)
                for i, b in enumerate(b for b in blocks for _ in range(b.size))]
    summary = json.loads((o.OUT_DIR / "summary.json").read_text())
    saved = {"random": "random_student_timetables.csv", "fcfs": "fcfs_student_timetables.csv",
             "fcfs_no_clash": "fcfs_no_clash_student_timetables.csv"}
    baselines = {}
    for name, path in saved.items():
        if (o.OUT_DIR / path).exists():
            baselines[name] = read_assignment(o.OUT_DIR / path, "student")
            keep = {k: summary[name][k] for k in ("students_missing_a_course", "courses_missing")
                    if k in summary.get(name, {})}
            summary[name] = {**o.metrics(students, baselines[name], times), **keep,
                             "week_evenness_std": week_evenness(students, baselines[name], times)}
    summary["planner"] = {**o.metrics(blocks, assign, times), "students_missing_a_course": 0,
                          "courses_missing": 0,
                          "week_evenness_std": week_evenness(blocks, assign, times)}
    summary["weights"] = {"gaps": GAP_WEIGHT * 5, "even_week": 5, "fairness": FAIR_WEIGHT}
    summary["planner_method"] = (f"even-week CP-SAT with large-neighbourhood search, {step} steps "
                                 f"of {NEIGHBOURHOOD} blocks, {args.minutes:g} min")
    (o.OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    o.write_timetables(o.OUT_DIR / "planner_block_timetables.csv", blocks, assign, times, sections)
    view = o.student_view(students, baselines, blocks, assign, times, sections)
    app = {"summary": summary, "days": o.DAYS, "hours": [o.HOURS[0], o.HOURS[-1]], "students": view}
    (o.OUT_DIR / "app_data.json").write_text(json.dumps(app, separators=(",", ":")))

    cols = [k for k in ("random", "fcfs", "fcfs_no_clash", "planner") if k in summary]
    print(f"\n{'metric':52}" + "".join(f"{c[:13]:>14}" for c in cols))
    for k in summary["planner"]:
        print(f"{k:52}" + "".join(f"{summary[c].get(k, ''):>14}" for c in cols))


if __name__ == "__main__":
    main()
