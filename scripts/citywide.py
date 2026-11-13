"""Scale the real timetables to every CityU undergraduate and re-run the model.

1. Population (bootstrap with demand matching). The real students (read from
   the screenshots, data/real_students.csv) keep their own courses and
   sections. Further students are made by drawing a real student at random
   (with replacement) and copying the shape of their timetable: each of their
   courses is kept or swapped for another course of the same subject and
   level (e.g. CB2xxx for CB2201), with probability proportional to the seats
   that course still has to fill in the AIMS Sem A 2026/27 undergraduate
   enrolment. A course is only added if it still has a seat that fits the
   student's week, and the student takes a random such section, so everyone
   in the population has a real, clash-free timetable. Students are added
   until every course's enrolment is used up.
2. Scenarios on that population, all with real section times and seat caps:
   - random:   the timetables the population was built with: each student a
               random clash-free mix of open sections (the real students keep
               their real ones). The real screenshots look like this.
   - fcfs:     everyone registers again in random order and takes the best
               clash-free mix still open (perfect first-come-first-served);
               late students can miss out on a course.
   - planner:  starting from `random`, sections are re-assigned for everyone,
               worst timetables first, with seat swaps between students, also
               spreading each building's load over the day.
3. Uncertainty: the pipeline runs on several bootstrap populations (seeds);
   inside each, a paired bootstrap over students gives 95% intervals.

Usage: python3 scripts/citywide.py [--replicates 3] [--planner-minutes 6]
Writes results/citywide_summary.json.
"""
import argparse
import csv
import json
import random
import statistics
import sys
import time
from collections import defaultdict
from itertools import product
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import optimize as o  # noqa: E402
from even_week import building_of  # noqa: E402

ROOT = o.ROOT
REAL = ROOT / "data/real_students.csv"
OUT = ROOT / "results"
KEEP_AFFINITY = 4  # a drawn student's own course counts 4x when picking its replacement
CROSS_SUBJECT = 0.1  # weight of same-level courses in other subjects
MIN_SHAPE = 0.75  # a clone keeps at least 75% as many courses as its donor
TRIES = 6  # course picks tried per timetable slot before giving the slot up
MISS = 150  # penalty per course left out
GAP_W = 15  # one idle hour between classes costs as much as 3 hours of uneven week
LOAD_SCALE = 1000  # planner: an hour in a building with 1,000 students in class costs 1
MAX_COMBOS = 600
METRICS = ("gap_hours", "unevenness", "longest_day", "days_on_campus", "missing_courses")


# ---------------------------------------------------------------- options

class Opt:
    """One way to take a course: a lecture/tutorial/lab section combination."""
    __slots__ = ("course", "crns", "slots", "reg", "sig", "bld")

    def __init__(self, course, secs):
        self.course = course
        self.crns = tuple(s.crn for s in secs)
        slots = defaultdict(int)
        reg = [0] * 6
        bld = []
        for s in secs:
            for mt in s.meetings:
                wm = sum(1 << w for w in mt.weeks)
                for h in mt.hours():
                    if 9 <= h <= 22:
                        slots[mt.day, h] |= wm
                        if mt.regular:
                            reg[mt.day] |= 1 << (h - 9)
                            if mt.day < 5 and mt.venues:
                                bld.append((building_of(mt), mt.day, h))
        self.slots = dict(slots)
        self.reg = tuple(reg)
        self.bld = tuple(bld)
        self.sig = (self.reg, tuple(sorted(self.slots.items())), self.bld)


def build_options(sections, courses):
    opts = {}
    raw = o.section_options(sections, courses)
    for c, kinds in raw.items():
        groups = o.linked_groups(kinds)
        combos = []
        if groups:
            for g in groups:
                combos += product(*[[s for s in secs if s.group == g] for secs in kinds.values()])
        else:
            combos = list(product(*kinds.values()))
        if len(combos) > MAX_COMBOS:
            combos = random.Random(c).sample(combos, MAX_COMBOS)
        opts[c] = [Opt(c, combo) for combo in combos]
    return opts


def score_masks(reg):
    hours = [m.bit_count() for m in reg]
    total_h = sum(hours)
    gaps = 0
    for m in reg:
        if m:
            gaps += m.bit_length() - ((m & -m).bit_length() - 1) - m.bit_count()
    even = sum(abs(5 * hours[d] - total_h) for d in range(5)) + 5 * hours[5]
    return GAP_W * gaps + even


def timetable_score(chosen):
    reg = [0] * 6
    for op in chosen.values():
        if op is not None:
            for d in range(6):
                reg[d] |= op.reg[d]
    return score_masks(reg)


def clashes(op, others):
    for op2 in others:
        if op2 is None:
            continue
        for k, wm in op.slots.items():
            if op2.slots.get(k, 0) & wm:
                return True
    return False


class Seats:
    """Seats left per section, who holds them, and students per building-hour."""

    def __init__(self, sections):
        self.left = {crn: s.cap for crn, s in sections.items()}
        self.holders = defaultdict(set)
        self.load = defaultdict(int)

    def ok(self, op):
        return all(self.left[c] > 0 for c in op.crns)

    def take(self, sid, op):
        for c in op.crns:
            self.left[c] -= 1
            self.holders[c].add(sid)
        for k in op.bld:
            self.load[k] += 1

    def give(self, sid, op):
        for c in op.crns:
            self.left[c] += 1
            self.holders[c].discard(sid)
        for k in op.bld:
            self.load[k] -= 1

    def take_all(self, sid, chosen):
        for op in chosen.values():
            if op is not None:
                self.take(sid, op)

    def give_all(self, sid, chosen):
        for op in chosen.values():
            if op is not None:
                self.give(sid, op)


def candidates(course, options, seats, held=None):
    """Open options of a course, one per distinct timing and building."""
    seen, out = set(), []
    for op in options[course]:
        if op.sig in seen:
            continue
        if op is held or seats.ok(op):
            seen.add(op.sig)
            out.append(op)
    return out


# ---------------------------------------------------------------- population

def level_class(course):
    subject = course[:len(course) - len(course.lstrip("ABCDEFGHIJKLMNOPQRSTUVWXYZ"))]
    return subject, course[len(subject):len(subject) + 1]


def load_real(options):
    real = defaultdict(list)
    with open(REAL, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            real[r["student"]].append((r["course"], r["crn"]))
    out = []
    for sid in sorted(real):
        crns = {crn for c, crn in real[sid] if c in options}
        chosen = {}
        for c in sorted({c for c, _ in real[sid] if c in options}):
            # the option holding most of the student's sections (a section
            # missing from a screenshot, or added after the catalogue was
            # scraped with no seats in it, leaves an option partly matched)
            best = max(options[c], key=lambda op: len(set(op.crns) & crns))
            chosen[c] = best if set(best.crns) & crns else None
        if chosen:
            out.append((chosen, crns))
    return out


def demand_targets(options):
    with open(o.CAPACITY, encoding="utf-8-sig") as f:
        rows = {r["course_code"]: r for r in csv.DictReader(f)}
    target = {}
    for c in options:
        r = rows.get(c)
        if r and r["open_to_undergrads"] == "Y" and "B" in r["level_codes"].split():
            target[c] = int(r["enrolled_est"])
    return target


def make_population(real, target, options, sections, seed):
    """Real students first, then bootstrap clones until course demand runs out.

    Returns (courses per student, starting timetables, seats, info).
    """
    rng = random.Random(seed)
    residual = dict(target)
    seats = Seats(sections)
    by_class, by_level = defaultdict(list), defaultdict(list)
    for c in target:
        subject, level = level_class(c)
        by_class[subject, level].append(c)
        by_level[level].append(c)
    everything = list(target)
    pop, plans = [], []
    for chosen, _ in real:
        pop.append(sorted(chosen))
        plans.append(dict(chosen))
        seats.take_all(len(plans) - 1, chosen)
        for c in chosen:
            residual[c] -= 1
    stall = 0
    while sum(max(v, 0) for v in residual.values()) > 0 and stall < 500:
        donor = list(rng.choice(real)[0])
        rng.shuffle(donor)
        mine = {}
        for c in donor:
            subject, level = level_class(c)
            pool = [x for x in by_class[subject, level] if x not in mine]
            weights = [max(residual[x], 0) * (KEEP_AFFINITY if x == c else 1) for x in pool]
            other = [x for x in by_level[level] if x not in mine and level_class(x)[0] != subject]
            weights += [CROSS_SUBJECT * max(residual[x], 0) for x in other]
            pool += other
            if sum(weights) <= 0:  # nothing left at this level: any course with seats to fill
                pool = [x for x in everything if x not in mine]
                weights = [max(residual[x], 0) for x in pool]
            for _ in range(TRIES):
                if sum(weights) <= 0:
                    break
                i = rng.choices(range(len(pool)), weights)[0]
                fits = [op for op in candidates(pool[i], options, seats)
                        if not clashes(op, mine.values())]
                if fits:
                    mine[pool[i]] = rng.choice(fits)
                    break
                weights[i] = 0
        if len(mine) < max(1, round(MIN_SHAPE * len(donor))):
            stall += 1  # the seats left can't make a timetable of this shape
            continue
        stall = 0
        pop.append(sorted(mine))
        plans.append(mine)
        seats.take_all(len(plans) - 1, mine)
        for c in mine:
            residual[c] -= 1
    filled = sum(target[c] - max(residual[c], 0) for c in target)
    info = {"students": len(pop), "real_students": len(real),
            "target_enrolments": sum(target.values()),
            "simulated_enrolments": sum(len(p) for p in pop),
            "demand_covered": round(filled / sum(target.values()), 4),
            "courses": len(target),
            "mean_courses_per_student": round(statistics.mean(len(p) for p in pop), 2),
            "real_mean_courses_per_student": round(statistics.mean(len(c) for c, _ in real), 2)}
    return pop, plans, seats, info


# ---------------------------------------------------------------- registration

def total(chosen, load=None):
    s = timetable_score(chosen) + MISS * sum(1 for v in chosen.values() if v is None)
    if load is not None:
        s += sum(load[k] for op in chosen.values() if op is not None for k in op.bld) / LOAD_SCALE
    return s


def best_response(courses, options, seats, rng, start=None, rounds=3, load=None):
    """Locally best clash-free timetable for one student given the open seats."""
    held = start or {}
    cands = {c: candidates(c, options, seats, held.get(c)) for c in courses}
    if start:
        chosen = dict(start)
    else:
        chosen = {c: None for c in courses}
        for c in sorted(courses, key=lambda c: len(cands[c])):
            best, best_s = None, None
            for op in cands[c]:
                if clashes(op, chosen.values()):
                    continue
                chosen[c] = op
                s = total(chosen, load)
                if best_s is None or s < best_s:
                    best, best_s = op, s
            chosen[c] = best
    cur = total(chosen, load)
    for _ in range(rounds):
        improved = False
        order = list(courses)
        rng.shuffle(order)
        for c in order:
            keep = chosen[c]
            others = [v for k, v in chosen.items() if k != c]
            for op in cands[c]:
                if op is keep or clashes(op, others):
                    continue
                chosen[c] = op
                s = total(chosen, load)
                if s < cur:
                    cur, keep, improved = s, op, True
            chosen[c] = keep
        if not improved:
            break
    return chosen, cur


def register(pop, options, sections, seed):
    """First come, first served: each student takes the best open timetable."""
    rng = random.Random(seed)
    seats = Seats(sections)
    order = list(range(len(pop)))
    rng.shuffle(order)
    plan = [None] * len(pop)
    for sid in order:
        chosen, _ = best_response(pop[sid], options, seats, rng)
        seats.take_all(sid, chosen)
        plan[sid] = chosen
    return plan


def plan_all(start, options, seats, seed, minutes):
    """Improve everyone's timetables: worst first, own re-plans plus seat swaps."""
    rng = random.Random(seed)
    plan = [dict(p) for p in start]
    score = [total(p, seats.load) for p in plan]
    deadline = time.time() + 60 * minutes
    passes = 0
    while time.time() < deadline:
        passes += 1
        moved = 0
        for sid in sorted(range(len(plan)), key=lambda i: -score[i]):
            if time.time() > deadline:
                break
            mine = plan[sid]
            seats.give_all(sid, mine)
            before = total(mine, seats.load)
            new, s = best_response(list(mine), options, seats, rng, start=mine, load=seats.load)
            if s < before - 1e-9:
                mine = new
                moved += 1
            elif total(mine) >= 3 * GAP_W and try_swap(sid, mine, plan, options, seats, rng):
                mine = plan[sid]
                moved += 1
            seats.take_all(sid, mine)
            plan[sid] = mine
            score[sid] = total(mine, seats.load)
        print(f"  planner pass {passes}: {moved} students improved, mean score "
              f"{statistics.mean(timetable_score(p) for p in plan):.1f}", flush=True)
        if moved == 0:
            break
    return plan


def try_swap(sid, mine, plan, options, seats, rng):
    """Let `sid` take a full section if one holder can move elsewhere for less.

    `sid` holds no seats while this runs; on success plan[sid] and the
    holder's timetable are updated (the holder's seats are taken here).
    """
    base = total(mine)
    for c in rng.sample(list(mine), len(mine)):
        others = [v for k, v in mine.items() if k != c]
        for op in options[c]:
            if op is mine[c] or clashes(op, others):
                continue
            trial = dict(mine)
            trial[c] = op
            gain = base - total(trial)
            full = [crn for crn in op.crns if seats.left[crn] <= 0]
            if gain <= 0 or len(full) != 1 or not seats.holders[full[0]]:
                continue
            for t in rng.sample(sorted(seats.holders[full[0]]), min(4, len(seats.holders[full[0]]))):
                theirs = plan[t]
                old = total(theirs)
                seats.give_all(t, theirs)
                seats.left[full[0]] -= 1  # keep the seat for sid
                new, s = best_response(list(theirs), options, seats, rng, rounds=2)
                seats.left[full[0]] += 1
                if s - old < gain and not any(x is not None and full[0] in x.crns
                                              for x in new.values()):
                    seats.take_all(t, new)
                    plan[t] = new
                    plan[sid] = trial
                    return True
                seats.take_all(t, theirs)
    return False


# ---------------------------------------------------------------- metrics

def per_student(chosen):
    reg = [0] * 6
    for op in chosen.values():
        if op is not None:
            for d in range(6):
                reg[d] |= op.reg[d]
    return student_row(reg, sum(1 for v in chosen.values() if v is None))


def student_row(reg, missing):
    hours = [m.bit_count() for m in reg]
    spans = [(m.bit_length() - ((m & -m).bit_length() - 1)) if m else 0 for m in reg]
    total_h = sum(hours)
    return {"gap_hours": sum(spans) - total_h,
            "unevenness": round(sum(abs(5 * hours[d] - total_h) for d in range(5)) / 25, 3),
            "longest_day": max(spans),
            "days_on_campus": sum(1 for m in reg if m),
            "saturday_hours": hours[5],
            "missing_courses": missing}


def actual_rows(real, times):
    """The real students' own timetables, every section they took (regular weeks)."""
    rows = []
    for _, crns in real:
        reg = [0] * 6
        for crn in crns:
            for mt in times[crn]:
                if mt.day < 6 and mt.regular:
                    for h in mt.hours():
                        if 9 <= h <= 22:
                            reg[mt.day] |= 1 << (h - 9)
        rows.append(student_row(reg, 0))
    return rows


def load_stats(plans):
    load = defaultdict(int)
    for chosen in plans:
        for op in chosen.values():
            if op is not None:
                for k in op.bld:
                    load[k] += 1
    campus = defaultdict(int)
    peaks = defaultdict(int)
    for (b, d, h), n in load.items():
        campus[d, h] += n
        peaks[b] = max(peaks[b], n)
    hourly = [campus.get((d, h), 0) for d in range(5) for h in range(9, 22)]
    return {"peak_students_in_class": max(hourly),
            "hourly_load_std": round(statistics.pstdev(hourly), 1),
            "building_peak_sum": sum(peaks.values()),
            "building_peaks": dict(sorted(peaks.items(), key=lambda x: -x[1])[:8])}


def summarize(rows):
    out = {k: round(statistics.mean(r[k] for r in rows), 3)
           for k in ("gap_hours", "unevenness", "longest_day", "days_on_campus",
                     "saturday_hours", "missing_courses")}
    gaps = sorted(r["gap_hours"] for r in rows)
    out["share_with_3h_plus_gaps"] = round(sum(1 for g in gaps if g >= 3) / len(rows), 4)
    out["share_with_no_gaps"] = round(sum(1 for g in gaps if g == 0) / len(rows), 4)
    out["worst_10pct_gap_hours"] = round(statistics.mean(gaps[-max(1, len(gaps) // 10):]), 2)
    out["share_missing_a_course"] = round(sum(1 for r in rows if r["missing_courses"]) / len(rows), 4)
    return out


def paired_ci(a, b, key, reps=1000, seed=7):
    """Mean of b - a with a 95% bootstrap interval (resampling students)."""
    rng = random.Random(seed)
    d = [y[key] - x[key] for x, y in zip(a, b)]
    means = sorted(statistics.fmean(rng.choices(d, k=len(d))) for _ in range(reps))
    return [round(statistics.fmean(d), 3), round(means[int(0.025 * reps)], 3),
            round(means[int(0.975 * reps)], 3)]


# ---------------------------------------------------------------- main

def run(seed, real, options, sections, times, target, minutes):
    t0 = time.time()
    pop, rnd, seats, info = make_population(real, target, options, sections, seed)
    print(f"[seed {seed}] population ({time.time() - t0:.0f}s): {info}", flush=True)
    fcfs = register(pop, options, sections, seed)
    print(f"[seed {seed}] first come done ({time.time() - t0:.0f}s)", flush=True)
    planner = plan_all(rnd, options, seats, seed, minutes)
    print(f"[seed {seed}] planner done ({time.time() - t0:.0f}s)", flush=True)
    plans = {"random": rnd, "fcfs": fcfs, "planner": planner}
    rows = {k: [per_student(p) for p in v] for k, v in plans.items()}
    n = info["real_students"]
    actual = actual_rows(real, times)
    return {
        "seed": seed,
        "population": info,
        "all_students": {k: summarize(rows[k]) | load_stats(plans[k]) for k in plans},
        "planner_vs_random": {k: paired_ci(rows["random"], rows["planner"], k) for k in METRICS},
        "planner_vs_fcfs": {k: paired_ci(rows["fcfs"], rows["planner"], k) for k in METRICS},
        "real_students": {"actual": summarize(actual),
                          **{k: summarize(v[:n]) for k, v in rows.items() if k != "random"}},
        "real_planner_vs_actual": {k: paired_ci(actual, rows["planner"][:n], k)
                                   for k in METRICS[:4]},
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--replicates", type=int, default=3)
    ap.add_argument("--planner-minutes", type=float, default=6)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    sections = o.load_sections()
    times = {crn: s.meetings for crn, s in sections.items()}
    options = build_options(sections, {s.course for s in sections.values()})
    target = demand_targets(options)
    options = {c: v for c, v in options.items() if c in target}
    real = load_real(options)
    print(f"{len(options)} undergraduate courses with timed sections, "
          f"{len(real)} real students", flush=True)
    results = []
    for r in range(args.replicates):
        results.append(run(args.seed + r, real, options, sections, times, target,
                           args.planner_minutes))
        (OUT / "citywide_summary.json").write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps({k: v for k, v in results[-1].items() if k != "population"}, indent=1))


if __name__ == "__main__":
    main()
