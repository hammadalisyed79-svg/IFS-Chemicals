"""Shared helpers for V17.2 certification suite."""

from __future__ import annotations

import os
import tempfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


@dataclass
class CheckResult:
    category: str
    name: str
    status: str  # pass | fail | skip | warn | not_certified
    detail: str = ""
    evidence: str = ""


@dataclass
class ReportBundle:
    title: str
    results: list[CheckResult] = field(default_factory=list)
    sections: dict[str, str] = field(default_factory=dict)

    def add(self, category: str, name: str, status: str, detail: str = "", evidence: str = "") -> None:
        self.results.append(CheckResult(category, name, status, detail, evidence))

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.status == "pass")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.status == "fail")

    @property
    def not_certified(self) -> int:
        return sum(1 for r in self.results if r.status == "not_certified")

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.status in ("skip", "not_certified"))

    def pass_rate(self) -> float:
        actionable = [r for r in self.results if r.status not in ("skip",)]
        if not actionable:
            return 0.0
        return round(100.0 * sum(1 for r in actionable if r.status == "pass") / len(actionable), 1)

    def finalize_v173(self) -> "ReportBundle":
        """V17.3 — coerce every non-pass status to fail (no NOT CERTIFIED / SKIP / WARN)."""
        for r in self.results:
            if r.status != "pass":
                if r.status != "fail":
                    if not r.detail:
                        r.detail = f"Former status: {r.status}"
                    r.status = "fail"
        self.sections["V17.3"] = "All items normalized to **PASS** or **FAIL** only."
        return self

    def to_markdown(self, extra: str = "", *, v173: bool = False) -> str:
        if v173:
            self.finalize_v173()
        lines = [
            f"# {self.title}",
            "",
            f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Tool:** `{'tools/generate_v17_3_certification.py' if v173 else 'tools/generate_v17_2_reports.py'}`",
            "",
            "## Summary",
            "",
            f"| Metric | Count |",
            f"|--------|------:|",
            f"| Pass | {self.passed} |",
            f"| Fail | {self.failed} |",
        ]
        if not v173:
            lines.append(f"| Not certified / Skip | {self.not_certified} |")
        lines += [
            f"| Pass rate | {self.pass_rate()}% |",
            "",
        ]
        for title, body in self.sections.items():
            lines += [f"## {title}", "", body, ""]
        lines += ["## Detailed Results", "", "| Status | Category | Check | Detail |", "|--------|----------|-------|--------|"]
        for r in self.results:
            d = (r.detail or "").replace("|", "/").replace("\n", " ")[:120]
            lines.append(f"| {r.status} | {r.category} | {r.name} | {d} |")
        if extra:
            lines += ["", extra]
        return "\n".join(lines)


def temp_database():
    import database as db
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(closefd := fd)
    db.DB_PATH = Path(path)
    db.reset_runtime_state()
    t0 = time.perf_counter()
    db.init_db()
    init_ms = round((time.perf_counter() - t0) * 1000, 1)
    return db, path, init_ms


def write_report(filename: str, content: str) -> Path:
    out = ROOT / filename
    out.write_text(content, encoding="utf-8")
    return out


def timed(name: str, fn) -> tuple[float, object]:
    t0 = time.perf_counter()
    result = fn()
    return round((time.perf_counter() - t0) * 1000, 2), result
