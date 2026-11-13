"""Research workbook: every result and assumption behind the CityU timetable model.

Reads results/citywide_summary.json, results/explorer/data.json and
results/summary.json; writes results/cityu_timetable_model_results.xlsx.

Usage: python3 scripts/build_workbook.py && python3 <xlsx skill>/scripts/recalc.py <file>
"""
import json
import statistics
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "results/cityu_timetable_model_results.xlsx"
RUNS = json.loads((ROOT / "results/citywide_summary.json").read_text())
EXP = json.loads((ROOT / "results/explorer/data.json").read_text())
Y1 = json.loads((ROOT / "results/summary.json").read_text())

F = "Arial"
BLUE = Font(name=F, color="0000FF")
BODY = Font(name=F)
BOLD = Font(name=F, bold=True)
HEAD = Font(name=F, bold=True, color="FFFFFF")
TITLE = Font(name=F, bold=True, size=14, color="0B2A5E")
NOTE = Font(name=F, italic=True, color="4F6684", size=9)
HFILL = PatternFill("solid", fgColor="1A5FD0")
KEY = PatternFill("solid", fgColor="E3EEFD")
THIN = Border(bottom=Side(style="thin", color="D5E1F0"))
WRAP = Alignment(wrap_text=True, vertical="top")

SCEN = {"random": "Random clash-free picks (today)", "fcfs": "First come, best pick",
        "planner": "Planner (model)", "actual": "Real timetables (screenshots)"}
METRICS = [
    ("gap_hours", "Gap hours per student per week", "0.00"),
    ("unevenness", "Uneven week (avg distance of a weekday from 1/5 of weekly hours)", "0.00"),
    ("longest_day", "Longest day on campus (h)", "0.00"),
    ("days_on_campus", "Days on campus per week", "0.00"),
    ("saturday_hours", "Saturday class hours per week", "0.00"),
    ("worst_10pct_gap_hours", "Gap hours, worst 10% of students", "0.00"),
    ("share_with_3h_plus_gaps", "Share of students with 3+ gap hours", "0.0%"),
    ("share_with_no_gaps", "Share of students with no gaps", "0.0%"),
    ("share_missing_a_course", "Share of students missing a course", "0.0%"),
]


def sheet(wb, name, title, note=None):
    ws = wb.create_sheet(name)
    ws["A1"] = title
    ws["A1"].font = TITLE
    if note:
        ws["A2"] = note
        ws["A2"].font = NOTE
    ws.sheet_view.showGridLines = False
    return ws


def header(ws, row, cols):
    for i, c in enumerate(cols, 1):
        cell = ws.cell(row=row, column=i, value=c)
        cell.font, cell.fill, cell.alignment = HEAD, HFILL, Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[row].height = 32


def put(ws, row, col, value, fmt=None, font=BODY):
    c = ws.cell(row=row, column=col, value=value)
    c.font, c.border = font, THIN
    if fmt:
        c.number_format = fmt
    return c


def widths(ws, ws_widths):
    for i, w in enumerate(ws_widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w


def avg(vals):
    return round(statistics.fmean(vals), 4)


def overview(wb):
    ws = wb.active
    ws.title = "Overview"
    ws.sheet_view.showGridLines = False
    o, r = EXP["overall"], EXP["real"]
    pop = RUNS[0]["population"]
    lines = [
        ("CityU timetable planner: results for the research report", TITLE),
        ("Semester A 2026/27, City University of Hong Kong", NOTE),
        ("", None),
        ("What the model does", BOLD),
        ("Class times and room seat caps stay fixed. The model only decides which section (lecture, tutorial, lab) each "
         "student takes, so that weeks have fewer idle gaps, a shorter longest day, a more even spread over Mon-Fri, "
         "every student keeps all their courses, and busy buildings are relieved.", BODY),
        ("", None),
        ("How the population was built", BOLD),
        (f"{r['students']} real Semester A timetables (from student screenshots, anonymised to course/section codes) were "
         f"bootstrapped to about {o['students']:,} undergraduates matched to AIMS enrolment of {pop['courses']} timed "
         f"undergraduate courses (about {pop['demand_covered']:.0%} of seats). Three independent populations were built; "
         "figures are their average, with 95% paired-bootstrap intervals over students.", BODY),
        ("", None),
        ("Key findings (see the sheets for every number)", BOLD),
        (f"1. All undergraduates: gap hours fall from {o['random']['gap']:.2f} to {o['planner']['gap']:.2f} per student per week "
         f"(95% interval {-o['ci_gap'][2]:.2f} to {-o['ci_gap'][1]:.2f} h less) against today's random section picks.", BODY),
        (f"2. Longest day on campus falls from {o['random']['long']:.1f} to {o['planner']['long']:.1f} hours.", BODY),
        (f"3. Students with 3+ gap hours a week fall from {o['random']['gap3_share']:.0%} to {o['planner']['gap3_share']:.0%}.", BODY),
        (f"4. The {r['students']} real students: gaps from {r['actual']['gap']:.2f} h in their real timetables to "
         f"{r['planner']['gap']:.2f} h with the planner, longest day {r['actual']['long']:.1f} -> {r['planner']['long']:.1f} h.", BODY),
        ("5. Real timetables are worse than random picks, so 'today' in this workbook understates current gaps.", BODY),
        ("6. A perfect first-come system gets close on gaps but leaves about 7% of students without a course; "
         "the planner places every course.", BODY),
        ("7. Largest gains: Business common core, Mathematics, Computer Science; smallest: Veterinary Medicine "
         "(few sections to choose from). See 'By programme'.", BODY),
        ("", None),
        ("Sheets", BOLD),
        ("Headline results - all undergraduates, three scenarios, with range over populations", BODY),
        ("Real students - the 183 real timetables vs the planner", BODY),
        ("Effects & intervals - change with 95% bootstrap intervals", BODY),
        ("By programme - 26 programme groups", BODY),
        ("Example timetables - biggest improvement per programme", BODY),
        ("Populations - size and coverage of each bootstrap population", BODY),
        ("Building load - busiest hour per building", BODY),
        ("Year 1 prototype - the earlier first-year-only CP-SAT model", BODY),
        ("Assumptions & parameters - every setting and definition", BODY),
        ("Data sources - files, scripts and links", BODY),
        ("", None),
        ("Colour key: blue text = values copied from model output; black = formulas in this workbook.", NOTE),
    ]
    for i, (text, font) in enumerate(lines, 1):
        c = ws.cell(row=i, column=1, value=text)
        if font:
            c.font = font
        c.alignment = WRAP
    ws.column_dimensions["A"].width = 120
    for i in (5, 8, 11, 14):
        ws.row_dimensions[i].height = 44


def headline(wb):
    ws = sheet(wb, "Headline results", "All undergraduates: three ways of assigning sections",
               "Mean over 3 bootstrap populations; min/max show the spread between populations. Per student per week, regular teaching weeks.")
    cols = ["Metric"]
    for k in ("random", "fcfs", "planner"):
        cols += [SCEN[k], "min", "max"]
    cols += ["Planner - today", "Planner vs today (%)", "Planner - first come"]
    header(ws, 4, cols)
    row = 5
    for key, label, fmt in METRICS:
        put(ws, row, 1, label)
        c = 2
        for k in ("random", "fcfs", "planner"):
            vals = [r["all_students"][k][key] for r in RUNS]
            put(ws, row, c, avg(vals), fmt, BLUE)
            put(ws, row, c + 1, min(vals), fmt, BLUE)
            put(ws, row, c + 2, max(vals), fmt, BLUE)
            c += 3
        put(ws, row, 11, f"=H{row}-B{row}", fmt)
        put(ws, row, 12, f"=IF(B{row}=0,\"-\",(H{row}-B{row})/B{row})", "0.0%")
        put(ws, row, 13, f"=H{row}-E{row}", fmt)
        if key in ("gap_hours", "longest_day", "share_with_3h_plus_gaps"):
            for cc in range(1, 14):
                ws.cell(row=row, column=cc).fill = KEY
        row += 1
    row += 1
    put(ws, row, 1, "Campus and building load", font=BOLD)
    row += 1
    for key, label in (("peak_students_in_class", "Peak students in class (busiest weekday hour)"),
                       ("hourly_load_std", "Std of students in class per weekday hour"),
                       ("building_peak_sum", "Sum over buildings of busiest-hour students")):
        put(ws, row, 1, label)
        c = 2
        for k in ("random", "fcfs", "planner"):
            vals = [r["all_students"][k][key] for r in RUNS]
            put(ws, row, c, avg(vals), "#,##0", BLUE)
            put(ws, row, c + 1, min(vals), "#,##0", BLUE)
            put(ws, row, c + 2, max(vals), "#,##0", BLUE)
            c += 3
        put(ws, row, 11, f"=H{row}-B{row}", "#,##0")
        put(ws, row, 12, f"=IF(B{row}=0,\"-\",(H{row}-B{row})/B{row})", "0.0%")
        put(ws, row, 13, f"=H{row}-E{row}", "#,##0")
        row += 1
    put(ws, row + 1, 1, "Highlighted rows are the headline figures. Negative changes are improvements, except days on campus "
        "(the planner spreads classes across the week on purpose).", font=NOTE)
    widths(ws, [52] + [13] * 9 + [14, 14, 16])
    ws.freeze_panes = "B5"


def real(wb):
    ws = sheet(wb, "Real students", "The real students: their actual timetables vs the model",
               "Same courses, section times and seat caps. Real = timetables read from screenshots; mean over the 3 populations they were placed in.")
    header(ws, 4, ["Metric", SCEN["actual"], SCEN["fcfs"], SCEN["planner"], "Planner - real", "Planner vs real (%)"])
    n_real = RUNS[0]["population"]["real_students"]
    row = 5
    for key, label, fmt in METRICS:
        put(ws, row, 1, label)
        for j, k in enumerate(("actual", "fcfs", "planner")):
            put(ws, row, 2 + j, avg(r["real_students"][k][key] for r in RUNS), fmt, BLUE)
        put(ws, row, 5, f"=D{row}-B{row}", fmt)
        put(ws, row, 6, f"=IF(B{row}=0,\"-\",(D{row}-B{row})/B{row})", "0.0%")
        row += 1
    put(ws, row, 1, "Number of real students")
    put(ws, row, 2, n_real, "0", BLUE)
    put(ws, row + 2, 1, "Real students' timetables have more gaps than the random-picks simulation (3.84 vs 3.01 h), "
        "which is why 'today' elsewhere is a cautious baseline.", font=NOTE)
    widths(ws, [52, 22, 20, 18, 16, 18])


def effects(wb):
    ws = sheet(wb, "Effects & intervals", "Change per student per week with the planner, 95% bootstrap intervals",
               "Paired bootstrap over students (1,000 resamples) in each population; the change is the mean over populations, "
               "the interval the widest over populations.")
    header(ws, 4, ["Comparison", "Metric", "Change", "95% low", "95% high", "Interval excludes 0?"])
    comps = (("planner_vs_random", "Planner vs today (random picks), all students"),
             ("planner_vs_fcfs", "Planner vs first come, all students"),
             ("real_planner_vs_actual", "Planner vs real timetables, real students"))
    names = {"gap_hours": "Gap hours", "unevenness": "Uneven week", "longest_day": "Longest day (h)",
             "days_on_campus": "Days on campus", "missing_courses": "Missing courses per student"}
    row = 5
    for comp, label in comps:
        for m in RUNS[0][comp]:
            vals = [r[comp][m] for r in RUNS]
            put(ws, row, 1, label)
            put(ws, row, 2, names.get(m, m))
            put(ws, row, 3, avg(v[0] for v in vals), "0.000", BLUE)
            put(ws, row, 4, min(v[1] for v in vals), "0.000", BLUE)
            put(ws, row, 5, max(v[2] for v in vals), "0.000", BLUE)
            put(ws, row, 6, f"=IF(OR(E{row}<0,D{row}>0),\"Yes\",\"No\")")
            row += 1
    widths(ws, [46, 28, 12, 12, 12, 20])


def programmes(wb):
    ws = sheet(wb, "By programme", "Results by programme group (all undergraduates, vs today's random picks)",
               "Programme = the subject a student takes most (excluding GE, PE, language and service maths/science). "
               "Students = average per population.")
    cols = ["Programme", "Students", "Gap h today", "Gap h planner", "Gap change", "Gap change (%)",
            "95% low", "95% high", "Longest day today", "Longest day planner", "Longest day change",
            "Uneven today", "Uneven planner", "Days today", "Days planner", "3+ gap h today", "3+ gap h planner",
            "Missing a course today", "Missing a course planner", "Class hours/week"]
    header(ws, 4, cols)
    rows = [("All students", EXP["overall"])] + list(EXP["programmes"].items())
    row = 5
    for name, g in rows:
        r, p = g["random"], g["planner"]
        vals = [(name, None), (g["students"], "#,##0"), (r["gap"], "0.00"), (p["gap"], "0.00"),
                (f"=D{row}-C{row}", "0.00"), (f"=IF(C{row}=0,\"-\",(D{row}-C{row})/C{row})", "0.0%"),
                (g["ci_gap"][1], "0.00"), (g["ci_gap"][2], "0.00"),
                (r["long"], "0.0"), (p["long"], "0.0"), (f"=J{row}-I{row}", "0.0"),
                (r["uneven"], "0.00"), (p["uneven"], "0.00"), (r["days"], "0.0"), (p["days"], "0.0"),
                (r["gap3_share"], "0.0%"), (p["gap3_share"], "0.0%"),
                (r["miss_share"], "0.0%"), (p["miss_share"], "0.0%"), (p["hours"], "0.0")]
        for j, (v, fmt) in enumerate(vals, 1):
            is_formula = isinstance(v, str) and v.startswith("=")
            c = put(ws, row, j, v, fmt, BODY if (is_formula or j == 1) else BLUE)
            if name == "All students":
                c.fill = KEY
                c.font = Font(name=F, bold=True, color=c.font.color)
        row += 1
    put(ws, row + 1, 1, "Programmes with fewer than 150 students are grouped as Other. 'First-year general education' are "
        "students taking only GE/PE/language courses.", font=NOTE)
    widths(ws, [34] + [12] * 19)
    ws.freeze_panes = "B5"


def examples(wb):
    ws = sheet(wb, "Example timetables", "Biggest improvement in each programme (student keeps every course)",
               "From population 1; students with 4-7 courses and no course missing in either timetable. Blocks list day, start hour and length.")
    header(ws, 4, ["Programme", "Courses", "Real or simulated", "Gap h today", "Gap h planner", "Gap change",
                   "Longest day today", "Longest day planner", "Days today", "Days planner",
                   "Week today (day start-hours course)", "Week with planner"])
    days = "Mon Tue Wed Thu Fri Sat".split()

    def week(blocks):
        return "; ".join(f"{days[d]} {h:02d}:00 +{n}h {c}" for c, d, h, n in sorted(blocks, key=lambda b: (b[1], b[2])) if d >= 0)

    row = 5
    for name, g in EXP["programmes"].items():
        if not g.get("examples"):
            continue
        ex = g["examples"][0]
        r, p = ex["random"], ex["planner"]
        vals = [name, " ".join(ex["courses"]), "real" if ex["real"] else "simulated", r["gap"], p["gap"],
                f"=E{row}-D{row}", r["long"], p["long"], r["days"], p["days"], week(r["blocks"]), week(p["blocks"])]
        for j, v in enumerate(vals, 1):
            c = put(ws, row, j, v, "0" if j in (4, 5, 6, 7, 8, 9, 10) else None,
                    BODY if j in (1, 2, 3, 6, 11, 12) else BLUE)
            if j in (2, 11, 12):
                c.alignment = WRAP
        ws.row_dimensions[row].height = 60
        row += 1
    put(ws, row + 1, 1, "These are best cases, not typical students; use 'By programme' for averages.", font=NOTE)
    widths(ws, [30, 34, 12, 10, 10, 10, 11, 11, 9, 9, 60, 60])


def populations(wb):
    ws = sheet(wb, "Populations", "Bootstrap populations", "Each population: real students plus clones until AIMS enrolment is used up.")
    header(ws, 4, ["Population (seed)", "Students", "Real students", "Target enrolments (AIMS)",
                   "Simulated enrolments", "Coverage", "Courses", "Courses per student", "Real courses per student"])
    row = 5
    for r in RUNS:
        p = r["population"]
        for j, (v, fmt) in enumerate([(r["seed"], "0"), (p["students"], "#,##0"), (p["real_students"], "0"),
                                      (p["target_enrolments"], "#,##0"), (p["simulated_enrolments"], "#,##0"),
                                      (f"=E{row}/D{row}", "0.0%"), (p["courses"], "0"),
                                      (p["mean_courses_per_student"], "0.00"),
                                      (p["real_mean_courses_per_student"], "0.00")], 1):
            put(ws, row, j, v, fmt, BODY if j == 6 else BLUE)
        row += 1
    put(ws, row, 1, "Average", font=BOLD)
    for j, fmt in ((2, "#,##0"), (5, "#,##0"), (6, "0.0%"), (8, "0.00")):
        col = get_column_letter(j)
        put(ws, row, j, f"=AVERAGE({col}5:{col}{row - 1})", fmt, BOLD)
    widths(ws, [18, 12, 13, 22, 20, 11, 10, 18, 22])


def buildings(wb):
    ws = sheet(wb, "Building load", "Busiest weekday hour per building (students in class)",
               "Mean over populations; regular weeks; building = first word of the venue code.")
    blds = sorted({b for r in RUNS for k in ("random", "planner") for b in r["all_students"][k]["building_peaks"]},
                  key=lambda b: -RUNS[0]["all_students"]["random"]["building_peaks"].get(b, 0))
    header(ws, 4, ["Building", SCEN["random"], SCEN["fcfs"], SCEN["planner"], "Planner - today", "Planner vs today (%)"])
    row = 5
    for b in blds:
        put(ws, row, 1, b)
        for j, k in enumerate(("random", "fcfs", "planner")):
            put(ws, row, 2 + j, avg(r["all_students"][k]["building_peaks"].get(b, 0) for r in RUNS), "#,##0", BLUE)
        put(ws, row, 5, f"=D{row}-B{row}", "#,##0")
        put(ws, row, 6, f"=IF(B{row}=0,\"-\",(D{row}-B{row})/B{row})", "0.0%")
        row += 1
    put(ws, row, 1, "Total", font=BOLD)
    for j in (2, 3, 4, 5):
        col = get_column_letter(j)
        put(ws, row, j, f"=SUM({col}5:{col}{row - 1})", "#,##0", BOLD)
    put(ws, row, 6, f"=IF(B{row}=0,\"-\",(D{row}-B{row})/B{row})", "0.0%", BOLD)
    widths(ws, [14, 30, 22, 18, 16, 20])


def year1(wb):
    ws = sheet(wb, "Year 1 prototype", "Earlier model: Year 1 students only, CP-SAT optimiser",
               f"{Y1['planner']['students']:,} first-year students in cohort blocks; other years' seats held back. From results/summary.json.")
    keys = [("idle_hours_per_student_week", "Gap hours per student per week", "0.00"),
            ("longest_day_hours_per_student", "Longest day (h)", "0.00"),
            ("daily_hours_std_per_student", "Std of daily hours", "0.00"),
            ("days_on_campus_per_student_week", "Days on campus", "0.00"),
            ("students_with_3h_plus_idle_per_week", "Students with 3+ gap hours", "#,##0"),
            ("student_clash_hours", "Student clash hours (term)", "#,##0"),
            ("students_missing_a_course", "Students missing a course", "#,##0"),
            ("weekday_hourly_load_std", "Std of campus load per weekday hour", "0.0"),
            ("building_peak_sum", "Sum of building busiest hours", "#,##0")]
    scen = [("random", "Random"), ("fcfs", "First come (clashes allowed)"),
            ("fcfs_no_clash", "First come (no clashes)"), ("planner", "Planner")]
    header(ws, 4, ["Metric"] + [s[1] for s in scen] + ["Planner - random"])
    row = 5
    for key, label, fmt in keys:
        put(ws, row, 1, label)
        for j, (k, _) in enumerate(scen):
            v = Y1.get(k, {}).get(key)
            put(ws, row, 2 + j, v if v is not None else "-", fmt, BLUE)
        put(ws, row, 6, f"=IF(ISNUMBER(B{row}),E{row}-B{row},\"-\")", fmt)
        row += 1
    widths(ws, [40, 14, 24, 22, 14, 16])


def assumptions(wb):
    ws = sheet(wb, "Assumptions & parameters", "Settings, definitions and limitations")
    header(ws, 3, ["Item", "Value", "Meaning / why"])
    items = [
        ("Population", None, None),
        ("Real students used", RUNS[0]["population"]["real_students"], "Sem A 2026/27 screenshots with timed undergraduate courses (199 screenshots, 189 Sem A)."),
        ("Bootstrap populations", len(RUNS), "Independent populations with different random seeds."),
        ("Course keep weight (KEEP_AFFINITY)", 4, "A clone's donor course counts 4x when picking its replacement."),
        ("Cross-subject weight (CROSS_SUBJECT)", 0.1, "Weight of same-level courses in other subjects when swapping."),
        ("Minimum timetable shape (MIN_SHAPE)", 0.75, "A clone keeps at least 75% as many courses as its donor."),
        ("Course tries per slot (TRIES)", 6, "Courses tried for a slot before giving it up when no seat fits the week."),
        ("Enrolment target", "AIMS enrolled_est", "Undergraduate-open courses with timed sections (cap minus seats available)."),
        ("Planner objective", None, None),
        ("Gap weight (GAP_W)", 15, "One idle hour between classes costs as much as 3 hours of uneven week."),
        ("Missing course penalty (MISS)", 150, "Effectively: never drop a course to improve a week."),
        ("Building load scale (LOAD_SCALE)", 1000, "An hour in a building with 1,000 students in class costs 1 point."),
        ("Planner time per population", "6 min", "Local search: worst timetables first, own re-plans and seat swaps."),
        ("Section combinations per course (MAX_COMBOS)", 600, "Cap on lecture/tutorial/lab combinations considered."),
        ("Definitions", None, None),
        ("Gap hours", "h/week", "Idle hours between a student's first and last class of each day, summed over the week."),
        ("Uneven week", "index", "Mean over Mon-Fri of |day hours - week hours/5|, divided by 5."),
        ("Longest day", "h", "Longest span from first to last class on any day."),
        ("Regular week", ">= 7 weeks", "Only meetings held in at least 7 teaching weeks count toward the weekly shape."),
        ("Today (random picks)", "-", "Each student holds a random clash-free mix of open sections; real screenshots are worse."),
        ("First come, best pick", "-", "Random registration order, each student takes the best open timetable."),
        ("Programme", "-", "Most-taken subject, ignoring GE, PED, LC, CHIN; MA/PHY/CHEM/CSCI only if nothing else."),
        ("95% interval", "-", "Paired bootstrap over students, 1,000 resamples (600 per programme)."),
        ("Limitations", None, None),
        ("Untimed courses", "excluded", "Courses with no fixed time (online, TBA) do not affect the weekly timetable."),
        ("Section restrictions", "ignored", "Major-only or year-only sections are treated as open to everyone."),
        ("Sample bias", "first-years", "About half the screenshots are first-years; demand matching fixes course mix, not preferences."),
        ("Coverage", "~93%", "The last seats of each course were too scattered to form clash-free weeks."),
        ("Personal preferences", "not modelled", "Students may prefer gaps (work, clubs); the planner could take preferences as input."),
    ]
    row = 4
    for item, val, why in items:
        if val is None and why is None:
            put(ws, row, 1, item, font=BOLD)
            ws.cell(row=row, column=1).fill = KEY
        else:
            put(ws, row, 1, item)
            put(ws, row, 2, val, None, BLUE)
            c = put(ws, row, 3, why)
            c.alignment = WRAP
        row += 1
    widths(ws, [42, 18, 100])


def sources(wb):
    ws = sheet(wb, "Data sources", "Files, scripts and links (repository kimpasha2008-spec/schedule_maker)")
    header(ws, 3, ["What", "Where", "Notes"])
    items = [
        ("Section timetable, Sem A 2026/27", "data/sections.csv", "From the public CityU Schedule Builder mirror (cityu-schedule.xmzr.dev/courses.json), scraped 23 Aug 2026."),
        ("Course capacity and enrolment", "data/cityuhk_course_offerings_capacity.csv", "AIMS course offerings: cap, available, enrolled estimate."),
        ("Real timetables (transcribed)", "data/real_timetables_transcribed.txt", "One student per line, course/section codes only; no names or IDs."),
        ("Real timetables (resolved)", "data/real_students.csv", "Student id, CRN, course, section."),
        ("Bootstrap + scenarios + planner", "scripts/citywide.py", "python3 scripts/citywide.py --replicates 3 --planner-minutes 6"),
        ("Per-programme analysis", "scripts/citywide_majors.py", "Writes results/explorer/data.json."),
        ("Summary of all runs", "results/citywide_summary.json", "Per population: metrics, intervals, load."),
        ("Every simulated timetable", "results/citywide_students_seed{1,2,3}.json.gz", "Per student and scenario: course -> day bitmasks."),
        ("This workbook", "scripts/build_workbook.py", "Regenerates this file from the results."),
        ("Year 1 CP-SAT model", "scripts/optimize.py, scripts/even_week.py", "Earlier first-year model with OR-Tools CP-SAT."),
        ("Interactive explorer", "https://claude.ai/artifact/5GHA2KVRmxDYbPYpY18gsF", "Per-programme results and before/after weeks (share before sending)."),
        ("Impact report page", "https://claude.ai/artifact/Tx3BiqYczKRGUK8fUWfr4H", "Summary charts with intervals."),
    ]
    row = 4
    for vals in items:
        for j, v in enumerate(vals, 1):
            c = put(ws, row, j, v)
            c.alignment = WRAP
        row += 1
    widths(ws, [34, 52, 90])


def main():
    wb = Workbook()
    overview(wb)
    headline(wb)
    real(wb)
    effects(wb)
    programmes(wb)
    examples(wb)
    populations(wb)
    buildings(wb)
    year1(wb)
    assumptions(wb)
    sources(wb)
    wb.save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
