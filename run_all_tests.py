"""Runs every test file in this folder and prints one PASS/FAIL line each."""
import sys, subprocess
from pathlib import Path

tests = sorted(p.name for p in Path(".").glob("test_*.py"))
failed = []
for t in tests:
    r = subprocess.run([sys.executable, t], capture_output=True, text=True)
    last = (r.stdout.strip().splitlines() or [""])[-1]
    ok = r.returncode == 0 and "PASSED" in last
    print(("PASS  " if ok else "FAIL  ") + t + ("" if ok else "\n" + (r.stderr or r.stdout)[-1500:]))
    if not ok:
        failed.append(t)
print("\nALL GOOD" if not failed else f"\n{len(failed)} test file(s) failed: {', '.join(failed)}")
sys.exit(1 if failed else 0)
