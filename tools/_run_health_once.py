"""Run health_check_2 and print failures only."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from erp_core.health_engine import run_health_check_2

rep = run_health_check_2()
fails = []
for r in (rep.results or []):
    if isinstance(r, (list, tuple)) and len(r) >= 3 and str(r[0]).lower() == "fail":
        fails.append(r)
print("score", getattr(rep, "score", None))
print("total", len(rep.results or []))
print("fails", len(fails))
for r in fails:
    cat = r[1] if len(r) > 1 else ""
    name = r[2] if len(r) > 2 else ""
    detail = r[3] if len(r) > 3 else ""
    print(f"- [{cat}] {name}: {detail}")
