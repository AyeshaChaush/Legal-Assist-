"""
Legal Assist+ : put a rebuilt Act into the app (statute JSON + vector index), safely
-------------------------------------------------------------------------------------
Takes the official PDF, rebuilds the Act's sections word-for-word (see build_statute_json.py),
then replaces ONLY that Act's vectors inside your existing FAISS index. Your judgment chunks
and every other Act are not touched, and build_vector_db.py is NOT re-run (so the random
judgment sampling cannot change).

It first works out HOW your index was embedded by re-embedding some existing chunks and
checking they match the stored vectors. If it cannot reproduce them, it stops and changes nothing.

TWO STEPS
  1) Preview (changes nothing in the app):
        python apply_rebuilt_statute.py --act BSA_2023 --pdf "data\\law_updates\\downloads\\bsa.pdf"
  2) Apply (backs up first; close the Streamlit app before this):
        python apply_rebuilt_statute.py --act BSA_2023 --pdf "data\\law_updates\\downloads\\bsa.pdf" --apply

UNDO
        python apply_rebuilt_statute.py --restore "data\\backups\\<folder name printed when applying>"
"""
import os
import sys
import json
import time
import pickle
import shutil
import argparse
from pathlib import Path

import numpy as np

import compare_law_versions as cv
import build_statute_json as bsj

VECTOR_DIR = Path("data") / "vector_db"
BACKUP_ROOT = Path("data") / "backups"
INDEX_FILE = "legal_index.faiss"
META_FILE = "chunk_metadata.pkl"
MODEL_NAME = "all-MiniLM-L6-v2"
TOLERANCE = 1e-3


# ---------------------------------------------------------------- how a chunk was embedded
def _f(c, k):
    return str(c.get(k, "") or "")


TEMPLATES = [
    # the exact recipe used by build_vector_db.py (generate_embeddings); the rest are fallbacks
    ("act Section N: title. text",
     lambda c: f"{_f(c, 'act_name')} Section {_f(c, 'number')}: {_f(c, 'title')}. {_f(c, 'text')}"),
    ("text only", lambda c: _f(c, "text")),
    ("title + text", lambda c: f"{_f(c, 'title')} {_f(c, 'text')}"),
    ("title, newline, text", lambda c: f"{_f(c, 'title')}\n{_f(c, 'text')}"),
    ("Section N: title, newline, text", lambda c: f"Section {_f(c, 'number')}: {_f(c, 'title')}\n{_f(c, 'text')}"),
    ("act Section N title text", lambda c: f"{_f(c, 'act_name')} Section {_f(c, 'number')} {_f(c, 'title')} {_f(c, 'text')}"),
    ("act, Section N (title): text",
     lambda c: f"{_f(c, 'act_name')}, Section {_f(c, 'number')} ({_f(c, 'title')}): {_f(c, 'text')}"),
    ("act - Section N - title, newline, text",
     lambda c: f"{_f(c, 'act_name')} - Section {_f(c, 'number')} - {_f(c, 'title')}\n{_f(c, 'text')}"),
    ("act, newline, Section N: title, newline, text",
     lambda c: f"{_f(c, 'act_name')}\nSection {_f(c, 'number')}: {_f(c, 'title')}\n{_f(c, 'text')}"),
]


def load_embedder():
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(MODEL_NAME)

    def embed(texts, normalize=False):
        return np.asarray(model.encode(list(texts), convert_to_numpy=True, normalize_embeddings=normalize,
                                       show_progress_bar=False, batch_size=32), dtype="float32")
    return embed


def detect_template(chunks, vectors, indices, embed):
    """Returns (name, fn, normalize) that reproduces the stored vectors, or None."""
    step = max(1, len(indices) // 8)
    sample = indices[::step][:8]
    stored = vectors[sample]
    for normalize in (False, True):
        for name, fn in TEMPLATES:
            emb = embed([fn(chunks[i]) for i in sample], normalize)
            if emb.shape == stored.shape and float(np.abs(emb - stored).max()) < TOLERANCE:
                return name, fn, normalize
    return None


# ---------------------------------------------------------------- finding the Act's chunks
def _clean_num(v):
    return str(v).strip().rstrip(".")


def find_target_chunks(chunks, rows):
    wanted = {bsj._num(r): r for r in rows}
    act_names = {r.get("act_name") for r in rows if r.get("act_name")}
    if not act_names:
        raise SystemExit("The JSON rows have no act_name field, so I cannot tell which index chunks belong to this Act.")
    found = {}
    for i, c in enumerate(chunks):
        if not isinstance(c, dict) or c.get("chunk_type", "statute") != "statute":
            continue
        n = _clean_num(c.get("number", ""))
        if c.get("act_name") in act_names and n in wanted:
            found.setdefault(n, []).append(i)
    missing = sorted(set(wanted) - set(found), key=lambda x: (len(x), x))
    dups = {n: v for n, v in found.items() if len(v) > 1}
    if missing or dups:
        raise SystemExit(f"Index and JSON do not line up. Sections missing from the index: {missing[:10]}; "
                         f"sections found more than once: {list(dups)[:10]}. Nothing changed.")
    return {n: v[0] for n, v in found.items()}, wanted


def check_texts_match(chunks, index_of, old_rows):
    old = {bsj._num(r): (r.get("text") or "").strip() for r in old_rows}
    bad = [n for n, i in index_of.items() if _f(chunks[i], "text").strip() != old.get(n, None)]
    if len(bad) > 0.05 * max(1, len(index_of)):
        raise SystemExit(
            f"The text stored in the index differs from your current JSON for {len(bad)} sections "
            f"(for example {bad[:5]}). The index was probably built from a different file, so I will not "
            "replace anything. Send me build_vector_db.py and I will adapt the script.")


# ---------------------------------------------------------------- backup / restore
def make_backup(json_path):
    folder = BACKUP_ROOT / time.strftime("%Y%m%d_%H%M%S")
    folder.mkdir(parents=True, exist_ok=False)
    shutil.copy2(VECTOR_DIR / INDEX_FILE, folder / INDEX_FILE)
    shutil.copy2(VECTOR_DIR / META_FILE, folder / META_FILE)
    shutil.copy2(json_path, folder / Path(json_path).name)
    (folder / "manifest.json").write_text(
        json.dumps({"json_path": str(json_path), "json_name": Path(json_path).name}), encoding="utf-8")
    return folder


def restore(folder):
    folder = Path(folder)
    man = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    shutil.copy2(folder / INDEX_FILE, VECTOR_DIR / INDEX_FILE)
    shutil.copy2(folder / META_FILE, VECTOR_DIR / META_FILE)
    shutil.copy2(folder / man["json_name"], man["json_path"])
    print(f"Restored the vector index, chunk metadata and {man['json_name']} from {folder}")


# ---------------------------------------------------------------- the main job
def main(argv=None):
    ap = argparse.ArgumentParser(description="Rebuild an Act from its PDF and update the app's data safely.")
    ap.add_argument("--act")
    ap.add_argument("--pdf")
    ap.add_argument("--json", help="current statute JSON (default: json_path in law_sources.json)")
    ap.add_argument("--apply", action="store_true", help="really change the JSON and the vector index (after a backup)")
    ap.add_argument("--restore", help="restore from a backup folder under data\\backups")
    a = ap.parse_args(argv)

    if a.restore:
        restore(a.restore)
        return
    if not a.act or not a.pdf:
        raise SystemExit("Give --act and --pdf (or --restore <backup folder>).")

    import faiss

    json_path = Path(a.json or bsj.default_json_path(a.act))
    rebuilt_path = bsj.default_out_path(json_path)
    # build_vector_db.py indexes EVERY *.json in the statutes folder, so stray rebuilt copies
    # there would be indexed twice. Move any such file out (moved, never deleted).
    for stray in sorted(json_path.parent.glob("*.rebuilt.json")):
        dest = rebuilt_path.parent / stray.name
        dest.parent.mkdir(parents=True, exist_ok=True)
        os.replace(stray, dest)
        print(f"Moved {stray} -> {dest} (it must not sit in the statutes folder).")
    old_data, new_data, info, report = bsj.run_rebuild(a.act, a.pdf, json_path, rebuilt_path)
    old_rows, new_rows = bsj._rows(old_data)[0], bsj._rows(new_data)[0]

    print(f"\n[1/3] Rebuilt {len(new_rows)} sections from the PDF.")
    print(f"      identical {len(info['same'])}, gained content {len(info['grew'])}, "
          f"wording differed {len(info['rewritten'])}.")
    print(f"      Review report: {report}")
    if info["odd_end"]:
        print(f"      {len(info['odd_end'])} section(s) end without punctuation (maybe a stray heading):")
        for n, tail in info["odd_end"][:15]:
            print(f"        Section {n}: ...{tail}")

    index_path, meta_path = VECTOR_DIR / INDEX_FILE, VECTOR_DIR / META_FILE
    if not index_path.is_file() or not meta_path.is_file():
        raise SystemExit(f"Cannot find {index_path} / {meta_path}.")
    index = faiss.read_index(str(index_path))
    with open(meta_path, "rb") as fh:
        chunks = pickle.load(fh)
    if not isinstance(chunks, list) or len(chunks) != index.ntotal:
        raise SystemExit(f"Unexpected chunk metadata (type {type(chunks).__name__}, "
                         f"{len(chunks) if hasattr(chunks, '__len__') else '?'} items vs {index.ntotal} vectors).")

    index_of, wanted = find_target_chunks(chunks, new_rows)
    check_texts_match(chunks, index_of, old_rows)
    print(f"[2/3] Found all {len(index_of)} chunks of this Act in the index ({index.ntotal} vectors in total).")

    vectors = np.ascontiguousarray(index.reconstruct_n(0, index.ntotal), dtype="float32")
    embed = load_embedder()
    found = detect_template(chunks, vectors, sorted(index_of.values()), embed)
    if not found:
        raise SystemExit("I could not reproduce your index's embeddings from its chunks, so I will NOT change anything.\n"
                         "Send me build_vector_db.py and I will adapt this script.")
    tname, tfn, normalize = found
    print(f"[3/3] Embedding method confirmed: {tname}" + (" (normalized)" if normalize else "") + ".")

    # build the replacement chunks and vectors
    new_chunks = list(chunks)
    order = sorted(index_of, key=lambda n: index_of[n])
    for n in order:
        i, row = index_of[n], wanted[n]
        c = dict(chunks[i])
        c["text"] = row["text"]
        title = (row.get("section_title") or row.get("title") or "").strip()
        if title:
            c["title"] = title
        new_chunks[i] = c
    new_vecs = embed([tfn(new_chunks[index_of[n]]) for n in order], normalize)
    updated = vectors.copy()
    for k, n in enumerate(order):
        updated[index_of[n]] = new_vecs[k]
    changed = sum(1 for n in order if new_chunks[index_of[n]]["text"].strip() != _f(chunks[index_of[n]], "text").strip())

    if not a.apply:
        print(f"\nPREVIEW ONLY: nothing in the app was changed. {changed} of {len(order)} chunks would get new text.")
        print("To apply (close the Streamlit app first), run the same command with  --apply  added.")
        return

    # ---- apply: backup, write new files beside the old ones, then swap
    folder = make_backup(json_path)
    print(f"\nBackup saved in {folder}")
    new_index = faiss.IndexFlatL2(index.d)
    new_index.add(np.ascontiguousarray(updated, dtype="float32"))
    tmp_index, tmp_meta = VECTOR_DIR / (INDEX_FILE + ".new"), VECTOR_DIR / (META_FILE + ".new")
    faiss.write_index(new_index, str(tmp_index))
    with open(tmp_meta, "wb") as fh:
        pickle.dump(new_chunks, fh)
    os.replace(tmp_index, index_path)
    os.replace(tmp_meta, meta_path)
    shutil.copyfile(rebuilt_path, json_path)

    # ---- verify what is now on disk
    chk_index = faiss.read_index(str(index_path))
    with open(meta_path, "rb") as fh:
        chk_chunks = pickle.load(fh)
    assert chk_index.ntotal == index.ntotal and len(chk_chunks) == len(chunks), "size changed"
    probe = (info["grew"] or info["rewritten"] or [(order[0], 0)])[0][0]
    pi = index_of[probe]
    dist, ids = chk_index.search(embed([tfn(chk_chunks[pi])], normalize), 1)
    assert int(ids[0][0]) == pi and float(dist[0][0]) < 1e-3, "search check failed"
    assert chk_chunks[pi]["text"].strip() == wanted[probe]["text"].strip(), "text check failed"
    print(f"Applied. {changed} chunks updated; index still has {chk_index.ntotal} vectors.")
    print(f"Check passed: searching for Section {probe} finds its new text.")
    print(f"To undo everything:  python apply_rebuilt_statute.py --restore \"{folder}\"")


if __name__ == "__main__":
    main()
