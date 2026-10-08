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

## Next steps
1. ~~Write a parser for AIMS section pages → `sections.csv`~~ Done via `scripts/build_sections.py` (see update above).
2. Build a synthetic-but-realistic student population from the major headcounts plus Year 1 Sem A course lists.
3. Prototype Stage A + Stage B in OR-Tools CP-SAT on the first-year subset. Report: total gap hours, gap std, max students per slot, room utilisation.
4. Compare against the current real timetable (from AIMS sections) as a baseline.
