"""Year 1 timetable optimizer (prototype) using OR-Tools CP-SAT.

Class times stay exactly as published; the optimizer only decides which
section (lecture, tutorial, lab) each student takes.

  Random     Students sign up one by one in random order; each gets a random
             clash-free timetable from the seats still open.
  FCFS       Same, but each student picks their own best timetable (today's
             first-come-first-served registration).
  Planner    Every student is assigned at once (Stage B). Students are modelled
             in *blocks*: up to BLOCK_SIZE students of one cohort (major +
             English stream) who share a timetable.

With --retime it also runs a timetable redesign: Stage A moves the meetings of
the sections Year 1 uses (keeping rooms, length and term weeks, never
double-booking rooms or instructors), then Stage B re-assigns students.

Meetings run in specific term weeks (e.g. a lecture in weeks 1-10 and its
tutorials in weeks 11-13 can share a slot), so clashes are checked week by week.
Gaps and campus load are optimised on the regular meetings (>= REGULAR_WEEKS
weeks); the reported metrics are computed for every teaching week and averaged.

Objective: IDLE_WEIGHT * student idle hours between classes
  + PEAK_WEIGHT * peak students on campus in any hour
  + FAIR_WEIGHT * the worst block's weekly idle hours
  + BALANCE_WEIGHT * each student's longest minus shortest day on campus
    (a linear stand-in for the std of daily hours, which metrics() reports)
  (+ in Stage A, LATE_WEIGHT per student-hour on Saturday or after 19:00).

Usage: python3 scripts/optimize.py [--time-limit SECONDS] [--seed N] [--retime]
"""
import argparse
import csv
import json
import math
import random
import re
import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from ortools.sat.python import cp_model

ROOT = Path(__file__).resolve().parent.parent
SECTIONS = ROOT / "data/sections.csv"
CURRICULA = ROOT / "data/curricula_year1_semA.csv"
OUT_DIR = ROOT / "results"

BLOCK_SIZE = 12
DAYS = "MTWRFS"  # Mon..Sat; Sunday meetings are kept but ignored for students
HOURS = range(9, 23)  # hour slots 09:00 .. 22:50
WEEKDAY_LAST, SAT_LAST = 21, 18  # last slot a moved meeting may use
EVENING = 19
TERM_START = date(2026, 8, 31)  # Monday of week 1
TEACHING_WEEKS = range(13)  # 31 Aug - 28 Nov
REGULAR_WEEKS = 7
# Objective weights, per student-hour. BALANCE_WEIGHT prices one hour of
# difference between a student's longest and shortest day on campus.
IDLE_WEIGHT, PEAK_WEIGHT, FAIR_WEIGHT, BALANCE_WEIGHT, LATE_WEIGHT = 2, 6, 100, 1, 2
CLASH_PENALTY = 1000
SECTION_RE = re.compile(r"^([A-Z])([A-Z]?)(\d+)$")


@dataclass
class Meeting:
    day: int
    start: int
    length: int
    venues: frozenset
    instructors: frozenset
    weeks: frozenset

    def hours(self):
        return range(self.start, self.start + self.length)

    @property
    def regular(self):
        return len(self.weeks) >= REGULAR_WEEKS

    def moved(self, day, start):
        return Meeting(day, start, self.length, self.venues, self.instructors, self.weeks)


@dataclass
class Section:
    crn: str
    course: str
    code: str
    kind: str
    group: str
    cap: int
    meetings: list = field(default_factory=list)


def parse_hours(start, end):
    sh, eh, em = int(start[:2]), int(end[:2]), int(end[3:])
    return sh, eh - sh + (1 if em > 0 else 0)


def term_weeks(day, date_from, date_to):
    """Weeks (0-based) in which a meeting on `day` falls inside the date range."""
    lo, hi = (date(*map(int, reversed(d.split("/")))) for d in (date_from, date_to))
    return frozenset(w for w in range(20)
                     if lo <= TERM_START + timedelta(weeks=w, days=day) <= hi)


def load_sections():
    sections = {}
    with open(SECTIONS, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            s = sections.get(r["crn"])
            if s is None:
                m = SECTION_RE.match(r["section"])
                s = sections[r["crn"]] = Section(
                    r["crn"], r["course"], r["section"], r["section"][:1],
                    m.group(2) if m else "", int(r["cap"] or 0))
            if not r["day"] or r["day"] not in DAYS + "U":
                continue
            day = (DAYS + "U").index(r["day"])
            start, length = parse_hours(r["start"], r["end"])
            weeks = term_weeks(day, r["date_from"], r["date_to"])
            venues = frozenset([r["venue"]]) if r["venue"] and not r["venue"].startswith("TBA") else frozenset()
            inst = frozenset(i.strip() for i in r["instructor"].split(",")
                             if i.strip() and not i.startswith("TBA"))
            for i, m in enumerate(s.meetings):  # one meeting held in several rooms
                if (m.day, m.start, m.length, m.weeks) == (day, start, length, weeks):
                    s.meetings[i] = Meeting(day, start, length, m.venues | venues,
                                            m.instructors | inst, weeks)
                    break
            else:
                s.meetings.append(Meeting(day, start, length, venues, inst, weeks))
    return sections


@dataclass
class Block:
    id: int
    major: str
    english: str
    size: int
    courses: list


def section_options(sections, courses):
    """course -> kind -> timed sections a Year 1 student could take."""
    opts = defaultdict(lambda: defaultdict(list))
    for s in sections.values():
        if s.course in courses and s.meetings and s.cap > 0 and all(m.day < 6 for m in s.meetings):
            opts[s.course][s.kind].append(s)
    return opts


def load_blocks(options):
    blocks = []
    with open(CURRICULA, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            n, courses = int(r["students"]), r["courses"].split()
            if n == 0:
                continue
            # Blocks must fit in the largest section of every course type.
            limit = min(max(s.cap for s in options[c][k]) for c in courses for k in options[c])
            nb = math.ceil(n / min(BLOCK_SIZE, limit))
            for i in range(nb):
                size = n // nb + (1 if i < n % nb else 0)
                blocks.append(Block(len(blocks), r["major"], r["english"], size, courses))
    return blocks


def linked_groups(kinds):
    """Lettered sections (CA1 + TA1) must match when every type uses the same letters."""
    groups = [frozenset(s.group for s in secs) for secs in kinds.values()]
    if len(groups) > 1 and len(set(groups)) == 1 and len(groups[0]) > 1:
        return sorted(groups[0])
    return None


def at_most_one_per_week(model, terms, limit=1, slack=None):
    """terms: [(literal or 1, weeks)]. At most `limit` active in any single week.

    With a `slack` list, the limit becomes soft: an excess variable per constraint
    is appended to it for the caller to penalise.
    """
    seen = set()
    for w in set().union(*(wk for _, wk in terms)):
        active = [t for t, wk in terms if w in wk]
        key = tuple(sorted(id(t) for t in active))
        if len(active) < 2 or key in seen:
            continue
        seen.add(key)
        fixed = sum(t for t in active if isinstance(t, int))
        excess = 0
        if slack is not None:
            excess = model.NewIntVar(0, len(active), "")
            slack.append(excess)
        model.Add(sum(t for t in active if not isinstance(t, int)) <= limit - fixed + excess)


def occupancy(model, terms):
    """Regular-week occupancy of one block-hour as a 0/1 expression."""
    regular = [t for t, wk in terms if len(wk) >= REGULAR_WEEKS]
    if any(isinstance(t, int) for t in regular):
        return 1
    if len(regular) <= 1:
        return sum(regular)
    o = model.NewBoolVar("")
    for t in regular:
        model.AddImplication(t, o)
    model.Add(o <= sum(regular))
    return o


class Week:
    """Per-block idle and on-campus variables plus the shared objective."""

    def __init__(self, model, blocks, occ):
        self.idle = {}
        hs = list(HOURS)
        worst_terms, spread_terms = [], []
        onsite = {}
        for b in blocks:
            mine = []
            longest = model.NewIntVar(0, len(hs), "")
            shortest = model.NewIntVar(0, len(hs), "")
            model.Add(shortest <= longest)
            for d in range(len(DAYS)):
                # pre[h] / suf[h]: some class before / after hour h (exact, so
                # idle and on-campus hours can't be padded to game the objective)
                pre, suf = {}, {}
                for h in hs:
                    pre[h] = model.NewBoolVar("")
                    if h == hs[0]:
                        model.Add(pre[h] == 0)
                    else:
                        model.Add(pre[h] >= pre[h - 1])
                        model.Add(pre[h] >= occ[b.id, d, h - 1])
                        model.Add(pre[h] <= pre[h - 1] + occ[b.id, d, h - 1])
                for h in reversed(hs):
                    suf[h] = model.NewBoolVar("")
                    if h == hs[-1]:
                        model.Add(suf[h] == 0)
                    else:
                        model.Add(suf[h] >= suf[h + 1])
                        model.Add(suf[h] >= occ[b.id, d, h + 1])
                        model.Add(suf[h] <= suf[h + 1] + occ[b.id, d, h + 1])
                day = []
                for h in hs:
                    idle = self.idle[b.id, d, h] = model.NewBoolVar("")
                    model.Add(idle >= pre[h] + suf[h] - 1 - occ[b.id, d, h])
                    model.Add(idle <= pre[h])
                    model.Add(idle <= suf[h])
                    model.Add(idle <= 1 - occ[b.id, d, h])
                    onsite[b.id, d, h] = occ[b.id, d, h] + idle
                    day.append(onsite[b.id, d, h])
                    mine.append(idle)
                # Balanced days: longest minus shortest day the block is on campus.
                present = model.NewBoolVar("")
                for h in hs:
                    model.Add(present >= occ[b.id, d, h])
                model.Add(present <= sum(occ[b.id, d, h] for h in hs))
                model.Add(longest >= sum(day))
                model.Add(shortest <= sum(day) + len(hs) * (1 - present))
            worst_terms.append(sum(mine))
            spread_terms.append(b.size * (longest - shortest))
        self.peak = model.NewIntVar(0, sum(b.size for b in blocks), "peak")
        for d in range(len(DAYS)):
            for h in hs:
                model.Add(self.peak >= sum(b.size * onsite[b.id, d, h] for b in blocks))
        self.worst = model.NewIntVar(0, len(DAYS) * len(hs), "worst")
        for t in worst_terms:
            model.Add(self.worst >= t)
        self.idle_hours = sum(blocks[bid].size * v for (bid, _, _), v in self.idle.items())
        self.spread = sum(spread_terms)

    def objective(self, extra=0):
        return (IDLE_WEIGHT * self.idle_hours + PEAK_WEIGHT * self.peak
                + FAIR_WEIGHT * self.worst + BALANCE_WEIGHT * self.spread + extra)


def solve(model, time_limit, label, workers=4, required=True):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = workers
    status = solver.Solve(model)
    if label:
        print(f"  {label}: {solver.StatusName(status)} objective={solver.ObjectiveValue():.0f} "
              f"bound={solver.BestObjectiveBound():.0f} time={solver.WallTime():.0f}s", flush=True)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        if required:
            raise SystemExit(f"{label} found no solution")
        return None
    return solver


def block_week(model, blocks, slot_terms, slack=None):
    """Clash constraints and occupancy from (block, day, hour) -> [(lit, weeks)]."""
    occ = {}
    for b in blocks:
        for d in range(len(DAYS)):
            for h in HOURS:
                terms = slot_terms.get((b.id, d, h), [])
                at_most_one_per_week(model, terms, slack=slack)
                occ[b.id, d, h] = occupancy(model, terms)
    return Week(model, blocks, occ)


def stage_b(blocks, options, times, time_limit, hint=None, label="Stage B", seats=None,
            allow_clash=False, workers=4, rng=None):
    """Assign blocks to sections given fixed meeting times. times: crn -> [Meeting].

    seats overrides section caps (crn -> seats left). With allow_clash, clashes are
    allowed at a heavy penalty. With rng, the choice is random instead of
    optimized (still clash-free when possible). Returns the chosen (block id, crn) pairs, or None
    if no assignment exists.
    """
    m = cp_model.CpModel()
    y = {}
    load = defaultdict(list)
    slot_terms = defaultdict(list)
    caps = {s.crn: s.cap for kinds in options.values() for secs in kinds.values() for s in secs}
    if seats is not None:
        caps.update(seats)
    for b in blocks:
        for c in b.courses:
            kinds = options[c]
            groups = linked_groups(kinds)
            pick = {g: m.NewBoolVar("") for g in groups} if groups else None
            if pick:
                m.AddExactlyOne(pick.values())
            for secs in kinds.values():
                choice = []
                for s in secs:
                    if caps[s.crn] < b.size:
                        continue
                    v = y[b.id, s.crn] = m.NewBoolVar("")
                    choice.append(v)
                    load[s.crn].append(b.size * v)
                    if pick:
                        m.AddImplication(v, pick[s.group])
                    for mt in times[s.crn]:
                        for h in mt.hours():
                            slot_terms[b.id, mt.day, h].append((v, mt.weeks))
                m.AddExactlyOne(choice)
    for crn, terms in load.items():
        m.Add(sum(terms) <= caps[crn])
    slack = [] if allow_clash else None
    week = block_week(m, blocks, slot_terms, slack)
    clash_cost = CLASH_PENALTY * sum(slack) if slack else 0
    if rng is None:
        m.Minimize(week.objective(clash_cost))
    else:
        m.Minimize(sum(rng.randrange(1000) * v for v in y.values()) + 1000 * clash_cost)
    if hint:
        for key, v in y.items():
            m.AddHint(v, key in hint)
    solver = solve(m, time_limit, label, workers=workers, required=label is not None)
    if solver is None:
        return None
    return {key for key, v in y.items() if solver.Value(v)}


def register(blocks, options, times, seed=1, random_choice=False):
    """Simulate students signing up one at a time in random order.

    Each student takes the best clash-free timetable still open to them (same
    objective as the planner, for one student), or with random_choice a random
    clash-free one. A student left with no clash-free choice takes the
    least-clashing one; one left with no seat in a course goes without it.

    Returns (students, assignment, unplaced) where students are size-1 blocks.
    """
    rng = random.Random(seed + 1) if random_choice else None
    students = []
    for b in blocks:
        for _ in range(b.size):
            students.append(Block(len(students), b.major, b.english, 1, b.courses))
    seats = {s.crn: s.cap for kinds in options.values() for secs in kinds.values() for s in secs}
    order = list(range(len(students)))
    random.Random(seed).shuffle(order)
    assign, unplaced = set(), defaultdict(list)
    for n, sid in enumerate(order):
        st = students[sid]
        open_courses = [c for c in st.courses
                        if all(any(seats[s.crn] > 0 for s in secs) for secs in options[c].values())]
        unplaced[sid] = [c for c in st.courses if c not in open_courses]
        me = Block(0, st.major, st.english, 1, open_courses)
        pick = (stage_b([me], options, times, 10, label=None, seats=seats, workers=1, rng=rng)
                or stage_b([me], options, times, 10, label=None, seats=seats, workers=1,
                           allow_clash=True, rng=rng))
        if pick is None:  # linked lecture/tutorial seats ran out together
            unplaced[sid] = st.courses
            pick = set()
        for _, crn in pick:
            seats[crn] -= 1
            assign.add((sid, crn))
        if (n + 1) % 500 == 0:
            print(f"  registered {n + 1}/{len(students)}", flush=True)
    return students, assign, {k: v for k, v in unplaced.items() if v}


def stage_a(blocks, sections, assign, time_limit):
    """Move the meetings of sections Year 1 uses; returns crn -> [Meeting]."""
    used = {crn for _, crn in assign}
    # An event is a set of meetings that move together: the same slot and rooms
    # (cross-listed sections, or one section's meetings in different weeks).
    events, member = defaultdict(list), {}
    for s in sections.values():
        for i, mt in enumerate(s.meetings):
            if mt.day >= 6:
                continue
            key = (mt.day, mt.start, mt.length, mt.venues or s.crn)
            events[key].append((s.crn, i))
            member[s.crn, i] = key
    movable = [k for k, ms in events.items() if any(crn in used for crn, _ in ms)]
    movable_set = set(movable)

    def meetings(e):
        return [sections[c].meetings[i] for c, i in events[e]]

    def info(e):
        ms = meetings(e)
        return (ms[0], frozenset().union(*(x.venues for x in ms)),
                frozenset().union(*(x.instructors for x in ms)),
                frozenset().union(*(x.weeks for x in ms)))

    # Fixed bookings: (resource, day, hour) -> weeks busy.
    busy = defaultdict(set)
    for s in sections.values():
        for i, mt in enumerate(s.meetings):
            if member.get((s.crn, i)) in movable_set:
                continue
            for h in mt.hours():
                for r in mt.venues | mt.instructors:
                    busy[r, mt.day, h] |= mt.weeks

    attendees = defaultdict(int)
    for bid, crn in assign:
        attendees[crn] += blocks[bid].size

    m = cp_model.CpModel()
    z = defaultdict(dict)  # event -> (day, start) -> literal
    late_terms = []
    for e in movable:
        mt0, venues, people, weeks = info(e)
        students = sum(attendees[c] for c, _ in events[e])
        for d in range(len(DAYS)):
            last = SAT_LAST if DAYS[d] == "S" else WEEKDAY_LAST
            for st in range(HOURS[0], last - mt0.length + 2):
                hs = range(st, st + mt0.length)
                if any(busy.get((r, d, h), set()) & weeks for r in venues | people for h in hs):
                    continue
                v = z[e][d, st] = m.NewBoolVar("")
                late = sum(1 for h in hs if DAYS[d] == "S" or h >= EVENING)
                if late:
                    late_terms.append(late * students * v)
        if (mt0.day, mt0.start) not in z[e]:
            print(f"  note: real slot of {events[e][0]} clashes with fixed bookings")
        m.AddExactlyOne(z[e].values())

    def covering(e, d, h):
        length = info_cache[e][0].length
        return [v for (dd, st), v in z[e].items() if dd == d and st <= h < st + length]

    info_cache = {e: info(e) for e in movable}

    # Rooms and instructors shared between moving events, week by week.
    users = defaultdict(list)
    for e in movable:
        _, venues, people, _ = info_cache[e]
        for r in venues | people:
            users[r].append(e)
    for es in users.values():
        if len(es) < 2:
            continue
        for d in range(len(DAYS)):
            for h in HOURS:
                terms = [(v, info_cache[e][3]) for e in es for v in covering(e, d, h)]
                if len(terms) > 1:
                    at_most_one_per_week(m, terms)

    # A section whose meetings were on different days keeps them on different days.
    by_section = defaultdict(set)
    for e in movable:
        for crn, _ in events[e]:
            by_section[crn].add(e)
    for es in by_section.values():
        if len(es) > 1 and len({e[0] for e in es}) == len(es):
            for d in range(len(DAYS)):
                m.Add(sum(v for e in es for (dd, _), v in z[e].items() if dd == d) <= 1)

    # Student clashes and occupancy: fixed meetings plus moving ones.
    slot_terms = defaultdict(list)
    for bid, crn in assign:
        for i, mt in enumerate(sections[crn].meetings):
            e = member.get((crn, i))
            if e in movable_set:
                for (d, st), v in z[e].items():
                    for h in range(st, st + mt.length):
                        slot_terms[bid, d, h].append((v, mt.weeks))
            elif mt.day < 6:
                for h in mt.hours():
                    slot_terms[bid, mt.day, h].append((1, mt.weeks))
    week = block_week(m, blocks, slot_terms)
    m.Minimize(week.objective(LATE_WEIGHT * sum(late_terms)))
    for e in movable:  # start from the real timetable
        mt0 = info_cache[e][0]
        for (d, st), v in z[e].items():
            m.AddHint(v, (d, st) == (mt0.day, mt0.start))
    solver = solve(m, time_limit, "Stage A (retime)")

    times = {crn: list(s.meetings) for crn, s in sections.items()}
    moved = 0
    for e in movable:
        d, st = next(k for k, v in z[e].items() if solver.Value(v))
        for crn, i in events[e]:
            old = sections[crn].meetings[i]
            moved += (old.day, old.start) != (d, st)
            times[crn][i] = old.moved(d, st)
    print(f"  moved {moved} of {sum(len(events[e]) for e in movable)} meetings "
          f"({len(movable)} movable events)")
    return times


def metrics(blocks, assign, times):
    """Student-level statistics, computed for every teaching week and averaged."""
    occ = defaultdict(int)
    for bid, crn in assign:
        for mt in times[crn]:
            if mt.day >= 6:
                continue
            for w in mt.weeks & set(TEACHING_WEEKS):
                for h in mt.hours():
                    occ[bid, w, mt.day, h] += 1
    nweeks = len(TEACHING_WEEKS)
    students = sum(b.size for b in blocks)
    idle_per_student, days, late, clashes = [], 0, 0, 0
    day_std, longest = [], []
    onsite = defaultdict(int)
    for b in blocks:
        idle, std_sum, long_sum = 0, 0, 0
        for w in TEACHING_WEEKS:
            spans = []
            for d in range(len(DAYS)):
                hs = [h for h in HOURS if occ.get((b.id, w, d, h))]
                if not hs:
                    continue
                spans.append(hs[-1] - hs[0] + 1)
                days += b.size
                clashes += b.size * sum(occ[b.id, w, d, h] - 1 for h in hs)
                late += b.size * sum(1 for h in hs if DAYS[d] == "S" or h >= EVENING)
                for h in range(hs[0], hs[-1] + 1):
                    onsite[w, d, h] += b.size
                    idle += not occ.get((b.id, w, d, h))
            std_sum += statistics.pstdev(spans) if spans else 0
            long_sum += max(spans, default=0)
        idle_per_student += [idle / nweeks] * b.size
        day_std += [std_sum / nweeks] * b.size
        longest += [long_sum / nweeks] * b.size
    weekday = [onsite.get((w, d, h), 0) for w in TEACHING_WEEKS for d in range(5) for h in HOURS]
    return {
        "students": students,
        "idle_hours_per_student_week": round(statistics.mean(idle_per_student), 2),
        "idle_hours_std": round(statistics.pstdev(idle_per_student), 2),
        "idle_hours_max": round(max(idle_per_student), 2),
        "students_with_3h_plus_idle_per_week": sum(1 for x in idle_per_student if x >= 3),
        "days_on_campus_per_student_week": round(days / students / nweeks, 2),
        "daily_hours_std_per_student": round(statistics.mean(day_std), 2),
        "longest_day_hours_per_student": round(statistics.mean(longest), 2),
        "peak_students_on_campus": max(onsite.values()),
        "weekday_hourly_load_std": round(statistics.pstdev(weekday), 1),
        "evening_or_saturday_class_hours_per_student_week": round(late / students / nweeks, 2),
        "student_clash_hours": clashes,
    }


def double_bookings(times):
    """(kind, resource, week, day, hour) used by meetings at different start times.

    Meetings that share room, day and start are cross-listed sections, not clashes.
    """
    use = defaultdict(set)
    for mts in times.values():
        for mt in mts:
            for h in mt.hours():
                for w in mt.weeks:
                    for r in mt.venues:
                        use["room", r, w, mt.day, h].add((mt.start, mt.length))
                    for p in mt.instructors:
                        use["instructor", p, w, mt.day, h].add((mt.start, mt.length))
    return {key for key, starts in use.items() if len(starts) > 1}


def conflict_summary(real, times):
    before, after = double_bookings(real), double_bookings(times)
    count = lambda keys, kind: sum(1 for k in keys if k[0] == kind)
    return {f"{kind}_hours_{label}": count(keys, kind)
            for kind in ("room", "instructor")
            for label, keys in (("in_real_data", before), ("introduced", after - before),
                                ("resolved", before - after))}


def write_timetables(path, blocks, assign, times, sections):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["block", "major", "english", "students", "course", "crn", "section",
                    "day", "start", "end", "weeks", "venue"])
        for bid, crn in sorted(assign):
            b, s = blocks[bid], sections[crn]
            for mt in times[crn]:
                w.writerow([bid, b.major, b.english, b.size, s.course, crn, s.code,
                            (DAYS + "U")[mt.day], f"{mt.start:02d}:00",
                            f"{mt.start + mt.length - 1:02d}:50",
                            f"{min(mt.weeks) + 1}-{max(mt.weeks) + 1}" if mt.weeks else "",
                            " + ".join(sorted(mt.venues))])


def student_view(students, baselines, blocks, opt, times, sections):
    """Per-student timetables for the app: each baseline vs the planner.

    baselines: {name: assignment over the size-1 student blocks}.
    """
    def week(assign, owner):
        out = []
        for crn in sorted(c for o, c in assign if o == owner):
            s = sections[crn]
            for mt in times[crn]:
                if mt.day < 6:
                    out.append([s.course, s.code, mt.day, mt.start, mt.length,
                                min(mt.weeks) + 1, max(mt.weeks) + 1, " + ".join(sorted(mt.venues))])
        return out
    by_owner = {name: defaultdict(set) for name in baselines}
    for name, assign in baselines.items():
        for sid, crn in assign:
            by_owner[name][sid].add((sid, crn))
    block_of, sid = {}, 0
    for b in blocks:  # students were expanded from blocks in this order
        for _ in range(b.size):
            block_of[sid] = b.id
            sid += 1
    opt_weeks = {b.id: week(opt, b.id) for b in blocks}
    return [{"major": st.major, "english": st.english, "courses": st.courses,
             **{name: week(by_owner[name][st.id], st.id) for name in baselines},
             "optimized": opt_weeks[block_of[st.id]], "group": block_of[st.id]}
            for st in students]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--time-limit", type=float, default=120, help="seconds per optimization stage")
    ap.add_argument("--seed", type=int, default=1, help="registration order for the simulation")
    ap.add_argument("--hint", type=Path,
                    help="block timetable CSV from an earlier run to start the planner from")
    ap.add_argument("--retime", action="store_true",
                    help="also try moving class times (a timetable redesign, not just sectioning)")
    args = ap.parse_args()

    sections = load_sections()
    with open(CURRICULA, encoding="utf-8") as f:
        courses = {c for r in csv.DictReader(f) for c in r["courses"].split()}
    options = section_options(sections, courses)
    blocks = load_blocks(options)
    print(f"{sum(b.size for b in blocks)} students in {len(blocks)} blocks, {len(courses)} courses, "
          f"{sum(len(v) for k in options.values() for v in k.values())} candidate sections")
    real = {crn: s.meetings for crn, s in sections.items()}

    summary = {"weights": {"idle": IDLE_WEIGHT, "peak": PEAK_WEIGHT, "fairness": FAIR_WEIGHT,
                           "daily_balance": BALANCE_WEIGHT},
               "block_size": BLOCK_SIZE, "blocks": len(blocks), "seed": args.seed,
               "time_limit_per_stage_s": args.time_limit}
    baselines = {}
    for name, random_choice, text in (
            ("random", True, "Random: each student gets a random clash-free timetable"),
            ("fcfs", False, "First come, first served: each student picks their own best timetable")):
        print(text, flush=True)
        students, assign, unplaced = register(blocks, options, real, args.seed, random_choice)
        summary[name] = metrics(students, assign, real)
        summary[name]["students_missing_a_course"] = len(unplaced)
        baselines[name] = assign

    print("Planner: assign every student together, class times unchanged", flush=True)
    hint = None
    if args.hint:
        with open(args.hint, encoding="utf-8") as f:
            hint = {(int(r["block"]), r["crn"]) for r in csv.DictReader(f)}
    opt_assign = stage_b(blocks, options, real, args.time_limit, hint=hint, label="Sectioning")
    summary["planner"] = metrics(blocks, opt_assign, real)
    summary["planner"]["students_missing_a_course"] = 0
    view = student_view(students, baselines, blocks, opt_assign, real, sections)

    OUT_DIR.mkdir(exist_ok=True)
    for name, assign in baselines.items():
        with open(OUT_DIR / f"{name}_student_timetables.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["student", "major", "english", "course", "crn", "section"])
            for sid, crn in sorted(assign):
                st = students[sid]
                w.writerow([sid, st.major, st.english, sections[crn].course, crn, sections[crn].code])
    write_timetables(OUT_DIR / "planner_block_timetables.csv", blocks, opt_assign, real, sections)

    if args.retime:
        print("Redesign: move class times, then re-section", flush=True)
        times = stage_a(blocks, sections, opt_assign, args.time_limit)
        re_assign = stage_b(blocks, options, times, args.time_limit, hint=opt_assign)
        summary["retimed"] = metrics(blocks, re_assign, times)
        summary["double_booked_hours"] = conflict_summary(real, times)
        write_timetables(OUT_DIR / "retimed_block_timetables.csv", blocks, re_assign, times, sections)
        with open(OUT_DIR / "retimed_section_times.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["course", "crn", "section", "old_day", "old_start", "new_day", "new_start",
                        "hours", "weeks", "venue"])
            for crn, s in sorted(sections.items(), key=lambda x: (x[1].course, x[1].code)):
                for old, new in zip(s.meetings, times[crn]):
                    if (old.day, old.start) != (new.day, new.start):
                        w.writerow([s.course, crn, s.code, DAYS[old.day], f"{old.start:02d}:00",
                                    DAYS[new.day], f"{new.start:02d}:00", old.length,
                                    f"{min(old.weeks) + 1}-{max(old.weeks) + 1}",
                                    " + ".join(sorted(old.venues))])

    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    app = {"summary": summary, "days": DAYS, "hours": [HOURS[0], HOURS[-1]], "students": view}
    (OUT_DIR / "app_data.json").write_text(json.dumps(app, separators=(",", ":")))

    cols = [k for k in ("random", "fcfs", "planner", "retimed") if k in summary]
    print(f"\n{'metric':52}" + "".join(f"{c:>10}" for c in cols))
    for k in summary["planner"]:
        print(f"{k:52}" + "".join(f"{summary[c].get(k, ''):>10}" for c in cols))


if __name__ == "__main__":
    main()
