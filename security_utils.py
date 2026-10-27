"""
Legal Assist+ : Security layer (Phase 5)
----------------------------------------
- AES-256-GCM encryption of uploaded documents at rest
- User accounts (scrypt-hashed passwords) stored in SQLite
- JWT session tokens
- Per-user document isolation + per-user chat history
- Auto-deletion of old uploads
- SHA-256 integrity hashes recorded in a hash-chained ledger (tamper-evident;
  the ledger stores ONLY hashes, never document content)

Setup (once):
    pip install cryptography PyJWT
    python security_utils.py --gen-keys      # prints two values; put them in .env
.env must contain:
    APP_MASTER_KEY=<base64 32-byte key>
    JWT_SECRET=<random string>
"""

import os
import re
import json
import time
import base64
import hashlib
import secrets
import sqlite3
import uuid
from pathlib import Path

import jwt
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "app.db"
UPLOAD_DIR = DATA_DIR / "secure_uploads"
CHAT_DIR = DATA_DIR / "user_chats"

JWT_ALGORITHM = "HS256"
JWT_TTL_SECONDS = 8 * 60 * 60        # session lasts 8 hours
DEFAULT_RETENTION_DAYS = 7           # uploads auto-deleted after this
MIN_PASSWORD_LEN = 8
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------
# KEYS
# ---------------------------------------------------------
def generate_keys():
    master = base64.b64encode(AESGCM.generate_key(bit_length=256)).decode()
    jwt_secret = secrets.token_urlsafe(48)
    return master, jwt_secret


def _master_key() -> bytes:
    raw = os.getenv("APP_MASTER_KEY")
    if not raw:
        raise RuntimeError(
            "APP_MASTER_KEY missing. Run `python security_utils.py --gen-keys` "
            "and add the output to your .env file."
        )
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise RuntimeError("APP_MASTER_KEY must decode to exactly 32 bytes (AES-256).")
    return key


def _jwt_secret() -> str:
    s = os.getenv("JWT_SECRET")
    if not s:
        raise RuntimeError("JWT_SECRET missing. Run `python security_utils.py --gen-keys`.")
    return s


# ---------------------------------------------------------
# ENCRYPTION (AES-256-GCM). Blob layout: 12-byte nonce || ciphertext+tag
# user_id is bound in as associated data, so a file copied into another
# user's folder will fail to decrypt.
# ---------------------------------------------------------
def encrypt_bytes(data: bytes, user_id: int) -> bytes:
    nonce = os.urandom(12)
    ct = AESGCM(_master_key()).encrypt(nonce, data, str(user_id).encode())
    return nonce + ct


def decrypt_bytes(blob: bytes, user_id: int) -> bytes:
    nonce, ct = blob[:12], blob[12:]
    return AESGCM(_master_key()).decrypt(nonce, ct, str(user_id).encode())


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------
# DATABASE
# ---------------------------------------------------------
def _conn():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                pw_salt BLOB NOT NULL,
                pw_hash BLOB NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                consent_at INTEGER NOT NULL,
                created_at INTEGER NOT NULL
            );
            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                original_name TEXT NOT NULL,
                sha256 TEXT NOT NULL,
                path TEXT NOT NULL,
                uploaded_at INTEGER NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            );
            CREATE TABLE IF NOT EXISTS ledger (
                seq INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_id TEXT NOT NULL,
                doc_sha256 TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                entry_hash TEXT NOT NULL,
                ts INTEGER NOT NULL
            );
            """
        )


# ---------------------------------------------------------
# USERS / AUTH
# ---------------------------------------------------------
def _hash_password(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)


def register_user(email: str, password: str, consent: bool):
    """Returns (ok, message). Consent is required (DPDP Act 2023)."""
    email = email.strip().lower()
    if not consent:
        return False, "You must accept the data-processing consent to create an account."
    if not EMAIL_RE.match(email):
        return False, "Please enter a valid email address."
    if len(password) < MIN_PASSWORD_LEN:
        return False, f"Password must be at least {MIN_PASSWORD_LEN} characters."
    salt = os.urandom(16)
    now = int(time.time())
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO users (email, pw_salt, pw_hash, consent_at, created_at) "
                "VALUES (?,?,?,?,?)",
                (email, salt, _hash_password(password, salt), now, now),
            )
    except sqlite3.IntegrityError:
        return False, "An account with this email already exists."
    return True, "Account created. You can log in now."


def authenticate(email: str, password: str):
    """Returns user dict or None. Constant-time hash comparison."""
    email = email.strip().lower()
    with _conn() as c:
        row = c.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    if not row:
        _hash_password(password, os.urandom(16))  # equalize timing
        return None
    candidate = _hash_password(password, row["pw_salt"])
    if not secrets.compare_digest(candidate, row["pw_hash"]):
        return None
    return {"id": row["id"], "email": row["email"], "role": row["role"]}


# ---------------------------------------------------------
# JWT
# ---------------------------------------------------------
def create_token(user: dict) -> str:
    now = int(time.time())
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "role": user["role"],
        "iat": now,
        "exp": now + JWT_TTL_SECONDS,
    }
    return jwt.encode(payload, _jwt_secret(), algorithm=JWT_ALGORITHM)


def verify_token(token: str):
    """Returns user dict, or None if invalid/expired."""
    try:
        p = jwt.decode(token, _jwt_secret(), algorithms=[JWT_ALGORITHM])
        return {"id": int(p["sub"]), "email": p["email"], "role": p["role"]}
    except jwt.PyJWTError:
        return None


# ---------------------------------------------------------
# DOCUMENT VAULT (encrypted, per-user)
# ---------------------------------------------------------
def _ledger_append(c, doc_id: str, doc_sha: str):
    last = c.execute("SELECT entry_hash FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
    prev = last["entry_hash"] if last else "0" * 64
    ts = int(time.time())
    entry = hashlib.sha256(f"{prev}|{doc_id}|{doc_sha}|{ts}".encode()).hexdigest()
    c.execute(
        "INSERT INTO ledger (doc_id, doc_sha256, prev_hash, entry_hash, ts) VALUES (?,?,?,?,?)",
        (doc_id, doc_sha, prev, entry, ts),
    )


def store_document(user_id: int, original_name: str, data: bytes) -> str:
    """Encrypts and saves a document. Returns the document id."""
    doc_id = uuid.uuid4().hex
    user_dir = UPLOAD_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    path = user_dir / f"{doc_id}.enc"
    path.write_bytes(encrypt_bytes(data, user_id))
    doc_sha = sha256_hex(data)
    with _conn() as c:
        c.execute(
            "INSERT INTO documents (id, user_id, original_name, sha256, path, uploaded_at) "
            "VALUES (?,?,?,?,?,?)",
            (doc_id, user_id, original_name, doc_sha, str(path), int(time.time())),
        )
        _ledger_append(c, doc_id, doc_sha)
    return doc_id


def list_documents(user_id: int):
    with _conn() as c:
        rows = c.execute(
            "SELECT id, original_name, uploaded_at FROM documents WHERE user_id=? "
            "ORDER BY uploaded_at DESC", (user_id,)
        ).fetchall()
    return [dict(r) for r in rows]


def load_document(user_id: int, doc_id: str) -> bytes:
    """Decrypts in memory. Enforces ownership and verifies integrity."""
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM documents WHERE id=? AND user_id=?", (doc_id, user_id)
        ).fetchone()
    if not row:
        raise PermissionError("Document not found or not yours.")
    data = decrypt_bytes(Path(row["path"]).read_bytes(), user_id)
    if sha256_hex(data) != row["sha256"]:
        raise ValueError("Integrity check failed: document has been altered.")
    return data


def _review_path(user_id: int, doc_id: str) -> Path:
    return UPLOAD_DIR / str(user_id) / f"{doc_id}.review.enc"


def _owns(user_id: int, doc_id: str) -> bool:
    with _conn() as c:
        return c.execute(
            "SELECT 1 FROM documents WHERE id=? AND user_id=?", (doc_id, user_id)
        ).fetchone() is not None


def save_review(user_id: int, doc_id: str, review: dict):
    """Stores a document's review results, encrypted, next to the document."""
    if not _owns(user_id, doc_id):
        raise PermissionError("Document not found or not yours.")
    blob = json.dumps(review, ensure_ascii=False).encode("utf-8")
    _review_path(user_id, doc_id).write_bytes(encrypt_bytes(blob, user_id))


def load_review(user_id: int, doc_id: str):
    """Returns the saved review dict, or None if absent / not yours / unreadable."""
    if not _owns(user_id, doc_id):
        return None
    p = _review_path(user_id, doc_id)
    if not p.exists():
        return None
    try:
        return json.loads(decrypt_bytes(p.read_bytes(), user_id).decode("utf-8"))
    except Exception:
        return None


def delete_document(user_id: int, doc_id: str) -> bool:
    with _conn() as c:
        row = c.execute(
            "SELECT path FROM documents WHERE id=? AND user_id=?", (doc_id, user_id)
        ).fetchone()
        if not row:
            return False
        Path(row["path"]).unlink(missing_ok=True)
        _review_path(user_id, doc_id).unlink(missing_ok=True)
        c.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    return True


def delete_all_user_data(user_id: int):
    """Right-to-erasure: removes documents, chat history, and the account."""
    for d in list_documents(user_id):
        delete_document(user_id, d["id"])
    chat_path(user_id).unlink(missing_ok=True)
    with _conn() as c:
        c.execute("DELETE FROM users WHERE id=?", (user_id,))


def purge_expired(retention_days: int = DEFAULT_RETENTION_DAYS) -> int:
    """Deletes uploads older than retention. Call on app start. Returns count."""
    cutoff = int(time.time()) - retention_days * 86400
    with _conn() as c:
        rows = c.execute(
            "SELECT id, user_id FROM documents WHERE uploaded_at < ?", (cutoff,)
        ).fetchall()
    for r in rows:
        delete_document(r["user_id"], r["id"])
    return len(rows)


_last_purge = 0.0   # module-level, so it is shared by every session on this server


def purge_if_due(retention_days: int = DEFAULT_RETENTION_DAYS, interval_seconds: int = 3600) -> int:
    """
    Runs purge_expired() at most once per interval. Safe to call on every page
    interaction, so a long-running server still removes expired uploads.
    """
    global _last_purge
    now = time.time()
    if now - _last_purge < interval_seconds:
        return 0
    _last_purge = now
    return purge_expired(retention_days)


# ---------------------------------------------------------
# LEDGER VERIFICATION
# ---------------------------------------------------------
def verify_ledger():
    """Returns (ok, first_bad_seq). Detects any edited or removed entry."""
    with _conn() as c:
        rows = c.execute("SELECT * FROM ledger ORDER BY seq").fetchall()
    prev = "0" * 64
    for r in rows:
        expected = hashlib.sha256(
            f"{prev}|{r['doc_id']}|{r['doc_sha256']}|{r['ts']}".encode()
        ).hexdigest()
        if r["prev_hash"] != prev or r["entry_hash"] != expected:
            return False, r["seq"]
        prev = r["entry_hash"]
    return True, None


# ---------------------------------------------------------
# PER-USER CHAT HISTORY (encrypted too)
# ---------------------------------------------------------
def chat_path(user_id: int) -> Path:
    return CHAT_DIR / f"{user_id}.enc"


def load_user_chat(user_id: int) -> dict:
    p = chat_path(user_id)
    empty = {"qa_history": [], "doc_qa_history": {}}
    if not p.exists():
        return empty
    try:
        return json.loads(decrypt_bytes(p.read_bytes(), user_id).decode("utf-8"))
    except Exception:
        return empty


def save_user_chat(user_id: int, data: dict):
    CHAT_DIR.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(data, ensure_ascii=False).encode("utf-8")
    chat_path(user_id).write_bytes(encrypt_bytes(blob, user_id))


if __name__ == "__main__":
    import sys
    if "--gen-keys" in sys.argv:
        m, j = generate_keys()
        print(f"APP_MASTER_KEY={m}\nJWT_SECRET={j}")
    else:
        print(__doc__)
