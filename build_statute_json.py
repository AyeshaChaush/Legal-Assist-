"""
Legal Assist+ : rebuild an Act's stored sections word-for-word from the official PDF
------------------------------------------------------------------------------------
Why: the comparison tool showed that some stored statute JSON files are abridged
(provisos, explanations, illustrations missing). This script reads the official PDF,
splits it into sections, and writes a NEW json file where every section's "text" is the
full PDF text. Everything else in each row (title, chapter, ids, any other field) is kept.

SAFETY
  * It NEVER overwrites your existing JSON. The output goes to a new file (default:
    data/law_updates/rebuilt/<name>.rebuilt.json, deliberately NOT in data/statutes/cleaned). It refuses to write over the input.
  * It refuses to run if the section count or numbering does not line up (override: --force).
  * It writes a report listing every section whose text changed, so a human can review.
  * It does not touch the vector database. Rebuilding that is a separate, approved step.

Usage:
    python build_statute_json.py --act BSA_2023 --pdf "data\\law_updates\\downloads\\bsa.pdf"
    python build_statute_json.py --act BSA_2023 --pdf x.pdf --json old.json --out new.json
"""
import re
import sys
import json
import time
import argparse
from pathlib import Path

import compare_law_versions as cv

LEADING = cv.LEADING_NUM_RE


def _rows(data):
    """Returns (list_of_rows, rewrap) where rewrap(new_rows) rebuilds the original wrapper."""
    if isinstance(data, list):
        return data, lambda rows: rows
    for k, v in data.items():
        if isinstance(v, list):
            def rewrap(rows, k=k):
                out = dict(data)
                out[k] = rows
                return out
            return v, rewrap
    raise SystemExit("expected a list of sections (or a dict holding one)")


def _num(row):
    return str(row.get("section_number", row.get("number", ""))).strip().rstrip(".")


def rebuild(pdf_sections, data, force=False):
    """Returns (new_data, report_info). Pure function: no file access."""
    rows, rewrap = _rows(data)
    by_num = {s["number"]: s for s in pdf_sections}
    stored_nums = [_num(r) for r in rows]
    problems = []
    if set(by_num) != set(stored_nums):
        only_pdf = cv._order(set(by_num) - set(stored_nums))
        only_json = cv._order(set(stored_nums) - set(by_num))
        problems.append(f"section numbers differ: only in PDF {only_pdf[:10]}, only in JSON {only_json[:10]}")
    if len(stored_nums) != len(set(stored_nums)):
        problems.append("duplicate section numbers in the JSON")
    if problems and not force:
        return None, {"problems": problems}

    new_rows, info = [], {"problems": problems, "grew": [], "same": [], "rewritten": [], "kept": [], "odd_end": []}
    for row in rows:
        n = _num(row)
        pdf = by_num.get(n)
        if pdf is None or stored_nums.count(n) > 1:
            new_rows.append(row)
            info["kept"].append(n)
            continue
        old_text = (row.get("text") or "").strip()
        new_text = f"{n}. {pdf['text']}".strip()
        new_row = dict(row)
        new_row["text"] = new_text
        if new_text and not new_text.endswith(cv.END_PUNCT):
            info["odd_end"].append((n, new_text.splitlines()[-1][:100]))
        new_rows.append(new_row)
        old_stored = {"title": cv.LEADING_NUM_RE.sub("", (row.get("section_title") or row.get("title") or ""), count=1),
                      "text": LEADING.sub("", old_text, count=1)}
        ratio, precision, recall = cv.similarity_detail(old_stored, pdf)
        if ratio >= 0.995:
            info["same"].append(n)
        elif precision >= 0.95 and recall < 0.95:
            info["grew"].append((n, recall))          # old text was a subset: content added
        else:
            info["rewritten"].append((n, ratio))      # old text differed in wording: review these
    return rewrap(new_rows), info


def make_report(act_id, pdf_path, in_path, out_path, info, data, new_data):
    old = {_num(r): r for r in _rows(data)[0]}
    new = {_num(r): r for r in _rows(new_data)[0]}
    L = [f"# Rebuild report: {act_id}", "",
         f"- PDF: `{pdf_path}`", f"- Old JSON (untouched): `{in_path}`", f"- New JSON: `{out_path}`",
         f"- Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}", "", "## Summary", "",
         f"- Sections identical to the old text: {len(info['same'])}",
         f"- Sections that gained missing content: {len(info['grew'])}",
         f"- Sections whose wording differed (please review): {len(info['rewritten'])}",
         f"- Sections left as they were: {len(info['kept'])}",
         f"- Sections ending without punctuation: {len(info['odd_end'])}", ""]
    if info["odd_end"]:
        L += ["## Sections whose text does not end with punctuation (possible stray heading - check)", ""]
        L += [f"- Section {n}: ...{tail}" for n, tail in info["odd_end"]] + [""]
    if info["rewritten"]:
        L += ["## Wording differs - review these first", ""]
        for n, r in sorted(info["rewritten"], key=lambda x: x[1]):
            L += [f"### Section {n} (similarity {r:.2f})", "", "OLD:", "```", (old[n].get("text") or "")[:900],
                  "```", "NEW:", "```", new[n]["text"][:900], "```", ""]
    if info["grew"]:
        L += ["## Gained content (lowest coverage first)", ""]
        for n, rec in sorted(info["grew"], key=lambda x: x[1]):
            L.append(f"- Section {n}: old text covered {rec:.0%} of the official text")
    return "\n".join(L)


def default_out_path(in_path):
    """Rebuilt files go OUTSIDE data/statutes/cleaned, because build_vector_db.py indexes every *.json in that folder."""
    return Path(cv.UPDATES_DIR) / "rebuilt" / (Path(in_path).stem + ".rebuilt.json")


def run_rebuild(act_id, pdf_path, in_path, out_path, force=False):
    """Splits the PDF, rebuilds the sections, writes <out_path> and a report. Returns (data, new_data, info, report_path)."""
    in_path, out_path = Path(in_path), Path(out_path)
    if out_path.resolve() == in_path.resolve():
        raise SystemExit("Refusing to overwrite the input file. Choose a different --out.")
    sections, warnings = cv.split_sections(cv.extract_text(pdf_path))
    if warnings and not force:
        raise SystemExit("Splitter warnings, stopping (use --force to override):\n  " + "\n  ".join(warnings))
    data = json.loads(in_path.read_text(encoding="utf-8"))
    new_data, info = rebuild(sections, data, force=force)
    if new_data is None:
        raise SystemExit("Stopping, nothing written:\n  " + "\n  ".join(info["problems"]))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(new_data, ensure_ascii=False, indent=2), encoding="utf-8")
    rep_dir = Path(cv.UPDATES_DIR) / "reports"
    rep_dir.mkdir(parents=True, exist_ok=True)
    rep = rep_dir / f"{act_id}_rebuild_{time.strftime('%Y%m%d_%H%M%S')}.md"
    rep.write_text(make_report(act_id, pdf_path, in_path, out_path, info, data, new_data), encoding="utf-8")
    return data, new_data, info, rep


def default_json_path(act_id):
    cfg = json.loads(Path(cv.CONFIG_PATH).read_text(encoding="utf-8"))
    act = next((x for x in cfg["acts"] if x["id"] == act_id), None)
    if not act or not act.get("json_path"):
        raise SystemExit(f"No json_path for {act_id}: pass --json")
    return act["json_path"]


def main():
    ap = argparse.ArgumentParser(description="Rebuild an Act's stored JSON verbatim from its official PDF.")
    ap.add_argument("--act", required=True)
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--json", help="existing JSON (default: json_path in law_sources.json)")
    ap.add_argument("--out", help="where to write the new JSON (default: <name>.rebuilt.json)")
    ap.add_argument("--force", action="store_true", help="write even if section numbering does not line up")
    a = ap.parse_args()

    in_path = Path(a.json or default_json_path(a.act))
    out_path = Path(a.out) if a.out else default_out_path(in_path)
    data, new_data, info, rep = run_rebuild(a.act, a.pdf, in_path, out_path, force=a.force)
    print(f"\nRebuild for {a.act}\n" + "-" * 60)
    print(f"Identical: {len(info['same'])}   Gained content: {len(info['grew'])}   "
          f"Wording differed: {len(info['rewritten'])}   Kept: {len(info['kept'])}")
    print(f"Sections ending without punctuation (check in report): {len(info['odd_end'])}")
    print("-" * 60)
    print(f"New JSON (old one untouched): {out_path}")
    print(f"Review report: {rep}")


if __name__ == "__main__":
    main()
