"""PART 12 — Code quality metrics."""

from __future__ import annotations

import ast
import re
from collections import Counter
from pathlib import Path

from tools.v17_2.common import ROOT, ReportBundle


def _complexity(fn: ast.FunctionDef) -> int:
    score = 1
    for node in ast.walk(fn):
        if isinstance(node, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With, ast.BoolOp)):
            score += 1
    return score


def run_code_quality() -> ReportBundle:
    rep = ReportBundle("Code Quality Report — V17.2")
    large_funcs = []
    complexities = []
    duplicate_sql = Counter()

    for p in [ROOT / "database.py", ROOT / "db_v3.py"]:
        if not p.exists():
            continue
        tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        for node in tree.body:
            if isinstance(node, ast.FunctionDef):
                lines = node.end_lineno - node.lineno + 1 if node.end_lineno else 0
                c = _complexity(node)
                complexities.append((str(p.name), node.name, c, lines))
                if lines > 80:
                    large_funcs.append((str(p.name), node.name, lines))
                if c > 15:
                    rep.add("Complexity", f"{p.name}:{node.name}", "warn", f"cyclomatic≈{c}")

    sql_pattern = re.compile(r'execute\(\s*["\']+(SELECT|INSERT|UPDATE|DELETE)', re.I)
    for p in ROOT.rglob("*.py"):
        if "venv" in str(p):
            continue
        for m in sql_pattern.findall(p.read_text(encoding="utf-8", errors="ignore")):
            duplicate_sql[m] += 1

    from tools.debt_scanner import scan_ui_db_calls
    ui_db = scan_ui_db_calls()

    try:
        from infrastructure.query_optimizer.analyzer import analyze_slow_query_log
        slow = analyze_slow_query_log(10)
        rep.add("Slow queries", "Query log", "pass" if len(slow) < 10 else "warn", f"{len(slow)} entries")
    except Exception as exc:
        rep.add("N+1", "Query optimizer", "not_certified", str(exc)[:80])

    rep.sections["Large Functions (>80 lines)"] = "\n".join(
        f"- `{f[0]}:{f[1]}` — {f[2]} lines" for f in sorted(large_funcs, key=lambda x: -x[2])[:15]
    ) or "None flagged"
    rep.sections["SQL Statement Counts"] = "\n".join(f"- {k}: {v}" for k, v in duplicate_sql.most_common(5))
    rep.sections["UI Direct DB"] = f"**{ui_db['total_calls']}** patterns in erp_ui/"
    rep.sections["Avg Complexity (db layers)"] = (
        f"{round(sum(c[2] for c in complexities) / max(len(complexities), 1), 1)} across "
        f"{len(complexities)} functions in database.py + db_v3.py"
    )
    rep.add("Duplicate Code", "UI→DB coupling", "warn" if ui_db["total_calls"] > 50 else "pass",
            f"{ui_db['total_calls']} calls")
    return rep
