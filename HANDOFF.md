# CityUHK Timetable Optimizer — Handoff

Context carried over from a Claude chat (8 Oct 2026). Start a Claude Code session in this folder and say:
"Read HANDOFF.md and continue."

## Goal
Build an optimizer ("AI") that creates timetables for CityUHK undergraduates:
1. Assign students to class sections so the **gaps between their classes are minimal** (minimise total idle time per student per day, and its standard deviation for fairness).
2. Keep **campus load even** across the week (minimise peak / variance of students on campus per time slot — not all ~12k undergrads at once).
3. **Manage classes sensibly**: balanced section sizes, rooms matched to section size, no room/instructor double-booking.

Hard constraints: no student clashes, room not double-booked, room/section capacity respected, every student gets every required course.

## Agreed approach
- This is the university course timetabling + student sectioning problem. Use optimisation (Google OR-Tools CP-SAT), not ML.
- Decompose for scale:
  - Stage A: place sections into time slots and rooms, treating each major's Year 1 cohort as one group (curricula).
  - Stage B: assign individual students to sections, given fixed times.
- Goals 1 and 2 conflict (compact days vs. spread load), so use a weighted objective.
- Time grid: CityU classes run in 50-minute blocks starting on the hour, Mon–Fri 09:00–21:50 and Sat 09:00–18:50. Seminars are often 3-hour blocks; lecture theatres are used in the evening (19:00–21:50).

## Data files in this folder
| File | What it is | Reliability |
|---|---|---|
| `cityuhk_course_offerings_capacity.csv` | All 1,591 courses offered this term, parsed from the user's AIMS Master Class Schedule paste: unit, subject, code, title, credits, level codes (B = bachelor, P = taught PG, R/D = research), **Cap**, **Avail**, enrolled estimate (Cap − Avail), fill rate. `open_to_undergrads` flag. | Real data (course-level totals, not per section) |
| `aims_course_offerings_raw.txt` | The original AIMS paste (tab-separated, per department). | Raw source |
| `cityuhk_ug_students_by_major_estimate.csv` | Estimated undergrad headcount per major (52 majors), scaled to the official 12,361 UG total (2024/25 annual report). Some majors anchored on 2026 JUPAS places. | Estimate (±30–40% for unanchored rows) |
| `cityuhk_year1_semA_schedule_by_major.csv` | Recommended Year 1 Semester A courses for 53 majors, with source links and confidence grade A–D. | A/B = official plans; C/D = partial |
| `cityuhk_teaching_rooms.csv` | 118+ central teaching rooms by building (Yeung, Li Dak Sum, Lau Ming Wai, CMC). Capacities only known for 5 rooms (LAU 6-207=57, 6-208=65, 7-207=37, 7-208=52, 14-282=26). Official range is 20–300 seats. | Real list, capacities mostly missing |
| `cityuhk_pg_sem_a_2026_room_timetable.csv` | Real Sem A 2026/27 room/time arrangement for 110 postgraduate courses (167 weekly meetings, 78 rooms), from the SGS cross-institutional timetable. | Real, PG only |

## Key findings so far
- UG-open courses: 843, total UG seat cap 108,698, about 80,570 taken (~74% full), ≈ 6.5 registrations per undergrad.
- GE1401 University English has ~3,007 enrolled, matching the ~3,000 first-year intake.
- Largest first-year courses: GE1601 (3,428), GE1401 (3,007), PED1305 (2,692), GE1501 (1,314), CB2201 (1,135), LC0200A (1,125), CB2200 (941), MA1200 (854).

## Missing (blocks the real optimizer)
**Section-level data**: CRN, section (lecture/tutorial/lab), day, time, venue and section cap for each course.
- Source: AIMS Master Class Schedule. Clicking a course shows its sections. The user can copy-paste these pages into a text file.
- Alternative: cityu-schedule.xmzr.dev loads the full catalogue as JSON in the browser. Save it from DevTools → Network.
- Minimum useful subset: big first-year courses: GE1401, GE1501, GE1601, PED1305, LC0200A, MA1200, CS1302, CS1315, MA1508, PHY1201, CHEM1300, CB2100, CB2200, CB2201, CB2300, CB2400, CB2500, CB2601.
- Room capacities can be estimated as the largest section cap ever booked into a room.
- Don't put the user's EID or password anywhere. If browsing AIMS, the user logs in themselves; read-only, normal browsing pace.

## Next steps
1. Write a parser for pasted AIMS section pages → `sections.csv` (course, CRN, type, section, day, start, end, room, cap, avail).
2. Build a synthetic-but-realistic student population from the major headcounts plus Year 1 Sem A course lists.
3. Prototype Stage A + Stage B in OR-Tools CP-SAT on the first-year subset. Report: total gap hours, gap std, max students per slot, room utilisation.
4. Compare against the current real timetable (from AIMS sections) as a baseline.
