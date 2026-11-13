"""Pack results/explorer/data.json into app/explorer.html (the interactive explorer).

Usage: python3 scripts/citywide_majors.py && python3 scripts/build_explorer.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
data = (ROOT / "results/explorer/data.json").read_text()
html = (ROOT / "app/explorer_template.html").read_text().replace("/*DATA*/null", data)
(ROOT / "app/explorer.html").write_text(html)
print(f"app/explorer.html ({len(html) // 1024} KB)")
