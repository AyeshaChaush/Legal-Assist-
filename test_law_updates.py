import os, json, shutil, tempfile, threading, functools
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

import check_law_updates as cl


class Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def serve(directory):
    handler = functools.partial(Quiet, directory=str(directory))
    srv = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


tmp = Path(tempfile.mkdtemp())
site, blocked_site, updates = tmp / "site", tmp / "blocked", tmp / "updates"
site.mkdir(); blocked_site.mkdir()

(site / "robots.txt").write_text("User-agent: *\nAllow: /\n")
(site / "a.pdf").write_bytes(b"%PDF-1.4 version one")
(site / "bad.pdf").write_bytes(b"<html>Service unavailable</html>")
(blocked_site / "robots.txt").write_text("User-agent: *\nDisallow: /\n")
(blocked_site / "a.pdf").write_bytes(b"%PDF-1.4 blocked")

srv, base = serve(site)
srv2, base2 = serve(blocked_site)

def write_config(acts, hosts=()):
    p = tmp / "cfg.json"
    p.write_text(json.dumps({"allowed_hosts": list(hosts), "delay_seconds": 0, "acts": acts}))
    return p

def run(acts, hosts=(), only=None):
    return cl.run_check(write_config(acts, hosts), updates, only=only, trust_env=False)

good = {"id": "T_ACT", "name": "Test Act", "pdf_url": f"{base}/a.pdf"}

# 1. first run records a baseline
r = run([good])[0]
assert r["status"] == "BASELINE", r
state = json.loads((updates / "state.json").read_text())
assert len(state["T_ACT"]["sha256"]) == 64

# 2. second run: unchanged (200 same hash, or 304)
r = run([good])[0]
assert r["status"] in ("UNCHANGED", "NOT_MODIFIED"), r

# 3. file changes upstream -> CHANGED, pending copy saved, old reference kept
old_sha = state["T_ACT"]["sha256"]
(site / "a.pdf").write_bytes(b"%PDF-1.4 version two, amended")
t = (site / "a.pdf").stat().st_mtime + 500
os.utime(site / "a.pdf", (t, t))
r = run([good])[0]
assert r["status"] == "CHANGED", r
state = json.loads((updates / "state.json").read_text())
assert state["T_ACT"]["sha256"] == old_sha                      # not auto-approved
assert state["T_ACT"]["pending_sha256"] != old_sha
assert Path(state["T_ACT"]["pending_file"]).read_bytes().startswith(b"%PDF")

# 4. error page instead of a PDF -> ERROR, state untouched
before = (updates / "state.json").read_text()
r = run([{"id": "BAD", "name": "Bad", "pdf_url": f"{base}/bad.pdf"}])[0]
assert r["status"] == "ERROR" and "not a PDF" in r["detail"], r
assert "BAD" not in json.loads((updates / "state.json").read_text())

# 5. missing file -> ERROR (HTTP 404)
r = run([{"id": "GONE", "name": "Gone", "pdf_url": f"{base}/nope.pdf"}])[0]
assert r["status"] == "ERROR" and "404" in r["detail"], r

# 6. robots.txt disallow is respected
r = run([{"id": "ROB", "name": "Robots", "pdf_url": f"{base2}/a.pdf"}])[0]
assert r["status"] == "BLOCKED_BY_ROBOTS", r
assert "ROB" not in json.loads((updates / "state.json").read_text())

# 7. hosts outside the allowlist are refused (never contacted)
r = run([{"id": "EVIL", "name": "Evil", "pdf_url": "https://example.com/x.pdf"}], hosts=["indiacode.nic.in"])[0]
assert r["status"] == "ERROR" and "allowed list" in r["detail"], r
r = run([{"id": "HTTP", "name": "Plain http", "pdf_url": "http://indiacode.nic.in/x.pdf"}], hosts=["indiacode.nic.in"])[0]
assert r["status"] == "ERROR" and "allowed list" in r["detail"], r

# 8. --only filter
rs = run([good, {"id": "OTHER", "name": "Other", "pdf_url": f"{base}/a.pdf"}], only="OTHER")
assert [x["id"] for x in rs] == ["OTHER"]

# 9. shipped config is well-formed and only points at India Code over https
cfg = json.loads(Path("law_sources.json").read_text())
assert {a["id"] for a in cfg["acts"]} == {"BNS_2023", "BNSS_2023", "BSA_2023"}
for a in cfg["acts"]:
    assert cl.url_allowed(a["pdf_url"], cfg["allowed_hosts"]), a

# 10. manual local-file mode
lf = tmp / "local.pdf"
mupd = tmp / "manual_updates"
cfgp = write_config([good])
lf.write_bytes(b"%PDF-1.4 local v1")
assert cl.check_local_file("T_ACT", lf, cfgp, mupd)["status"] == "BASELINE"
assert cl.check_local_file("T_ACT", lf, cfgp, mupd)["status"] == "UNCHANGED"
lf.write_bytes(b"%PDF-1.4 local v2")
r = cl.check_local_file("T_ACT", lf, cfgp, mupd)
assert r["status"] == "CHANGED" and list((mupd / "pending").glob("T_ACT_*.pdf")), r
lf.write_bytes(b"not a pdf")
assert cl.check_local_file("T_ACT", lf, cfgp, mupd)["status"] == "ERROR"
assert cl.check_local_file("T_ACT", tmp / "missing.pdf", cfgp, mupd)["status"] == "ERROR"

srv.shutdown(); srv2.shutdown()
shutil.rmtree(tmp, ignore_errors=True)
print("ALL LAW-UPDATE TESTS PASSED")
