import os, sys, json, pickle, shutil, hashlib, tempfile, types
from pathlib import Path
import numpy as np

# use the real faiss when installed; otherwise a tiny stand-in with the same calls
try:
    import faiss
    REAL = True
except ImportError:
    REAL = False
    class IndexFlatL2:
        def __init__(self, d):
            self.d = d; self._x = np.zeros((0, d), "float32")
        @property
        def ntotal(self): return len(self._x)
        def add(self, x):
            assert x.dtype == np.float32 and x.flags["C_CONTIGUOUS"]
            self._x = np.vstack([self._x, x])
        def reconstruct_n(self, i, n): return self._x[i:i + n].copy()
        def search(self, q, k):
            d = ((q[:, None, :] - self._x[None]) ** 2).sum(-1)
            ids = np.argsort(d, axis=1)[:, :k]
            return np.take_along_axis(d, ids, 1), ids
    fake = types.ModuleType("faiss")
    fake.IndexFlatL2 = IndexFlatL2
    fake.write_index = lambda ix, p: pickle.dump((ix.d, ix._x), open(p, "wb"))
    def _read(p):
        d, x = pickle.load(open(p, "rb")); ix = IndexFlatL2(d); ix.add(x); return ix
    fake.read_index = _read
    sys.modules["faiss"] = fake
    import faiss

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4

import apply_rebuilt_statute as ap
import compare_law_versions as cv

D = 16
def fake_embed(texts, normalize=False):
    out = []
    for t in texts:
        v = np.random.RandomState(int(hashlib.md5(t.encode()).hexdigest()[:8], 16)).randn(D).astype("float32")
        if normalize: v /= np.linalg.norm(v)
        out.append(v)
    return np.stack(out)
ap.load_embedder = lambda: fake_embed

tmp = Path(tempfile.mkdtemp()); here = os.getcwd(); os.chdir(tmp)
try:
    ACT = "Test Act, 2023"
    lines = ["ARRANGEMENT OF SECTIONS", "1. Short title.", "2. Confession.", "3. Other.", "",
             "1. Short title.—This Act is the Test Act, 2023.",
             "2. Confession.—(1) No confession shall be proved.",
             "Provided that facts discovered may be proved.",
             "3. Other.—Some words here."]
    c = canvas.Canvas("t.pdf", pagesize=A4); y = 800
    for ln in lines:
        c.drawString(40, y, ln); y -= 16
    c.save()

    old_rows = [
      {"act_name": ACT, "section_number": "1", "section_title": "Short title", "text": "1. Short title.—This Act is the Test Act, 2023."},
      {"act_name": ACT, "section_number": "2", "section_title": "Confession", "text": "2. Confession.—(1) No confession shall be proved."},
      {"act_name": ACT, "section_number": "3", "section_title": "Other", "text": "3. Other.—Some words here."}]
    Path("data/statutes/cleaned").mkdir(parents=True)
    jp = Path("data/statutes/cleaned/T.json")
    jp.write_text(json.dumps(old_rows), encoding="utf-8")

    def build_db(template_fn):
        chunks = [{"act_name": r["act_name"], "number": r["section_number"], "title": r["section_title"],
                   "text": r["text"], "jurisdiction": "Central", "chunk_type": "statute"} for r in old_rows]
        chunks.insert(1, {"act_name": "Other Act", "number": "2", "title": "Confession", "text": "unrelated",
                          "jurisdiction": "Central", "chunk_type": "statute"})
        chunks.append({"act_name": "A v B", "number": "9", "title": "x", "text": "judgment text",
                       "jurisdiction": "Central", "chunk_type": "judgment"})
        vecs = np.stack([fake_embed([template_fn(c)])[0] for c in chunks])
        ix = faiss.IndexFlatL2(D); ix.add(np.ascontiguousarray(vecs, dtype="float32"))
        Path("data/vector_db").mkdir(parents=True, exist_ok=True)
        faiss.write_index(ix, "data/vector_db/legal_index.faiss")
        pickle.dump(chunks, open("data/vector_db/chunk_metadata.pkl", "wb"))
        return chunks
    before_chunks = build_db(lambda c: f"{c['title']} {c['text']}")
    snap = lambda: (Path("data/vector_db/legal_index.faiss").read_bytes(), Path("data/vector_db/chunk_metadata.pkl").read_bytes(), jp.read_bytes())
    original = snap()

    args = ["--act", "T", "--pdf", "t.pdf", "--json", str(jp)]
    # 1) preview changes nothing
    ap.main(args)
    assert snap() == original, "preview modified the app data"
    assert Path("data/statutes/cleaned/T.rebuilt.json").exists()

    # 2) apply
    ap.main(args + ["--apply"])
    ix = faiss.read_index("data/vector_db/legal_index.faiss")
    ch = pickle.load(open("data/vector_db/chunk_metadata.pkl", "rb"))
    assert ix.ntotal == len(ch) == len(before_chunks)
    assert "Provided that facts discovered" in ch[2]["text"] and ch[2]["act_name"] == ACT
    assert ch[1] == before_chunks[1] and ch[-1] == before_chunks[-1]        # other Act + judgment untouched
    assert ch[0]["text"] == before_chunks[0]["text"]                         # identical section untouched
    old_ix_vecs = np.stack([fake_embed([f"{c['title']} {c['text']}"])[0] for c in before_chunks])
    new_vecs = ix.reconstruct_n(0, ix.ntotal)
    assert np.allclose(new_vecs[[0, 1, 3, 4]], old_ix_vecs[[0, 1, 3, 4]]), "unrelated vectors changed"
    assert np.allclose(new_vecs[2], fake_embed([f"{ch[2]['title']} {ch[2]['text']}"])[0]), "new vector wrong"
    assert not np.allclose(new_vecs[2], old_ix_vecs[2])
    assert "Provided that facts discovered" in json.loads(jp.read_text(encoding="utf-8"))[1]["text"]
    backups = list(Path("data/backups").iterdir()); assert len(backups) == 1
    assert {p.name for p in backups[0].iterdir()} == {"legal_index.faiss", "chunk_metadata.pkl", "T.json", "manifest.json"}

    # 3) restore brings back the exact old files
    ap.main(["--restore", str(backups[0])])
    assert snap() == original, "restore did not return the original files"

    # 4) an index built with an unknown embedding recipe is refused and left alone
    build_db(lambda c: "zzz " + c["text"])
    bad = snap()
    try:
        ap.main(args + ["--apply"]); raise AssertionError("should have refused")
    except SystemExit as e:
        assert "could not reproduce" in str(e), e
    assert snap() == bad and len(list(Path("data/backups").iterdir())) == 1, "refused run still changed something"

    # 5) an index that does not contain the Act is refused
    build_db(lambda c: f"{c['title']} {c['text']}")
    chs = pickle.load(open("data/vector_db/chunk_metadata.pkl", "rb"))
    for c_ in chs:
        if c_["act_name"] == ACT: c_["act_name"] = "Renamed Act"
    pickle.dump(chs, open("data/vector_db/chunk_metadata.pkl", "wb"))
    try:
        ap.main(args + ["--apply"]); raise AssertionError("should have refused")
    except SystemExit as e:
        assert "do not line up" in str(e), e
    print("ALL APPLY TESTS PASSED" + (" (real faiss)" if REAL else " (stand-in faiss)"))
finally:
    os.chdir(here); shutil.rmtree(tmp, ignore_errors=True)
