"""SQL query analyzer — N+1, duplicates, slow queries, index gaps."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field


@dataclass
class QueryReport:
    duplicate_queries: list[tuple[str, int]] = field(default_factory=list)
    slow_queries: list[dict] = field(default_factory=list)
    missing_index_candidates: list[str] = field(default_factory=list)
    n_plus_one_hints: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)


def analyze_slow_query_log(limit: int = 50) -> list[dict]:
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_slow_queries'").fetchone():
            return []
        return rows_to_list(conn.execute(
            "SELECT sql_text, duration_ms, recorded_at FROM erp_slow_queries ORDER BY duration_ms DESC LIMIT ?",
            (limit,),
        ).fetchall())


def scan_codebase_duplicates(root: str | None = None) -> list[tuple[str, int]]:
    import os
    root = root or os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    patterns = Counter()
    sql_re = re.compile(r'execute\s*\(\s*[f"\'](SELECT|INSERT|UPDATE|DELETE)[^"\']{20,}', re.I)
    for dirpath, _, files in os.walk(root):
        if "venv" in dirpath or "__pycache__" in dirpath:
            continue
        for f in files:
            if not f.endswith(".py"):
                continue
            text = open(os.path.join(dirpath, f), encoding="utf-8", errors="ignore").read()
            for m in sql_re.finditer(text):
                norm = re.sub(r"\s+", " ", m.group(0)[:120])
                patterns[norm] += 1
    return [(q, c) for q, c in patterns.most_common(20) if c > 2]


def check_missing_indexes() -> list[str]:
    from database import get_connection
    candidates = []
    index_targets = [
        ("sales_invoices", "customer_id"), ("sales_invoices", "sale_date"), ("sales_invoices", "status"),
        ("purchase_invoices", "supplier_id"), ("general_ledger", "account_id"), ("general_ledger", "entry_date"),
        ("portal_orders", "customer_id"), ("portal_orders", "status"),
    ]
    with get_connection() as conn:
        for table, col in index_targets:
            if not conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
                continue
            idx = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql LIKE ?",
                (table, f"%{col}%"),
            ).fetchall()
            if not idx:
                candidates.append(f"CREATE INDEX IF NOT EXISTS idx_{table}_{col} ON {table}({col})")
    return candidates


def detect_n_plus_one_patterns(root: str | None = None) -> list[str]:
    import os
    root = root or os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    hints = []
    loop_exec = re.compile(r"for\s+\w+\s+in\s+.*:[\s\S]{0,200}?\.execute\(", re.M)
    for dirpath, _, files in os.walk(os.path.join(root, "erp_ui")):
        for f in files:
            if not f.endswith(".py"):
                continue
            path = os.path.join(dirpath, f)
            text = open(path, encoding="utf-8", errors="ignore").read()
            if loop_exec.search(text):
                hints.append(os.path.relpath(path, root))
    return hints[:30]


def generate_report() -> QueryReport:
    rep = QueryReport()
    rep.slow_queries = analyze_slow_query_log()
    rep.duplicate_queries = scan_codebase_duplicates()
    rep.missing_index_candidates = check_missing_indexes()
    rep.n_plus_one_hints = detect_n_plus_one_patterns()
    if rep.missing_index_candidates:
        rep.recommendations.append(f"Add {len(rep.missing_index_candidates)} recommended indexes")
    if rep.n_plus_one_hints:
        rep.recommendations.append(f"Review {len(rep.n_plus_one_hints)} potential N+1 patterns in erp_ui")
    if rep.duplicate_queries:
        rep.recommendations.append(f"Consolidate {len(rep.duplicate_queries)} duplicate SQL patterns")
    return rep


def to_markdown() -> str:
    rep = generate_report()
    lines = ["# Query Optimization Report", ""]
    lines.append(f"**Slow queries logged:** {len(rep.slow_queries)}")
    lines.append(f"**Duplicate SQL patterns:** {len(rep.duplicate_queries)}")
    lines.append(f"**Missing index candidates:** {len(rep.missing_index_candidates)}")
    lines.append(f"**N+1 hints (erp_ui):** {len(rep.n_plus_one_hints)}")
    lines += ["", "## Recommendations"]
    for r in rep.recommendations:
        lines.append(f"- {r}")
    if rep.missing_index_candidates:
        lines += ["", "## Suggested indexes", "```sql"]
        lines.extend(rep.missing_index_candidates[:15])
        lines.append("```")
    if rep.n_plus_one_hints:
        lines += ["", "## N+1 review files"]
        for h in rep.n_plus_one_hints[:15]:
            lines.append(f"- {h}")
    return "\n".join(lines)
