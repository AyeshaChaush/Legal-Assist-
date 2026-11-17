import json, shutil, tempfile
from pathlib import Path

import compare_law_versions as cv

# ---- synthetic Act text: a table of contents, then the body --------------------
TEXT = """THE TEST ACT, 2023
ARRANGEMENT OF SECTIONS
SECTIONS
1. Short title.
2. Definitions.
3. Offences.
3A. Special offences.
4. Punishment.
1
CHAPTER I
PRELIMINARY
1. Short title.—This Act may be called the Test Act, 2023.
2. Definitions.—In this Act, unless the context otherwise requires,—
1. "court" means a court of ordinary criminal jurisdiction;
2. "person" includes a company.
3. Offences.—Whoever does the prohibited act shall be punished with imprisonment up to three
years.
3A. Special offences.—Whoever does the prohibited act with a weapon shall be punished
with imprisonment up to seven years.
4. Punishment.—The punishment under this Act shall be rigorous.
7
THE SCHEDULE
1. Classification of offences listed below.
"""

secs, warns = cv.split_sections(TEXT)
nums = [s["number"] for s in secs]
assert nums == ["1", "2", "3", "3A", "4"], nums           # TOC skipped, sub-items "1." "2." not mistaken for sections
assert secs[0]["title"] == "Short title"
assert "Classification" not in secs[-1]["text"]           # schedule cut off the last section
assert "7" not in secs[-1]["text"].split()[-1:]           # stray page number removed
assert not warns, warns

# ---- stored JSON: section 2 differs, section 5 not in PDF, 3A not stored -------
stored_rows = [
    {"act_name": "Test Act, 2023", "section_number": "1", "section_title": "Short title",
     "text": "This Act may be called the Test Act, 2023."},
    {"act_name": "Test Act, 2023", "section_number": "2", "section_title": "Definitions",
     "text": 'In this Act, unless the context otherwise requires,— 1. "court" means a revenue court; 2. "person" includes a company.'},
    {"act_name": "Test Act, 2023", "section_number": "3", "section_title": "Offences",
     "text": "Whoever does the prohibited act shall be punished with imprisonmentup to three years."},  # spacing glitch only
    {"act_name": "Test Act, 2023", "section_number": "4", "section_title": "Punishment",
     "text": "The punishment under this Act shall be rigorous."},
    {"act_name": "Test Act, 2023", "section_number": "5", "section_title": "Repealed", "text": "Repealed."},
]
tmp = Path(tempfile.mkdtemp())
jp = tmp / "stored.json"
jp.write_text(json.dumps(stored_rows), encoding="utf-8")
stored = cv.load_stored(jp)

res = cv.compare(secs, stored)
assert res["unchanged"] == ["1", "3", "4"], res          # spacing glitch is ignored
assert [n for n, _ in res["changed"]] == ["2"], res      # "ordinary criminal" vs "revenue"
assert res["new"] == ["3A"] and res["missing"] == ["5"], res
snip = cv.diff_snippet(stored["2"], secs[1])
assert any("revenue" in d and "ordinary" in d for d in snip), snip

# ---- dict-shaped JSON and duplicate entries ------------------------------------
jp2 = tmp / "dict.json"
jp2.write_text(json.dumps({"sections": stored_rows + [dict(stored_rows[0], text="More text.")]}), encoding="utf-8")
assert "More text." in cv.load_stored(jp2)["1"]["text"]

# ---- full path with a real PDF (reportlab) -------------------------------------
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
pdf = tmp / "act.pdf"
c = canvas.Canvas(str(pdf), pagesize=A4)
y = 800
for line in TEXT.splitlines():
    c.setFont("Helvetica", 10); c.drawString(40, y, line.replace("—", "-").replace("—", "-")); y -= 14
    if y < 60:
        c.showPage(); y = 800
c.save()
raw = cv.extract_text(pdf)
assert "Short title" in raw

# CLI wiring with a config, state-less run, report file
cfg = tmp / "law_sources.json"
cfg.write_text(json.dumps({"acts": [{"id": "T", "name": "Test", "pdf_url": "x", "json_path": str(jp)}]}))
result, sections, stored2, warnings, out = cv.run("T", str(pdf), None, cfg, tmp / "upd")
assert out.exists() and "Law comparison: T" in out.read_text(encoding="utf-8")
assert len(sections) >= 4                                   # ASCII dash in the PDF: headings still found

# pending-file lookup
(tmp / "upd" / "state.json").write_text(json.dumps({"T": {"pending_file": str(pdf)}}))
assert cv.resolve_paths("T", None, None, cfg, tmp / "upd")[0] == str(pdf)

# garbage input is handled, not a crash
s, w = cv.split_sections("this is not an Act at all")
assert s == [] and w

shutil.rmtree(tmp, ignore_errors=True)
print("ALL COMPARE TESTS PASSED")
