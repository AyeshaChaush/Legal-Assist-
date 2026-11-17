"""
Legal Assist+ : Phase 6, step 2 -- compare an Act PDF with your stored sections
-------------------------------------------------------------------------------
Reads an Act PDF, splits it into numbered sections, and compares each section
with the matching entry in your structured JSON (data/statutes/cleaned/...).

Reports:
  * sections that are NEW in the PDF (not in your JSON)
  * sections MISSING from the PDF (in your JSON, not found in the PDF)
  * sections whose text CHANGED, with a short word-level diff
  * sections with MINOR differences (usually PDF text-extraction noise)

It never edits your JSON or the vector index. It only writes a report to
data/law_updates/reports/ for a human to read.

IMPORTANT -- calibrate first. Run it on the PDF your JSON was made from (your
baseline file). A good run shows almost everything UNCHANGED. Any differences
then show how noisy the splitter / PDF text is, so you know how much to trust a
real "changed" result later.

Usage:
    python compare_law_versions.py --act BNS_2023 --pdf "data\\law_updates\\downloads\\bns.pdf"
    python compare_law_versions.py --act BNS_2023            # uses the pending file, if any
    python compare_law_versions.py --act BNS_2023 --pdf x.pdf --json path\\to\\other.json
"""

import re
import sys
import json
import time
import argparse
import difflib
from pathlib import Path

CONFIG_PATH = Path("law_sources.json")
UPDATES_DIR = Path("data/law_updates")

HEAD_RE = re.compile(r"^\s*(\d{1,3}[A-Z]{0,2})\.\s+(\S.*)$")
PAGE_NUM_RE = re.compile(r"^\s*\d{1,3}\s*$")
SCHEDULE_RE = re.compile(r"^\s*THE\s+(FIRST\s+)?SCHEDULE\b|^\s*SCHEDULE\b")
MAX_SKIP = 3            # tolerate up to this many missing numbers in a row (reported as warnings)


# ---------------------------------------------------------------- PDF -> text
def extract_text(pdf_path):
    import pdfplumber
    pages = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\n".join(pages)


# ---------------------------------------------------------------- splitting
def _successors(num):
    m = re.fullmatch(r"(\d+)([A-Z]*)", num)
    n, suf = int(m.group(1)), m.group(2)
    out = {str(n + k) for k in range(1, MAX_SKIP + 1)}
    if not suf:
        out.add(f"{n}A")
    elif suf[-1] != "Z":
        out.add(f"{n}{suf[:-1]}{chr(ord(suf[-1]) + 1)}")
    return out


def _title_from(rest):
    return re.split(r"\s*\.?\s*[—–]\s*", rest, maxsplit=1)[0].strip(" .")


def split_sections(text):
    """
    Returns (sections, warnings). Each section: {"number", "title", "text"}.
    The Arrangement of Sections (table of contents) is skipped: the body is taken
    to start at the second line that begins "1. ". Section headings are then
    accepted only in sequence (n+1, n+2, ...), which stops numbered lines inside
    a section from being mistaken for headings.
    """
    lines = [ln for ln in text.splitlines() if not PAGE_NUM_RE.match(ln)]
    heads = []
    for i, ln in enumerate(lines):
        m = HEAD_RE.match(ln)
        if m:
            heads.append((i, m.group(1), m.group(2)))

    ones = [h for h in heads if h[1] == "1"]
    if not ones:
        return [], ["no section 1 heading found; is this an Act PDF?"]
    start_line = (ones[1] if len(ones) > 1 else ones[0])[0]

    accepted, warnings, cur = [], [], None
    for i, num, rest in heads:
        if i < start_line:
            continue
        if cur is None:
            ok = num == "1"
        else:
            ok = num in _successors(cur)
        if not ok:
            continue
        if cur is not None:
            cur_n = re.match(r"\d+", cur).group()
            expected = str(int(cur_n) + 1)
            if num != expected and not re.fullmatch(cur_n + r"[A-Z]+", num):
                warnings.append(f"jumped from section {cur} to {num}; check for a missed heading")
        accepted.append((i, num, rest))
        cur = num

    sections = []
    for k, (i, num, rest) in enumerate(accepted):
        end = accepted[k + 1][0] if k + 1 < len(accepted) else len(lines)
        body = lines[i:end]
        if k + 1 == len(accepted):          # last section: stop at the schedules
            for j, ln in enumerate(body):
                if j > 0 and SCHEDULE_RE.match(ln):
                    body = body[:j]
                    break
        body_text = "\n".join(body)
        body_text = re.sub(rf"^\s*{re.escape(num)}\.\s+", "", body_text, count=1)
        sections.append({"number": num, "title": _title_from(rest), "text": body_text})
    return sections, warnings


# ---------------------------------------------------------------- stored JSON
def load_stored(json_path):
    data = json.loads(Path(json_path).read_text(encoding="utf-8"))
    if isinstance(data, dict):
        lists = [v for v in data.values() if isinstance(v, list)]
        if not lists:
            raise SystemExit(f"{json_path}: expected a list of sections")
        data = lists[0]
    stored = {}
    for row in data:
        num = str(row.get("section_number", row.get("number", ""))).strip().rstrip(".")
        if not num:
            continue
        title = (row.get("section_title") or row.get("title") or "").strip()
        text = (row.get("text") or "").strip()
        if num in stored:                       # duplicate entries for one number: join them
            stored[num]["text"] += "\n" + text
        else:
            stored[num] = {"title": title, "text": text}
    return stored


# ---------------------------------------------------------------- comparing
def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower().replace("­", ""))


def similarity(stored_row, pdf_row):
    """Best ratio of the PDF section against the stored text, with or without its title."""
    p = _norm(pdf_row["text"])        # already starts with the heading text (title included)
    candidates = [_norm(stored_row["text"]), _norm(stored_row["title"] + " " + stored_row["text"])]
    best = 0.0
    for c in candidates:
        if c == p:
            return 1.0
        if not c or not p:
            continue
        sm = difflib.SequenceMatcher(None, c, p, autojunk=False)
        if sm.real_quick_ratio() < best or sm.quick_ratio() < best:
            continue
        best = max(best, sm.ratio())
    return best


def diff_snippet(stored_row, pdf_row, max_ops=3, width=140):
    a = (stored_row["text"] or stored_row["title"]).split()
    b = pdf_row["text"].split()
    ops = [o for o in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes() if o[0] != "equal"]
    out = []
    for tag, i1, i2, j1, j2 in ops[:max_ops]:
        old, new = " ".join(a[i1:i2])[:width], " ".join(b[j1:j2])[:width]
        out.append({"replace": f"stored: \"{old}\"  ->  PDF: \"{new}\"",
                    "delete": f"only in stored: \"{old}\"",
                    "insert": f"only in PDF: \"{new}\""}[tag])
    if len(ops) > max_ops:
        out.append(f"... and {len(ops) - max_ops} more difference(s)")
    return out


def _order(nums):
    def key(n):
        m = re.fullmatch(r"(\d+)([A-Z]*)", n)
        return (int(m.group(1)), m.group(2)) if m else (10**9, n)
    return sorted(nums, key=key)


def compare(pdf_sections, stored, minor_below=0.995, changed_below=0.95):
    by_num = {s["number"]: s for s in pdf_sections}
    new = [n for n in _order(by_num) if n not in stored]
    missing = [n for n in _order(stored) if n not in by_num]
    unchanged, minor, changed = [], [], []
    for n in _order(n for n in by_num if n in stored):
        r = similarity(stored[n], by_num[n])
        if r >= minor_below:
            unchanged.append(n)
        elif r >= changed_below:
            minor.append((n, r))
        else:
            changed.append((n, r))
    return {"new": new, "missing": missing, "unchanged": unchanged, "minor": minor, "changed": changed}


# ---------------------------------------------------------------- report
def build_report(act_id, pdf_path, json_path, result, pdf_sections, stored, warnings):
    by_num = {s["number"]: s for s in pdf_sections}
    L = [f"# Law comparison: {act_id}", "",
         f"- PDF: `{pdf_path}`", f"- Stored JSON: `{json_path}`",
         f"- Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}", "",
         "## Summary", "",
         f"- Sections found in PDF: {len(pdf_sections)}",
         f"- Sections in stored JSON: {len(stored)}",
         f"- Unchanged: {len(result['unchanged'])}",
         f"- Minor differences: {len(result['minor'])}",
         f"- Changed: {len(result['changed'])}",
         f"- New in PDF: {len(result['new'])}",
         f"- Missing from PDF: {len(result['missing'])}", ""]
    if warnings:
        L += ["## Splitter warnings", ""] + [f"- {w}" for w in warnings[:50]] + [""]
    if result["changed"]:
        L += ["## Changed sections", ""]
        for n, r in result["changed"]:
            L.append(f"### Section {n}: {by_num[n]['title']}  (similarity {r:.2f})")
            L += [f"- {d}" for d in diff_snippet(stored[n], by_num[n])] + [""]
    if result["minor"]:
        L += ["## Minor differences (often extraction noise)", ""]
        for n, r in result["minor"]:
            L.append(f"### Section {n}: {by_num[n]['title']}  (similarity {r:.3f})")
            L += [f"- {d}" for d in diff_snippet(stored[n], by_num[n], max_ops=2)] + [""]
    if result["new"]:
        L += ["## New in PDF", ""] + [f"- Section {n}: {by_num[n]['title']}" for n in result["new"]] + [""]
    if result["missing"]:
        L += ["## Missing from PDF", ""] + [f"- Section {n}: {stored[n]['title']}" for n in result["missing"]] + [""]
    return "\n".join(L)


# ---------------------------------------------------------------- CLI
def resolve_paths(act_id, pdf_arg, json_arg, config_path=CONFIG_PATH, updates_dir=UPDATES_DIR):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    act = next((a for a in config["acts"] if a["id"] == act_id), None)
    if not act:
        raise SystemExit(f"No Act with id {act_id!r} in {config_path}")
    json_path = json_arg or act.get("json_path")
    if not json_path:
        raise SystemExit("No stored JSON path: pass --json or add json_path for this Act in law_sources.json")
    pdf_path = pdf_arg
    if not pdf_path:
        sp = Path(updates_dir) / "state.json"
        state = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
        pdf_path = state.get(act_id, {}).get("pending_file")
        if not pdf_path:
            raise SystemExit("No --pdf given and no pending file recorded for this Act.")
    return pdf_path, json_path


def run(act_id, pdf_arg=None, json_arg=None, config_path=CONFIG_PATH, updates_dir=UPDATES_DIR):
    pdf_path, json_path = resolve_paths(act_id, pdf_arg, json_arg, config_path, updates_dir)
    if not Path(pdf_path).is_file():
        raise SystemExit(f"PDF not found: {pdf_path}")
    if not Path(json_path).is_file():
        raise SystemExit(f"Stored JSON not found: {json_path}")
    sections, warnings = split_sections(extract_text(pdf_path))
    stored = load_stored(json_path)
    result = compare(sections, stored)
    report = build_report(act_id, pdf_path, json_path, result, sections, stored, warnings)
    out_dir = Path(updates_dir) / "reports"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{act_id}_{time.strftime('%Y%m%d_%H%M%S')}.md"
    out.write_text(report, encoding="utf-8")
    return result, sections, stored, warnings, out


def main():
    ap = argparse.ArgumentParser(description="Compare an Act PDF with your stored JSON sections.")
    ap.add_argument("--act", required=True, help="Act id from law_sources.json, e.g. BNS_2023")
    ap.add_argument("--pdf", help="PDF to compare (default: the pending file for this Act)")
    ap.add_argument("--json", help="stored JSON (default: json_path in law_sources.json)")
    args = ap.parse_args()

    result, sections, stored, warnings, out = run(args.act, args.pdf, args.json)
    print(f"\nComparison for {args.act}\n" + "-" * 60)
    print(f"Sections in PDF: {len(sections)}   in stored JSON: {len(stored)}")
    print(f"Unchanged: {len(result['unchanged'])}   Minor differences: {len(result['minor'])}   "
          f"Changed: {len(result['changed'])}")
    print(f"New in PDF: {len(result['new'])}   Missing from PDF: {len(result['missing'])}   "
          f"Splitter warnings: {len(warnings)}")
    print("-" * 60)
    print(f"Full report: {out}")


if __name__ == "__main__":
    main()
