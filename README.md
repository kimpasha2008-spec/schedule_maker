# CityU timetable planner

Code, data and results behind the report on assigning course sections to City
University of Hong Kong undergraduates (Semester A 2026/27). Class times, rooms
and seat caps never change: the model only decides which lecture, tutorial or
lab section each student takes.

## What is here

| Folder | Contents |
|---|---|
| `data/` | Inputs: section timetable (`sections.csv`), AIMS course capacity and enrolment, 189 anonymised real timetables (`real_timetables_transcribed.txt`, `real_students.csv`), Year 1 curricula |
| `scripts/` | Every step, from raw data to charts and workbooks (see below) |
| `results/` | Model outputs: summaries (`*.json`), every simulated timetable (`*.json.gz`), Excel workbooks (`*.xlsx`) |
| `app/` | Interactive pages: the Year 1 student explorer (`index.html`) and the programme explorers (`explorer.html`, `explorer_compact.html`) |

Real timetables keep course and section codes only; no names, student numbers
or screenshots are stored.

## Two planner objectives

| | Even week (`--objective even`) | Fewer days (`--objective compact`) |
|---|---|---|
| Goal | Few idle hours, classes spread evenly Mon-Fri | Few idle hours, as few days on campus as possible |
| Score per student | 15 x gap hours + sum over Mon-Fri of abs(5 x day hours - week hours) + 5 x Saturday hours | 15 x gap hours + 30 x days on campus + 5 x hours of any day beyond 8 h + 5 x Saturday hours |
| Results | `results/citywide_summary.json`, `cityu_timetable_key_results.xlsx` | `results/citywide_compact_summary.json`, `cityu_timetable_key_results_compact.xlsx` |

Both also add 150 per course a student cannot take, and a building-load term:
each hour in a building costs (students already in class there) / 1,000.

## Parameters

### City-wide model (`scripts/citywide.py`)

| Parameter | Value | Meaning |
|---|---|---|
| `GAP_W` | 15 | Cost of one idle hour between classes |
| `MISS` | 150 | Cost of a course left out (in practice never accepted) |
| `SAT_W` | 5 | Cost per Saturday class hour |
| `DAY_W` | 30 | Fewer-days objective: cost of one day on campus (= 2 idle hours) |
| `LONG_DAY`, `LONG_W` | 8 h, 5 | Fewer-days objective: cost per hour of a day's span beyond 8 hours |
| `LOAD_SCALE` | 1,000 | Building-load cost = students in that building-hour / 1,000 |
| `KEEP_AFFINITY` | 4 | Bootstrap: a cloned student's own course is 4x as likely to be kept as swapped |
| `CROSS_SUBJECT` | 0.1 | Bootstrap: weight of same-level courses from other subjects when swapping |
| `MIN_SHAPE` | 0.75 | Bootstrap: a clone keeps at least 75% of its donor's number of courses |
| `TRIES` | 6 | Bootstrap: course picks tried per timetable slot |
| `MAX_COMBOS` | 600 | Most lecture/tutorial/lab combinations considered per course |
| Populations | 3 (seeds 1-3) | Independent bootstrap populations; results are their mean |
| Planner time | 6 min per population | Local search: worst timetables first, own re-plans and seat swaps |
| Bootstrap intervals | 1,000 resamples (600 per programme) | Paired over students, 95% |
| Regular week | meetings held in 7+ teaching weeks | Only these shape the weekly timetable |
| Programme groups | min. 150 students | Smaller groups are merged into "Other" |

Enrolment targets are the AIMS undergraduate enrolment (cap minus seats
available) of the 740 undergraduate courses with fixed meeting times.

### Year 1 prototype (`scripts/optimize.py`, `scripts/even_week.py`)

| Parameter | Value |
|---|---|
| Weights: idle, balance, peak, late, lunch, fairness | 3, 3, 1, 1, 1, 100 |
| Even-week LNS: fairness, building peaks, gap weight | 100, 10, 3 |
| Block size (students sharing a timetable) | 12 |
| Max share of seats for Year 1 | 95% |
| LNS neighbourhood, step time | 16 blocks, 10 s |
| Solver | OR-Tools CP-SAT 9.15 |

The weights are design choices, not values estimated from data. A sensitivity
check (rerunning with each weight halved and doubled) is the natural next step
if the report needs one.

## Reproduce

```bash
pip install -r requirements.txt   # ortools, openpyxl
python3 scripts/read_screenshots.py                     # transcribed timetables -> data/real_students.csv
python3 scripts/citywide.py --replicates 3 --planner-minutes 6                       # even week
python3 scripts/citywide.py --objective compact --seed 1 --replicates 1 \
    --summary results/citywide_compact_summary.json     # fewer days (repeat for seeds 2, 3)
python3 scripts/citywide_majors.py && python3 scripts/build_explorer.py              # programme explorer
TAG=_compact python3 scripts/citywide_majors.py && TAG=_compact python3 scripts/build_explorer.py
python3 scripts/citywide_report.py                      # report data files
python3 scripts/build_workbook.py                       # full workbook
python3 scripts/build_key_results.py                    # key results (even week)
TAG=_compact python3 scripts/build_key_results.py       # key results (fewer days)
```

One population takes about 7 minutes. The Year 1 model: `python3 scripts/optimize.py`
then `python3 scripts/even_week.py --minutes 25`.

## Headline results (all ~14,600 undergraduates, per student per week)

| | Today (random section picks) | Even-week planner | Fewer-days planner |
|---|---|---|---|
| Idle gap hours | 3.01 | 1.13 | 1.26 |
| Days on campus | 4.02 | 4.39 | 3.59 |
| Longest day | 7.8 h | 6.4 h | 7.5 h |
| Students with 3+ gap hours | 51% | 19% | 20% |

For the 183 students with real timetables, gap hours fall from 3.84 to 1.25
(even week) or 1.40 (fewer days). See `HANDOFF.md` for the full history.
