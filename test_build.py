import json, shutil, tempfile
from pathlib import Path
import compare_law_versions as cv
import build_statute_json as b

PDF_SECS = [
 {"number": "1", "title": "Short title", "text": "Short title.—This Act is the Test Act."},
 {"number": "2", "title": "Confession", "text": "Confession.—(1) No confession shall be proved.\n(2) None in custody.\nProvided that facts discovered may be proved."},
 {"number": "3", "title": "Other", "text": "Other.—Completely new wording here for the official text."},
]
OLD = [
 {"section_number": "1", "section_title": "Short title", "chapter": "I", "text": "1. Short title.—This Act is the Test Act."},
 {"section_number": "2", "section_title": "Confession", "chapter": "I", "text": "2. Confession.—(1) No confession shall be proved.\n(2) None in custody."},
 {"section_number": "3", "section_title": "Other", "chapter": "II", "text": "3. Other.—Totally different earlier wording of this one."},
]
new, info = b.rebuild(PDF_SECS, OLD)
assert [r["section_number"] for r in new] == ["1", "2", "3"]
assert new[0]["text"] == "1. " + PDF_SECS[0]["text"] and new[0]["chapter"] == "I"      # other fields kept
assert "Provided that facts discovered" in new[1]["text"] and new[1]["text"].startswith("2. Confession")
assert info["same"] == ["1"] and [n for n, _ in info["grew"]] == ["2"] and [n for n, _ in info["rewritten"]] == ["3"], info
assert OLD[1]["text"].endswith("custody.")                                              # input not mutated
# dict wrapper is preserved
new2, _ = b.rebuild(PDF_SECS, {"act": "X", "sections": OLD})
assert new2["act"] == "X" and len(new2["sections"]) == 3
# mismatched numbering stops
nn, inf = b.rebuild(PDF_SECS[:2], OLD)
assert nn is None and inf["problems"], inf
nn, inf = b.rebuild(PDF_SECS[:2], OLD, force=True)
assert nn is not None and [r["section_number"] for r in nn] == ["1", "2", "3"]          # extra JSON row kept untouched
assert inf["kept"] == ["3"]
print("ALL BUILD TESTS PASSED")
