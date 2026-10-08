"""Resolve the free-text Year 1 Sem A plans into concrete course lists.

Writes data/curricula_year1_semA.csv: one row per (major, English stream) cohort
with its Year 1 intake and the course codes its students take this semester.

Resolution rules (the source plans are prose, so these are assumptions):
- English: 70% of each intake take GE1401, 30% take LC0200A (EAP1) instead
  (GE1401's timed tutorials only seat 2,350).
- Electives with many options are left out: "Gateway Education course", the
  arts/social-science "College requirement", "only if required" CHIN1001.
  GE1501 is kept only where a plan names it.
- GE1601 is left out: its lectures have no fixed time (online).
- "X / Y" alternatives -> the first option; MA1300 (Enhanced) for Physics,
  Chemistry and Computational Finance so MA1200 demand fits its seats.
- College of Business "3-4 courses chosen from" lists -> 2-4 CB core courses
  per major, chosen so Year 1 demand stays within each course's section caps.
- Courses with no Sem A sections (VM2003, VM2100, SS1024, EN2722, CAH2611,
  CAH2612, COM2118, PIA2105, PIA2107, LW2604A) are dropped; CAH2613 -> CAH2614,
  PIA2400 -> PIA2530.
- Majors with no plan (Criminology and Sociology) borrow Crime Science's plan;
  "Bachelor of Laws (incl. LLB double degrees)" uses the "Bachelor of Laws" plan;
  "BEng Building Services Engineering" uses the Architectural Engineering plan.
- Seat calibration: majors are scaled down until each course's Year 1 demand
  fits within MAX_FILL of its real section seats (column estimated_students
  keeps the pre-calibration number).
"""
import csv
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAJORS = ROOT / "data/cityuhk_ug_students_by_major_estimate.csv"
SECTIONS = ROOT / "data/sections.csv"
OUT = ROOT / "data/curricula_year1_semA.csv"

ENGLISH_LC_SHARE = 0.30
MAX_FILL = 0.90  # Year 1 may use at most this share of a course's seats
CIVIL = ["MA1200", "CS1302", "PHY1201"]
EE = ["MA1200", "CS1302", "GE1354", "EE1001"]
MECH = ["MA1200", "MNE2066", "PHY1101", "MNE2116"]

# Non-English courses for each major (English is added per stream below).
# GE1601 is left out: its lectures have no fixed time (online), so it does not
# affect the weekly timetable.
PLANS = {
    "BBA Accountancy": ["CB2100", "CB2201", "CB2300", "CB2601"],
    "BBA Finance": ["CB2400", "CB2201", "CB2100"],
    "BBA Business Economics": ["CB2201", "CB2400", "CB2500"],
    "BBA Marketing": ["CB2601", "CB2201", "CB2400"],
    "BBA Management": ["CB2201", "CB2601", "CB2400"],
    "BBA Global Business": ["CB2100", "CB2601"],
    "BBA Global Business Systems Management": ["CB2201", "CB2500", "CB2300"],
    "BBA Artificial Intelligence in Business": ["CB2201", "CB2500", "CB2400"],
    "BBA Business Decision Analytics": ["CB2201", "CB2400", "CB2500"],
    "BBA Global Operations Management": ["CB2201", "CB2400", "CB2500"],
    "BSc Computational Finance and Financial Technology": ["CB2400", "CS1102", "MA1300"],
    "BSc Computer Science": ["CS1302A", "MA1508", "CS2115"],
    "BSc Data Science": ["MA1508", "CS1315", "DSC1001"],
    "BSc Data and Systems Engineering": ["MA1508", "CS1315", "DSC1001"],
    "BSc Cybersecurity": ["CS1302A", "MA1508", "CS2115", "CS2117"],
    "BEng Civil Engineering": CIVIL,
    "BEng Building Services Engineering": CIVIL,
    "BSc Architecture and Surveying": CIVIL,
    "BEng Computer and Data Engineering": EE,
    "BEng Electronic and Electrical Engineering": EE,
    "BEng Information Engineering": EE,
    "BEng Microelectronics Engineering": EE,
    "BEng Mechanical Engineering": MECH,
    "BEng Aerospace Engineering": MECH,
    "BEng Nuclear and Risk Engineering": MECH,
    "BEng Materials Science and Engineering": ["CHEM1300", "MA1200", "MSE1001", "PHY1201"],
    "BEng Intelligent Manufacturing Engineering": ["MA1200", "SYE2066", "PHY1201", "GE1501"],
    "BEng Innovation and Enterprise Engineering": ["MA1200", "SYE1001", "PHY1201", "GE2304", "GE1501"],
    "BEng Energy Science and Engineering": ["MA1200", "CHEM1200", "CHEM1300", "SEE1003"],
    "BEng Environmental Science and Engineering": ["MA1200", "CHEM1200", "CHEM1300", "SEE1003"],
    "BSc Environment and Sustainable Business": ["CB2100", "CHEM1300", "MA1200", "SEE1005"],
    "BSc Chemistry": ["MA1300", "CS1102", "CHEM1300", "CSCI1001"],
    "BSc Computing Mathematics": ["GE1501", "MA1400", "CS1302", "MA1502", "CSCI1001"],
    "BSc Physics": ["PHY1101", "CS1302", "CSCI1001", "MA1300"],
    "BEng Biomedical Engineering": ["PHY1201", "CHEM1200", "MA1200", "BME2105"],
    "BSc Biological Sciences": ["CHEM1300", "CHEM1200", "BMS1901", "GE1501"],
    "BSc Biomedical Sciences": ["CHEM1300", "CHEM1200", "BMS1901", "GE1501"],
    "Bachelor of Veterinary Medicine": ["VM2001", "VM2102"],
    "BA English": ["EN2714"],
    "BA Chinese and History": ["CAH2610", "CAH2614"],
    "BA Linguistics and Language Applications": ["LT1101", "GE1501"],
    "BA Media and Communication": ["COM2105"],
    "BA Digital Television and Broadcasting": ["COM2105"],
    "BSocSc International Relations and Global Affairs": ["PIA2050"],
    "BSocSc Public Affairs and Management": ["PIA2307", "PIA2530"],
    "BSocSc Crime Science": ["SS1011", "SS1101"],
    "BSocSc Criminology and Sociology": ["SS1011", "SS1101"],
    "BSocSc Psychology": ["SS1101", "SS1011"],
    "BSocSc Social Work": ["SS1011", "SS1101"],
    "BA Creative Media": ["SM1103A", "SM1701", "SM1702A"],
    "BSc Creative Media": ["SM1701", "SM1702A", "SM2714", "CS1103B"],
    "BAS New Media": ["SM1103A", "SM1701", "SM1702A"],
    "Bachelor of Laws (incl. LLB double degrees)": ["LW2601", "LW2602A", "LW2603A"],
}


def seat_supply():
    """Seats per course = smallest per-type total cap over timed sections."""
    caps = defaultdict(dict)
    with open(SECTIONS, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["day"]:
                caps[r["course"]][r["crn"]] = (r["section"][:1], int(r["cap"]))
    supply = {}
    for course, secs in caps.items():
        by_type = defaultdict(int)
        for kind, cap in secs.values():
            by_type[kind] += cap
        supply[course] = min(by_type.values())
    return supply


def calibrate(intakes, plans, supply):
    """Scale majors down until every course's demand fits MAX_FILL of its seats.

    The intake estimates are rough (+/-30-40%), while section caps are real, so a
    major whose courses are oversubscribed is shrunk by its tightest course.
    """
    scale = {m: 1.0 for m in intakes}
    for _ in range(50):
        demand = defaultdict(float)
        for m, n in intakes.items():
            for c in plans[m]:
                demand[c] += n * scale[m]
        ratio = {c: min(1.0, MAX_FILL * supply[c] / d) for c, d in demand.items()}
        if min(ratio.values()) > 0.999:
            break
        for m in scale:
            scale[m] *= min(ratio[c] for c in plans[m])
    return {m: int(intakes[m] * scale[m]) for m in intakes}


def main():
    supply = seat_supply()
    with open(MAJORS, encoding="utf-8-sig") as f:
        majors = [r for r in csv.DictReader(f) if r["major"]]

    n_lc, intakes, plans = {}, {}, {}
    for m in majors:
        name = m["major"]
        missing = [c for c in PLANS[name] if c not in supply]
        assert not missing, f"{name}: not offered in Sem A: {missing}"
        intake = int(m["est_annual_intake_all_routes"])
        n_lc[name] = round(intake * ENGLISH_LC_SHARE)
        intakes[(name, "GE1401")] = intake - n_lc[name]
        intakes[(name, "LC0200A")] = n_lc[name]
        plans[(name, "GE1401")] = ["GE1401"] + PLANS[name]
        plans[(name, "LC0200A")] = ["LC0200A"] + PLANS[name]
    sized = calibrate(intakes, plans, supply)

    out = []
    for m in majors:
        for english in ("GE1401", "LC0200A"):
            key = (m["major"], english)
            out.append({"college": m["college"], "major": m["major"], "english": english,
                        "students": sized[key], "estimated_students": intakes[key],
                        "courses": " ".join(plans[key])})
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(out[0]))
        w.writeheader()
        w.writerows(out)
    print(f"{len(out)} cohorts, {sum(r['students'] for r in out)} students "
          f"(estimate before seat calibration: {sum(intakes.values())}) -> {OUT}")


if __name__ == "__main__":
    main()
