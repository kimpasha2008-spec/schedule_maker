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
**Direction (user's decision, 9 Oct):** class times stay exactly as published. The product assigns students to sections (registration helper), not a timetable redesign. Retiming is kept behind `--retime` for reference.

Run: `pip install -r requirements.txt`, then `python3 scripts/build_sections.py`, `python3 scripts/build_curricula.py`, `python3 scripts/optimize.py --time-limit 300` (about 7 min), and finally `python3 scripts/build_app.py`. The app link is shared as "anyone with the link" (set by the user).

**App:** `app/index.html`, built from `app/template.html`. It's a single page with the summary, a chart of gap hours, and any student's week under first-come-first-served next to the planner's assignment. Published privately at https://claude.ai/artifact/N9cvAg2GNrgcGNaWB4J8YR.

**Population** (`data/curricula_year1_semA.csv`): 2,796 first-years in 104 cohorts (52 majors × GE1401 or LC0200A English stream), taking 58 courses across 586 candidate sections. Plans were resolved by the rules at the top of `scripts/build_curricula.py`, and intakes were scaled so each course's Year 1 demand fits 90% of its real seats.

**Comparison** (all on the published times, same 2,796 students, registration order seed 1):
- **Random clash-free:** students register one at a time; each gets a random clash-free timetable from the seats still open. If no clash-free option is left, they take the least-clashing one.
- **First come, first served:** the same, but each student picks their own best timetable, using the planner's objective for one student. If no clash-free option is left, they accept the smallest clash.
- **First come, no clashes:** the same, but a student who can't fit a clash-free timetable drops as few courses as needed. Added with `python3 scripts/optimize.py --only-no-clash`, which keeps the saved results and merges in this scenario.
- **Planner:** assigns everyone at once, in blocks of ≤12 from the same cohort.

**Planner priorities (user's weights, 9 Oct):**
- **Weighted goals:** gaps 3 (per student-hour), balanced days 3 (longest − shortest day on campus, per student-hour; a linear stand-in for the std of daily hours), crowding 1 (per student in the busiest hour), late classes 1 (per student-hour from 19:00), lunch break 1 (per day with class at both 12:00 and 13:00), fairness 100 (per gap hour of the worst-off block).
- **Hard rules:** every course, no clashes, seat caps, and linked sections.
- **Seats for other years:** first-years may take at most a quota of each course and section type. Other years keep what they really enrolled (AIMS enrolment − Year 1 demand), capped so Year 1 fits within 95% of seats. That holds back 6,267 of the 7,578 seats; per-course detail is in `results/seats_kept_for_other_years.csv`. All three scenarios use the same quotas.

| per student, averaged over 13 teaching weeks | random clash-free | first come, first served | first come, no clashes | planner |
|---|---|---|---|---|
| gap hours / week (mean) | 3.01 | 0.41 | **0.40** | 0.47 |
| gap hours max | 19.8 | 6.9 | 6.9 | **5.9** |
| students with ≥3 gap hours / week | 1,359 | 97 | 98 | **72** |
| std of daily hours on campus | 1.95 | 0.95 | 0.95 | **0.91** |
| longest day (hours) | 7.3 | 4.9 | 4.9 | **4.8** |
| class hours after 19:00 / week | 0.21 | 0.12 | 0.12 | **0.10** |
| days without lunch break / week | 1.41 | **1.25** | **1.25** | 1.28 |
| student clash hours over the term | 169 | 99 | **0** | **0** |
| students who had to drop a course | 0 | 0 | 11 | **0** |
| peak first-years on campus in one hour | 1,470 | 1,368 | 1,368 | **1,213** |

The planner beats random on everything. Against an idealised first come, first served, it wins on clashes, the worst-off students, balanced days, late classes and crowding, and loses slightly on mean gaps and lunch breaks. CP-SAT is far from optimal on this model: objective 23,556 against a bound of 6,891 after 900 s, warm-started. Solving it better (next step 7) is the main lever left. Run: `python3 scripts/optimize.py --time-limit 900 --hint <previous planner_block_timetables.csv>`.

**Even-week planner (current, 9 Oct):** `python3 scripts/even_week.py --minutes 25`. This is the version the app shows.
- **Goal (user's direction):** minimise gaps, spread each student's class hours evenly over Mon–Fri, and be fair.
- **Block score:** 15 per gap hour + 5 per hour a weekday is off the even Mon–Fri split, with Saturday class hours counting in full. Objective = Σ students × score + 100 × the worst block's score.
- **Hard rules:** the same as before, including other-year seat quotas.
- **Method:** large-neighbourhood search. Each step frees 16 blocks (those sharing one course, plus the 3 worst blocks), keeps everyone else fixed, and re-solves with CP-SAT for 10 s. A change is kept only if the total falls. It starts from the previous planner timetable and plateaued after about 250 of 267 steps.
- **Comparison:** baselines are the saved registrations, with metrics recomputed.

| per student, averaged over 13 weeks | random clash-free | first come | first come, no clashes | even-week planner |
|---|---|---|---|---|
| planner score: total (lower is better) | 278,571 | 111,028 | 110,840 | **89,022** |
| planner score: worst group | 342 | 111 | 111 | **64** |
| unevenness across Mon–Fri (std of class hours) | 1.95 | 1.51 | 1.51 | **1.24** |
| gap hours / week | 3.01 | 0.41 | **0.40** | 0.47 |
| students with ≥3 gap hours / week | 1,359 | 97 | 98 | **93** |
| longest day (hours) | 7.3 | 4.9 | 4.9 | **4.6** |
| days on campus / week | **3.8** | 4.2 | 4.2 | 4.5 |
| clash hours over the term / students dropping a course | 169 / 0 | 99 / 0 | 0 / 11 | **0 / 0** |
| peak first-years on campus | 1,470 | 1,368 | 1,368 | **1,340** |
| class hours after 19:00 / days without lunch | 0.21 / 1.41 | **0.12 / 1.25** | **0.12 / 1.25** | 0.18 / 1.50 |

On the combined goal the planner is 20% better than first come and 42% better for the worst-off group. It trades a little average gap time (0.47 vs 0.41 h) for a much more even week, and it is the only scenario with neither clashes nor dropped courses. Lunch, late classes and crowding are no longer optimised, only measured. The earlier weighted planner is still in `scripts/optimize.py`.

**Caveats:**
- The simulated students are optimal myopic registrants. Real students also weigh friends, instructors and lunch, and they register in priority rounds, not in random order.
- Section restrictions ("only for Major/Programme …") are ignored, and the Gateway and college-requirement electives are left out.
- Other years' students aren't modelled, but they also hold seats in these sections.
- The planner puts each student in a block of ≤12 classmates who share a timetable. Assigning individuals could do slightly better.

## Next steps
1. ~~Write a parser for AIMS section pages → `sections.csv`~~ Done via `scripts/build_sections.py` (see update above).
2. ~~Build a synthetic student population~~ Done: `scripts/build_curricula.py`.
3. ~~Prototype Stage A + Stage B in CP-SAT~~ Done: `scripts/optimize.py` (results above).
4. ~~Compare against the current real timetable~~ Done (baseline column above).
5. ~~Simulate first-come-first-served registration~~ Done (`first_come_first_served` in `scripts/optimize.py`).
6. Respect major/programme section restrictions (parse the `restrict` column).
7. Solve the planner better: decompose (large-neighbourhood search over one major or a few blocks at a time) so it gets close to optimal, then tune the weights.
8. Add student preferences: no classes before X, days off, keep friends together.
9. Model other years' seat use in shared sections.
10. Tune the weights (gaps vs. peak load vs. days on campus) and show the trade-off.
