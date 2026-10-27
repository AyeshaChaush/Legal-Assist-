import os, time, shutil, sqlite3, tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.chdir(tmp)

import security_utils as su
m, j = su.generate_keys()
os.environ["APP_MASTER_KEY"], os.environ["JWT_SECRET"] = m, j

su.init_db()

# registration + auth
assert not su.register_user("a@x.com", "longenough", consent=False)[0]
assert not su.register_user("bad", "longenough", True)[0]
assert not su.register_user("a@x.com", "short", True)[0]
assert su.register_user("a@x.com", "longenough", True)[0]
assert not su.register_user("A@x.com", "longenough", True)[0]   # duplicate, case-insens.
assert su.register_user("b@x.com", "longenough2", True)[0]
ua = su.authenticate("a@x.com", "longenough")
ub = su.authenticate("b@x.com", "longenough2")
assert ua and ub and su.authenticate("a@x.com", "wrong") is None

# JWT
tok = su.create_token(ua)
assert su.verify_token(tok)["email"] == "a@x.com"
assert su.verify_token(tok + "x") is None

# vault
data = b"%PDF-1.4 secret contract text"
doc = su.store_document(ua["id"], "c.pdf", data)
on_disk = Path(su.list_documents(ua["id"]) and f"data/secure_uploads/{ua['id']}/{doc}.enc").read_bytes()
assert b"secret contract" not in on_disk
assert su.load_document(ua["id"], doc) == data
try:
    su.load_document(ub["id"], doc); raise SystemExit("isolation FAILED")
except PermissionError:
    pass

# tamper detection on file
p = Path(f"data/secure_uploads/{ua['id']}/{doc}.enc")
b = bytearray(p.read_bytes()); b[20] ^= 1; p.write_bytes(bytes(b))
try:
    su.load_document(ua["id"], doc); raise SystemExit("tamper FAILED")
except Exception as e:
    assert "tamper FAILED" not in str(e)

# ledger
d2 = su.store_document(ub["id"], "d.pdf", b"another")
assert su.verify_ledger() == (True, None)
with sqlite3.connect(su.DB_PATH) as c:
    c.execute("UPDATE ledger SET doc_sha256='00' WHERE seq=1")
assert su.verify_ledger()[0] is False

# purge
with sqlite3.connect(su.DB_PATH) as c:
    c.execute("UPDATE documents SET uploaded_at=? WHERE id=?", (int(time.time()) - 10*86400, d2))
assert su.purge_expired(7) == 1 and su.list_documents(ub["id"]) == []

# saved reviews
d3 = su.store_document(ub["id"], "e.pdf", b"third doc")
review = {"results": ["r1", "r2"], "missing": "m"}
su.save_review(ub["id"], d3, review)
assert su.load_review(ub["id"], d3) == review
assert su.load_review(ua["id"], d3) is None            # other user cannot read it
try:
    su.save_review(ua["id"], d3, review); raise SystemExit("review isolation FAILED")
except PermissionError:
    pass
assert b"r1" not in next(Path("data/secure_uploads").rglob("*.review.enc")).read_bytes()
assert su.delete_document(ub["id"], d3)
assert not list(Path("data/secure_uploads").rglob("*.review.enc"))   # review removed with its document

# throttled periodic purge
def _backdate(doc_id):
    with sqlite3.connect(su.DB_PATH) as c:
        c.execute("UPDATE documents SET uploaded_at=? WHERE id=?", (int(time.time()) - 10*86400, doc_id))
d4 = su.store_document(ub["id"], "f.pdf", b"fourth"); _backdate(d4)
su._last_purge = 0.0
assert su.purge_if_due(7) == 1                         # first call purges
d5 = su.store_document(ub["id"], "g.pdf", b"fifth"); _backdate(d5)
assert su.purge_if_due(7) == 0                         # throttled within the hour
assert any(d["id"] == d5 for d in su.list_documents(ub["id"]))
su._last_purge = 0.0
assert su.purge_if_due(7) == 1                         # due again
assert not any(d["id"] == d5 for d in su.list_documents(ub["id"]))

# chat + erasure
su.save_user_chat(ua["id"], {"qa_history": [{"question": "q"}], "doc_qa_history": {}})
assert su.load_user_chat(ua["id"])["qa_history"][0]["question"] == "q"
assert su.load_user_chat(ub["id"])["qa_history"] == []
su.delete_all_user_data(ua["id"])
assert su.authenticate("a@x.com", "longenough") is None
print("ALL SECURITY TESTS PASSED")
shutil.rmtree(tmp, ignore_errors=True)
