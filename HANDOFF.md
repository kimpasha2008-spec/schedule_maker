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

### Scraping AIMS with Bright Data (user's request)
The user wants the section data scraped from AIMS with **Bright Data** for more precise, complete data (every course → every section: CRN, type, day, time, venue, cap, avail).

Suggested setup:
- Use Bright Data's **Browser API (Scraping Browser)** driven by Playwright or Puppeteer, because AIMS pages need a real logged-in browser session. Load the Bright Data plugin skills (`bright-data-best-practices`, `scraper-builder`) before writing code. The API key goes in the `BRIGHTDATA_API_KEY` env var, never in the repo.
- **Login:** the user logs in to AIMS themselves (EID, password, 2FA) in the controlled browser, then the script takes over the authenticated session. Never hard-code or store the EID or password, and never commit cookies.
- **Keep one sticky session and one IP for the whole run.** AIMS is a single authenticated session; rotating residential IPs mid-session will likely log the user out or look like account compromise to CityU security.
- **Crawl politely and read-only.** Go Master Class Schedule → department → course → sections. Wait 1–3 s between requests, cache every page to `raw/` so nothing is fetched twice, and never click register/add/drop.
- **Output:** `sections.csv` (term, subject, course, CRN, section, type, day, start, end, venue, cap, avail, waitlist, instructor if shown). Then validate it against `cityuhk_course_offerings_capacity.csv`: the section caps for each course should sum to that course's Cap.

Honest caveat for the user: Bright Data's main strengths (IP rotation, CAPTCHA and bot-block bypass) target public sites. They don't add precision on an authenticated portal like AIMS. A plain local Playwright script using the user's own logged-in browser gets exactly the same data, for free and with less risk. Bulk automated access may also conflict with CityU's IT acceptable-use rules, so it's worth checking first. Either way, the account and the decision are the user's.

### Update: section data obtained (no AIMS login needed)
`https://cityu-schedule.xmzr.dev/courses.json` (public mirror of the AIMS Master Class Schedule) was fetched through the Bright Data MCP (`scrape_batch`) and saved as `data/raw/xmzr_courses_semA_2026-27_scraped_2026-08-23.json`. `scripts/build_sections.py` flattens it into `data/sections.csv`. The output has one row per weekly meeting with these columns: term, course, CRN, section, type, day, start, end, venue, instructor, dates, cap, avail, restrict and note.
- 1,585 courses, 5,056 sections, 6,080 meeting rows and 207 distinct venues. All 18 "minimum subset" first-year courses are present.
- `avail` is from the mirror's scrape on 23 Aug 2026, so it's older than the AIMS paste. Use it for timing and caps, not current seat counts.
- Section caps sum to the AIMS course Cap for 1,265 courses. 307 differ, likely because caps changed after 23 Aug, and 13 courses are missing from the capacity file.
- 581 meetings have no fixed day or time (TBA or arranged), including 30 of GE1601's 31 lecture sections. These are flagged in `note`.
- Room capacities can now be estimated as the largest section cap booked into each venue.

## Prototype results (Year 1, Sem A 2026/27)
Run: `pip install -r requirements.txt`, then `python3 scripts/build_sections.py`, `python3 scripts/build_curricula.py` and `python3 scripts/optimize.py --time-limit 300`. The full run takes about 15 minutes on 4 cores.

**Population** (`data/curricula_year1_semA.csv`): 2,796 first-years in 104 cohorts (52 majors × GE1401 or LC0200A English stream), taking 58 courses across 586 candidate sections. The free-text plans were resolved by explicit rules, documented at the top of `scripts/build_curricula.py`. Intakes were then scaled down so each course's Year 1 demand fits within 90% of its real seats. For example, the estimates put more EE students into EE1001 than it seats.

**Model** (`scripts/optimize.py`): students move in blocks of ≤12 from the same cohort. Blocks of 20 couldn't be packed into the 20–25-seat GE1401 tutorials. Each block takes one section per course and section type, linked sections stay together (CA1 with TA*), and seats are capped. Clashes are checked week by week, because many lectures and tutorials share a slot in different weeks. Stage A moves the meetings of the sections Year 1 uses, keeping their rooms, length and weeks. It never double-books a room or instructor against any other course's bookings. Objective: idle hours + 3 × peak students on campus + 50 × the worst block's idle hours, plus a Stage A penalty for Saturday and after-19:00 classes.

| per student, averaged over 13 teaching weeks | baseline: real times, best sectioning | optimized |
|---|---|---|
| idle hours between classes / week (mean) | 0.36 | **0.24** (−33%) |
| idle hours std / max | 0.82 / 5.6 | 0.72 / 4.6 |
| students with ≥3 idle h / week | 77 | 68 |
| days on campus / week | 4.02 | 3.95 |
| peak Year 1 students on campus in one hour | 1,160 | **1,020** (−12%) |
| evening or Saturday class hours / week | 0.46 | **0.27** (−41%) |
| student clash hours | 0 | 0 |
| room / instructor double-bookings introduced | – | 0 / 0 (13 existing instructor overlaps resolved) |

Stage A moved 200 of the 615 meetings it could move. The new times are in `results/optimized_section_times.csv`, block timetables are in `results/*_block_timetables.csv`, and metrics are in `results/summary.json`. CP-SAT stopped at the time limit in every stage (FEASIBLE, not proven optimal), so longer runs may do a little better.

**Caveats:**
- The baseline is generous to the real timetable. It gives students the *best possible* sections on the real times, while real students register first-come-first-served, so real gaps are larger.
- Moving a section also moves the non-Year-1 students in it, whose timetables aren't modelled.
- Section restrictions ("only for Major/Programme …") and Gateway and college-requirement electives are ignored.
- Rooms stay as booked; reassigning rooms would add freedom.
- GE1601 is excluded because its lectures have no fixed time.
- The source data itself has 117 room-hours and 227 instructor-hours where meetings with different start times overlap. These are probably combined classes or data quirks, and the optimizer leaves them alone.

## Next steps
1. ~~Write a parser for AIMS section pages → `sections.csv`~~ Done via `scripts/build_sections.py` (see update above).
2. ~~Build a synthetic student population~~ Done: `scripts/build_curricula.py`.
3. ~~Prototype Stage A + Stage B in CP-SAT~~ Done: `scripts/optimize.py` (results above).
4. ~~Compare against the current real timetable~~ Done (baseline column above).
5. Make the baseline realistic: simulate first-come-first-served registration instead of optimal sectioning.
6. Add room reassignment (room capacities estimated as the largest cap booked into each room) and respect major/programme restrictions.
7. Model the other years (at least their fixed classes) so moving shared sections doesn't hurt them.
8. Tune the weights (gaps vs. peak load vs. days on campus) with the user and show the trade-off curve.
