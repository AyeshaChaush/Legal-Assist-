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
Of definitions
2. Definitions.—In this Act, unless the context otherwise requires,—
1. "court" means a court of ordinary criminal jurisdiction;
2. "person" includes a company.
3. Offences.—Whoever does the prohibited act shall be punished with imprisonment up to three
years.
3A. Special offences.—Whoever does the prohibited act with a weapon shall be punished
with imprisonment up to seven years.
CHAPTER II
OF PUNISHMENTS
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
assert "Of definitions" not in secs[0]["text"]                       # trailing sub-heading trimmed
assert "CHAPTER" not in secs[3]["text"] and "PUNISHMENTS" not in secs[3]["text"]   # banner trimmed

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

# PDF-vs-PDF mode: extraction noise cancels because both sides use the same pipeline
def write_pdf(path, text):
    cv_ = canvas.Canvas(str(path), pagesize=A4)
    yy = 800
    for ln in text.splitlines():
        cv_.setFont("Helvetica", 10); cv_.drawString(40, yy, ln.replace("\u2014", "-")); yy -= 14
        if yy < 60:
            cv_.showPage(); yy = 800
    cv_.save()

TEXT2 = TEXT.replace("ordinary criminal jurisdiction", "revenue jurisdiction") \
            .replace("4. Punishment.\n1\nCHAPTER I", "4. Punishment.\n5. Appeals.\n1\nCHAPTER I") \
            .replace("4. Punishment.\u2014The punishment under this Act shall be rigorous.\n",
                     "4. Punishment.\u2014The punishment under this Act shall be rigorous.\n"
                     "5. Appeals.\u2014An appeal shall lie to the High Court.\n")
pdf_old, pdf_new = tmp / "old.pdf", tmp / "new.pdf"
write_pdf(pdf_old, TEXT); write_pdf(pdf_new, TEXT2)
res2, secs2, ref2, w2, out2 = cv.run("T", str(pdf_new), None, cfg, tmp / "upd2", old_pdf=str(pdf_old))
assert [n for n, _ in res2["changed"]] == ["2"], res2
assert res2["new"] == ["5"] and res2["missing"] == [], res2
assert res2["unchanged"] == ["1", "3", "3A", "4"], res2
assert "previous PDF" in out2.read_text(encoding="utf-8")
res3 = cv.run("T", str(pdf_old), None, cfg, tmp / "upd2", old_pdf=str(pdf_old))[0]
assert not res3["changed"] and not res3["minor"] and not res3["new"] and not res3["missing"]   # same file: no noise at all

# --vs-baseline uses data/law_updates/baseline/<ACT>.pdf, and says clearly when it is missing
(tmp / "upd2" / "baseline").mkdir(parents=True, exist_ok=True)
(tmp / "upd2" / "baseline" / "T.pdf").write_bytes(pdf_old.read_bytes())
res4 = cv.run("T", str(pdf_new), None, cfg, tmp / "upd2", vs_baseline=True)[0]
assert [n for n, _ in res4["changed"]] == ["2"]
try:
    cv.run("T", str(pdf_new), None, cfg, tmp / "no_such_dir", vs_baseline=True); raise AssertionError("should exit")
except SystemExit as e:
    assert "baseline" in str(e)

# pending-file lookup
(tmp / "upd" / "state.json").write_text(json.dumps({"T": {"pending_file": str(pdf)}}))
assert cv.resolve_paths("T", None, None, cfg, tmp / "upd")[0] == str(pdf)

# garbage input is handled, not a crash
s, w = cv.split_sections("this is not an Act at all")
assert s == [] and w

# ---- unpunctuated sub-heading at the end of a section is trimmed, real text is kept -------
TEXT_C = ("ARRANGEMENT OF SECTIONS\n1. A.\n2. B.\n3. C.\n"
          "1. A.\u2014First sentence.\n2. B.\u2014Second sentence ends here.\n"
          "Judgments of Courts when relevant\n"
          "3. C.\u2014Third sentence.\nIllustrations\n(a) A does a thing.\n")
sc, wc = cv.split_sections(TEXT_C)
assert sc[1]["text"].rstrip().endswith("ends here."), sc[1]
assert "Judgments" not in sc[1]["text"] and not wc, (sc, wc)
assert sc[2]["text"].rstrip().endswith("A does a thing."), sc[2]     # real last line kept

# ---- heading with no space after the number, and end matter after the last section -----
TEXT_B = ("ARRANGEMENT OF SECTIONS\n1. A.\n2. B.\n3. C.\nCHAPTER I\n"
          "1. A.—First.\n2.—B.—Second.\n3. C.—Third.\n"
          "STATEMENT OF OBJECTS AND REASONS\nblah blah\n")
sb, wb = cv.split_sections(TEXT_B)
assert [s["number"] for s in sb] == ["1", "2", "3"], sb
assert sb[1]["title"] == "B" and "blah" not in sb[2]["text"] and not wb, (sb, wb)

# ---- stored JSON that starts text/title with the section number -------------------
jp3 = tmp / "num.json"
jp3.write_text(json.dumps([{"section_number": "3", "section_title": "3. Offences",
                            "text": "3. Whoever does the prohibited act."}]), encoding="utf-8")
st3 = cv.load_stored(jp3)
assert st3["3"]["text"].startswith("Whoever") and st3["3"]["title"] == "Offences", st3

# ---- abridged: stored text is a subset of the PDF text (missing proviso + illustration) -------
core = "The court may do the thing in question. " * 6
pdf_row = {"number": "9", "title": "T", "text": "T.—" + core +
           "Provided that the court shall first hear the other side and record its reasons in writing "
           "before it acts. Illustration. A sues B for a debt."}
r_ab = cv.compare([pdf_row], {"9": {"title": "T", "text": core}})
assert [n for n, _ in r_ab["abridged"]] == ["9"] and not r_ab["changed"], r_ab
assert r_ab["abridged"][0][1] < 0.8
r_same = cv.compare([pdf_row], {"9": {"title": "T", "text": pdf_row["text"][3:]}})
assert r_same["unchanged"] == ["9"] and not r_same["abridged"], r_same

# ---- diagonal watermark is ignored ----------------------------------------------
def write_wm(path, watermark):
    cc = canvas.Canvas(str(path), pagesize=A4)
    cc.setFont("Helvetica", 10)
    yy = 800
    for k in range(40):
        cc.drawString(40, yy, f"Line {k} of the section text goes right here for the test."); yy -= 14
    if watermark:
        cc.saveState(); cc.setFont("Helvetica", 40); cc.translate(120, 380); cc.rotate(45)
        cc.drawString(0, 0, "IndiaCode"); cc.restoreState()
    cc.save()
plain, marked = tmp / "plain.pdf", tmp / "marked.pdf"
write_wm(plain, False); write_wm(marked, True)
import pdfplumber
with pdfplumber.open(str(marked)) as pm, pdfplumber.open(str(plain)) as pp:
    assert pm.pages[0].extract_text() != pp.pages[0].extract_text(), "test watermark did not disturb plain extraction"
assert cv.extract_text(marked) == cv.extract_text(plain), "watermark letters leaked into the text"

shutil.rmtree(tmp, ignore_errors=True)
print("ALL COMPARE TESTS PASSED")
