"""Short workbook with only the results the report needs.

Usage: python3 scripts/build_key_results.py   (after scripts/build_workbook.py inputs exist)
"""
import json
import os
import statistics
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

ROOT = Path(__file__).resolve().parent.parent
TAG = os.environ.get("TAG", "")  # "_compact": planner minimises days on campus
OUT = ROOT / f"results/cityu_timetable_key_results{TAG}.xlsx"
RUNS = json.loads((ROOT / f"results/citywide{TAG}_summary.json").read_text())
EXP = json.loads((ROOT / f"results/explorer{TAG}/data.json").read_text())
F = "Arial"
BODY, BOLD, BLUE = Font(name=F), Font(name=F, bold=True), Font(name=F, color="0000FF")
HEAD, TITLE, NOTE = Font(name=F, bold=True, color="FFFFFF"), Font(name=F, bold=True, size=14, color="0B2A5E"), Font(name=F, italic=True, size=9, color="4F6684")
HFILL, KEY = PatternFill("solid", fgColor="1A5FD0"), PatternFill("solid", fgColor="E3EEFD")
LINE = Border(bottom=Side(style="thin", color="D5E1F0"))


def avg(v):
    return round(statistics.fmean(v), 4)


def share(group, scen, lo, hi):
    """Share of students whose days on campus is in [lo, hi)."""
    hist = group["days_hist"][scen]
    return round(sum(hist[lo:hi]) / sum(hist), 4)


def new(wb, name, title, note=None, first=False):
    ws = wb.active if first else wb.create_sheet(name)
    ws.title = name
    ws.sheet_view.showGridLines = False
    ws["A1"], ws["A1"].font = title, TITLE
    if note:
        ws["A2"], ws["A2"].font = note, NOTE
    return ws


def table(ws, row, head, rows, fmts, widths):
    for j, h in enumerate(head, 1):
        c = ws.cell(row=row, column=j, value=h)
        c.font, c.fill, c.alignment = HEAD, HFILL, Alignment(wrap_text=True, vertical="center")
    ws.row_dimensions[row].height = 30
    for i, vals in enumerate(rows, row + 1):
        for j, v in enumerate(vals, 1):
            v = v.replace("{r}", str(i)) if isinstance(v, str) else v
            c = ws.cell(row=i, column=j, value=v)
            c.border = LINE
            c.font = BODY if (j == 1 or (isinstance(v, str) and v.startswith("="))) else BLUE
            if fmts[j - 1]:
                c.number_format = fmts[j - 1]
    for j, w in enumerate(widths, 1):
        ws.column_dimensions[chr(64 + j)].width = w
    return row + len(rows) + 1


def main():
    wb = Workbook()
    o, r = EXP["overall"], EXP["real"]
    rs = lambda k, m: avg(x["real_students"][k][m] for x in RUNS)
    al = lambda k, m: avg(x["all_students"][k][m] for x in RUNS)

    ws = new(wb, "Key results", "Key results: fewer days on campus, CityU Semester A 2026/27",
             "Planner goal: as few campus days as possible (a day costs as much as two idle hours; days over 8 h penalised). "
             "Class times, rooms and seat caps unchanged. Per student per week.", first=True)
    ws["A4"], ws["A4"].font = "1. The 183 real students (timetables from screenshots), same courses", BOLD
    fm = [None, "0.00", "0.00", "0.00", "0.0%"]
    nxt = table(ws, 5, ["Metric", "Real timetable", "With planner", "Change", "Change (%)"], [
        ["Days on campus a week", rs("actual", "days_on_campus"), rs("planner", "days_on_campus"), "=C{r}-B{r}", "=(C{r}-B{r})/B{r}"],
        ["Idle gap hours a week", rs("actual", "gap_hours"), rs("planner", "gap_hours"), "=C{r}-B{r}", "=(C{r}-B{r})/B{r}"],
        ["Longest day on campus (h)", rs("actual", "longest_day"), rs("planner", "longest_day"), "=C{r}-B{r}", "=(C{r}-B{r})/B{r}"],
        ["Share with 3+ gap hours", rs("actual", "share_with_3h_plus_gaps"), rs("planner", "share_with_3h_plus_gaps"), "=C{r}-B{r}", "=(C{r}-B{r})/B{r}"],
    ], fm, [40, 18, 18, 14, 14])
    for c in "BCD":
        ws[f"{c}9"].number_format = "0.0%"
    ci = [x["real_planner_vs_actual"]["days_on_campus"] for x in RUNS]
    ws.cell(row=nxt, column=1, value=f"95% interval for the change in days: {min(v[1] for v in ci):.2f} to {max(v[2] for v in ci):.2f} days a week").font = NOTE

    row = nxt + 2
    ws.cell(row=row, column=1, value=f"2. All CityU undergraduates (about {o['students']:,}, bootstrapped from the real students)").font = BOLD
    nxt = table(ws, row + 1, ["Metric", "Today (random picks)", "With planner", "Change", "Change (%)"], [
        ["Days on campus a week", al("random", "days_on_campus"), al("planner", "days_on_campus"), "=C{r}-B{r}", "=(C{r}-B{r})/B{r}"],
        ["Idle gap hours a week", al("random", "gap_hours"), al("planner", "gap_hours"), "=C{r}-B{r}", "=(C{r}-B{r})/B{r}"],
        ["Longest day on campus (h)", al("random", "longest_day"), al("planner", "longest_day"), "=C{r}-B{r}", "=(C{r}-B{r})/B{r}"],
        ["Share with 3+ gap hours", al("random", "share_with_3h_plus_gaps"), al("planner", "share_with_3h_plus_gaps"), "=C{r}-B{r}", "=(C{r}-B{r})/B{r}"],
        ["Share missing a course", al("random", "share_missing_a_course"), al("planner", "share_missing_a_course"), "=C{r}-B{r}", None],
        ["Share on campus 5+ days a week", share(o, "random", 5, 7), share(o, "planner", 5, 7), "=C{r}-B{r}", "=(C{r}-B{r})/B{r}"],
        ["Share on campus 3 days or fewer", share(o, "random", 0, 4), share(o, "planner", 0, 4), "=C{r}-B{r}", "=(C{r}-B{r})/B{r}"],
    ], fm, [40, 18, 18, 14, 14])
    for rr in (row + 5, row + 6, row + 7, row + 8):
        for c in "BCD":
            ws[f"{c}{rr}"].number_format = "0.0%"
    ws.cell(row=nxt, column=1, value=f"95% interval for the change in days: {o['ci_days'][1]:.2f} to {o['ci_days'][2]:.2f} days a week.").font = NOTE

    row = nxt + 2
    ws.cell(row=row, column=1, value="3. Why a planner and not better registration").font = BOLD
    nxt = table(ws, row + 1, ["Metric", "First come, best pick", "With planner", "Change", None], [
        ["Days on campus a week", al("fcfs", "days_on_campus"), al("planner", "days_on_campus"), "=C{r}-B{r}", None],
        ["Idle gap hours a week", al("fcfs", "gap_hours"), al("planner", "gap_hours"), "=C{r}-B{r}", None],
        ["Share missing a course", al("fcfs", "share_missing_a_course"), al("planner", "share_missing_a_course"), "=C{r}-B{r}", None],
    ], [None, "0.00", "0.00", "0.00", None], [40, 18, 18, 14, 14])
    for c in "BCD":
        ws[f"{c}{row + 4}"].number_format = "0.0%"
    ws.cell(row=row + 1, column=5).fill = PatternFill(None)
    ws.cell(row=nxt, column=1, value=f"Students picking their own best timetable leave about {al('fcfs', 'share_missing_a_course'):.0%} without a course they need.").font = NOTE

    ws2 = new(wb, "By programme", "Days on campus by programme (all undergraduates, today vs planner)",
              "Programme inferred from the subject each student takes most. Sorted by reduction in days.")
    progs = sorted(EXP["programmes"].items(), key=lambda kv: kv[1]["planner"]["days"] - kv[1]["random"]["days"])
    rows = [[n, g["students"], g["random"]["days"], g["planner"]["days"], "=D{r}-C{r}", "=(D{r}-C{r})/C{r}",
             g["random"]["gap"], g["planner"]["gap"], g["random"]["long"], g["planner"]["long"]]
            for n, g in progs if n != "First-year general education"]
    table(ws2, 4, ["Programme", "Students", "Days today", "Days planner", "Change", "Change (%)",
                   "Gap h today", "Gap h planner", "Longest day today", "Longest day planner"], rows,
          [None, "#,##0", "0.00", "0.00", "0.00", "0.0%", "0.00", "0.00", "0.0", "0.0"],
          [34, 11, 11, 12, 10, 11, 11, 12, 15, 16])
    ws2.freeze_panes = "B5"

    ws3 = new(wb, "Caveats", "Caveats to state in the report")
    for i, t in enumerate([
        "Programmes are inferred from courses taken; the populations carry no declared majors.",
        "About half of the 183 real students are first-years; demand matching corrects course mix, not preferences.",
        "About 7% of AIMS seats could not be filled in the simulation (scattered last seats).",
        "Courses without fixed times and major-only section restrictions are left out.",
        "Students' own preferences (e.g. wanting gaps for work) are not modelled.",
        "Figures average 3 bootstrap populations; intervals are paired bootstrap over students.",
    ], 4):
        c = ws3.cell(row=i, column=1, value=f"{i - 3}. {t}")
        c.font, c.alignment = BODY, Alignment(wrap_text=True)
    ws3.column_dimensions["A"].width = 110
    wb.save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
