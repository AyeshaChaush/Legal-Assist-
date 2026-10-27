"""
Legal Assist+ : Phase 6, step 1 -- law update checker
-----------------------------------------------------
Checks whether the official PDF of each tracked Act has changed.

How it works (deliberately gentle on the source website):
  * one request per Act per run, plus one robots.txt request per host
  * obeys robots.txt (aborts that Act if crawling is disallowed)
  * only talks to hosts listed in law_sources.json
  * sends If-None-Match / If-Modified-Since so unchanged files cost almost nothing
  * waits `delay_seconds` between Acts
  * verifies the download really is a PDF (not an error page) before trusting it

Outcome per Act:
  BASELINE         first run: fingerprint recorded as the reference version
  UNCHANGED        same content as last time
  NOT_MODIFIED     server said 304, nothing to download
  CHANGED          new content: saved to data/law_updates/pending/ for review
  BLOCKED_BY_ROBOTS / ERROR   nothing was changed, reason printed

This step only DETECTS change. Nothing is re-indexed and no statute JSON is
touched; a human reviews pending files first (later steps of Phase 6).

Run:
    python check_law_updates.py                 # all Acts in law_sources.json
    python check_law_updates.py --only BNS_2023

Manual mode (when the website blocks automatic access): download the PDF yourself,
always from the SAME source each time, then:
    python check_law_updates.py --only BNS_2023 --file "C:\\path\\to\\bns.pdf"

Optional .env value (put an address where the site can reach you if needed):
    LEGAL_ASSIST_CONTACT=you@example.com
"""

import os
import sys
import json
import time
import argparse
import hashlib
from pathlib import Path
from urllib.parse import urlparse
from urllib import robotparser

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

CONFIG_PATH = Path("law_sources.json")
UPDATES_DIR = Path("data/law_updates")
MAX_BYTES = 60 * 1024 * 1024
TIMEOUT = 60
LOCAL_HOSTS = {"127.0.0.1", "localhost"}   # plain http is only accepted for these (tests)


def user_agent() -> str:
    base = "LegalAssistPlus-AcademicProject/1.0 (law update checker; low request rate)"
    contact = os.getenv("LEGAL_ASSIST_CONTACT", "").strip()
    return f"{base} contact:{contact}" if contact else base


def url_allowed(url: str, allowed_hosts) -> bool:
    p = urlparse(url)
    host = (p.hostname or "").lower()
    if host in LOCAL_HOSTS:
        return p.scheme in ("http", "https")
    return p.scheme == "https" and host in {h.lower() for h in allowed_hosts}


def robots_allows(session, url: str, ua: str) -> bool:
    """True if robots.txt permits fetching `url`. Raises on unreadable robots."""
    p = urlparse(url)
    robots_url = f"{p.scheme}://{p.netloc}/robots.txt"
    r = session.get(robots_url, headers={"User-Agent": ua}, timeout=TIMEOUT)
    if r.status_code in (404, 410):
        return True                       # no robots.txt means no restrictions
    if r.status_code != 200:
        raise RuntimeError(f"could not read robots.txt (HTTP {r.status_code})")
    rp = robotparser.RobotFileParser()
    rp.parse(r.text.splitlines())
    return rp.can_fetch(ua, url)


def fetch_pdf(session, url: str, ua: str, prior: dict):
    """Returns (status_code, bytes_or_None, etag, last_modified)."""
    headers = {"User-Agent": ua, "Accept": "application/pdf"}
    if prior.get("etag"):
        headers["If-None-Match"] = prior["etag"]
    if prior.get("last_modified"):
        headers["If-Modified-Since"] = prior["last_modified"]

    with session.get(url, headers=headers, timeout=TIMEOUT, stream=True) as r:
        if r.status_code == 304:
            return 304, None, prior.get("etag"), prior.get("last_modified")
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        data = bytearray()
        for part in r.iter_content(chunk_size=65536):
            data.extend(part)
            if len(data) > MAX_BYTES:
                raise RuntimeError("file larger than the 60 MB safety limit")
        return 200, bytes(data), r.headers.get("ETag"), r.headers.get("Last-Modified")


def load_state(updates_dir: Path) -> dict:
    p = updates_dir / "state.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def save_state(updates_dir: Path, state: dict):
    updates_dir.mkdir(parents=True, exist_ok=True)
    (updates_dir / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")


def now_iso() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S")


def evaluate_pdf(act, data, etag, last_mod, prior, state, updates_dir, result):
    """Compares PDF bytes with the recorded fingerprint and updates state/pending."""
    act_id = act["id"]
    url = act.get("pdf_url", "(local file)")
    if not data.startswith(b"%PDF"):
        result["detail"] = "response is not a PDF (possibly an error or login page); ignored"
        return result

    digest = hashlib.sha256(data).hexdigest()
    entry = {
        "name": act["name"], "pdf_url": url, "sha256": digest, "bytes": len(data),
        "etag": etag, "last_modified": last_mod, "last_checked": now_iso(),
        "last_changed": prior.get("last_changed"),
    }

    if not prior.get("sha256"):
        entry["last_changed"] = now_iso()
        result.update(status="BASELINE", detail=f"recorded reference fingerprint {digest[:12]}")
    elif prior["sha256"] == digest:
        result.update(status="UNCHANGED", detail=f"fingerprint {digest[:12]} matches")
    else:
        pending = Path(updates_dir) / "pending"
        pending.mkdir(parents=True, exist_ok=True)
        out = pending / f"{act_id}_{digest[:12]}.pdf"
        out.write_bytes(data)
        # keep the old fingerprint as the reference until a human approves this one
        entry["sha256"] = prior["sha256"]
        entry["bytes"] = prior.get("bytes", entry["bytes"])
        entry["pending_sha256"] = digest
        entry["pending_file"] = str(out)
        entry["pending_detected_at"] = now_iso()
        result.update(status="CHANGED",
                      detail=f"new version {digest[:12]} (was {prior['sha256'][:12]}) saved to {out}")
    state[act_id] = entry
    return result


def check_local_file(act_id, pdf_path, config_path=CONFIG_PATH, updates_dir=UPDATES_DIR):
    """Manual mode: fingerprint a PDF you downloaded yourself. No network access at all."""
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    act = next((a for a in config["acts"] if a["id"] == act_id), None)
    if not act:
        raise SystemExit(f"No Act with id {act_id!r} in {config_path}")
    updates_dir = Path(updates_dir)
    result = {"id": act_id, "name": act["name"], "status": "ERROR", "detail": ""}
    p = Path(pdf_path)
    if not p.is_file():
        result["detail"] = f"file not found: {p}"
        return result
    if p.stat().st_size > MAX_BYTES:
        result["detail"] = "file larger than the 60 MB safety limit"
        return result
    state = load_state(updates_dir)
    res = evaluate_pdf(act, p.read_bytes(), None, None, state.get(act_id, {}), state, updates_dir, result)
    save_state(updates_dir, state)
    return res


def check_act(session, act: dict, allowed_hosts, state: dict, updates_dir: Path, ua: str) -> dict:
    act_id, url = act["id"], act["pdf_url"]
    prior = state.get(act_id, {})
    result = {"id": act_id, "name": act["name"], "status": "ERROR", "detail": ""}

    try:
        if not url_allowed(url, allowed_hosts):
            result["detail"] = "URL host/scheme not in the allowed list"
            return result
        if not robots_allows(session, url, ua):
            result.update(status="BLOCKED_BY_ROBOTS", detail="robots.txt disallows this path")
            return result

        status, data, etag, last_mod = fetch_pdf(session, url, ua, prior)

        if status == 304:
            prior["last_checked"] = now_iso()
            state[act_id] = prior
            result.update(status="NOT_MODIFIED", detail="server reports no change")
            return result

        return evaluate_pdf(act, data, etag, last_mod, prior, state, updates_dir, result)

    except (requests.RequestException, RuntimeError) as e:
        result["detail"] = str(e)
        return result


def run_check(config_path=CONFIG_PATH, updates_dir=UPDATES_DIR, only=None, trust_env=True):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    updates_dir = Path(updates_dir)
    allowed_hosts = config.get("allowed_hosts", [])
    delay = float(config.get("delay_seconds", 5))
    acts = [a for a in config["acts"] if not only or a["id"] == only]
    if only and not acts:
        raise SystemExit(f"No Act with id {only!r} in {config_path}")

    session = requests.Session()
    session.trust_env = trust_env
    ua = user_agent()
    state = load_state(updates_dir)

    results = []
    for n, act in enumerate(acts):
        if n > 0:
            time.sleep(delay)
        res = check_act(session, act, allowed_hosts, state, updates_dir, ua)
        results.append(res)
        save_state(updates_dir, state)       # save after each Act so progress is never lost
    return results


def main():
    ap = argparse.ArgumentParser(description="Check tracked Acts for new official PDF versions.")
    ap.add_argument("--only", help="check a single Act id from law_sources.json")
    ap.add_argument("--file", help="manual mode: path to a PDF you downloaded yourself (needs --only)")
    args = ap.parse_args()

    if args.file:
        if not args.only:
            raise SystemExit("--file needs --only, e.g. --only BNS_2023 --file C:\\path\\bns.pdf")
        results = [check_local_file(args.only, args.file)]
    else:
        results = run_check(only=args.only)

    print(f"\nLaw update check, {now_iso()}\n" + "-" * 60)
    for r in results:
        print(f"{r['status']:<18} {r['id']:<12} {r['detail']}")
    print("-" * 60)
    if any(r["status"] == "CHANGED" for r in results):
        print("Changes found. Review the files in data/law_updates/pending/ before updating anything.")
    sys.exit(2 if any(r["status"] == "CHANGED" for r in results) else 0)


if __name__ == "__main__":
    main()
