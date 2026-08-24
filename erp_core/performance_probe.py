"""V14 RC1 — performance measurement probes."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class PerformanceReport:
    metrics: dict[str, float] = field(default_factory=dict)

    def record(self, name: str, seconds: float) -> None:
        self.metrics[name] = round(seconds * 1000, 2)  # ms

    def to_markdown(self) -> str:
        lines = ["# Performance Report", "", "| Operation | ms |", "|-----------|-----|"]
        for k, v in sorted(self.metrics.items()):
            lines.append(f"| {k} | {v} |")
        return "\n".join(lines)


def run_performance_probes() -> PerformanceReport:
    import database as db
    from erp_core.enterprise_search import enterprise_search

    rep = PerformanceReport()

    t0 = time.perf_counter()
    db.init_db()
    rep.record("startup_init_db", time.perf_counter() - t0)

    t0 = time.perf_counter()
    enterprise_search("test", limit=10)
    rep.record("enterprise_search", time.perf_counter() - t0)

    t0 = time.perf_counter()
    from datetime import date
    today = date.today().isoformat()
    db.get_cash_book(today, today)
    rep.record("cash_book_query", time.perf_counter() - t0)

    t0 = time.perf_counter()
    with db.get_connection() as conn:
        conn.execute("SELECT COUNT(*) FROM products").fetchone()
    rep.record("db_simple_query", time.perf_counter() - t0)

    return rep
