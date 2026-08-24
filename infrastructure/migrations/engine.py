"""Professional migration framework — version history, rollback, dependency graph."""

from __future__ import annotations

import hashlib
import importlib
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class MigrationRecord:
    migration_id: str
    version: str
    module: str
    depends_on: list[str]


# Ordered migration graph (dependencies must be listed)
MIGRATION_GRAPH: list[MigrationRecord] = [
    MigrationRecord("v3_base", "3", "db_v3", []),
    MigrationRecord("v13_13", "13.13", "db_v13_13", ["v3_base"]),
    MigrationRecord("v13_14", "13.14", "db_v13_14", ["v13_13"]),
    MigrationRecord("v14_rc1", "14.0", "db_v14_rc1", ["v13_14"]),
    MigrationRecord("v15_portal", "15.0", "db_v15", ["v14_rc1"]),
    MigrationRecord("v16_platform", "16.0", "db_v16", ["v15_portal"]),
    MigrationRecord("v17_extensibility", "17.0", "db_v17", ["v16_platform"]),
    MigrationRecord("v17_1_manufacturing", "17.1", "db_v17_1", ["v17_extensibility"]),
    MigrationRecord("v17_2_validation", "17.2", "db_v17_2", ["v17_1_manufacturing"]),
    MigrationRecord("v17_3_certification", "17.3", "db_v17_3", ["v17_2_validation"]),
]

_MIGRATION_FUNCS = {
    "db_v15": "migrate_v15_0_mobile_portal_distributor",
    "db_v16": "migrate_v16_0_enterprise_platform",
    "db_v17": "migrate_v17_0_extensibility",
    "db_v17_1": "migrate_v17_1_manufacturing",
    "db_v17_2": "migrate_v17_2_validation",
    "db_v17_3": "migrate_v17_3_certification",
    "db_v14_rc1": "migrate_v14_rc1_enterprise",
    "db_v13_14": "migrate_v13_14_enterprise_workflow_integration",
    "db_v13_13": "migrate_v13_13_professional_workflow_completion",
}


def _checksum(module: str) -> str:
    path = Path(__file__).resolve().parents[2] / f"{module}.py"
    if path.exists():
        return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    return ""


def record_applied(migration_id: str, version: str, duration_ms: float, checksum: str) -> None:
    from database import get_connection
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_migration_history'").fetchone():
            conn.execute(
                """INSERT INTO erp_migration_history(migration_id,version,duration_ms,checksum,status)
                   VALUES(?,?,?,?,?)
                   ON CONFLICT(migration_id) DO UPDATE SET applied_at=CURRENT_TIMESTAMP""",
                (migration_id, version, duration_ms, checksum, "applied"),
            )


def get_history() -> list[dict]:
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_migration_history'").fetchone():
            return []
        return rows_to_list(conn.execute(
            "SELECT * FROM erp_migration_history ORDER BY applied_at"
        ).fetchall())


def verify_graph() -> tuple[bool, list[str]]:
    """Verify dependency order is valid."""
    seen = set()
    errors = []
    for rec in MIGRATION_GRAPH:
        for dep in rec.depends_on:
            if dep not in seen and dep not in [r.migration_id for r in MIGRATION_GRAPH[:MIGRATION_GRAPH.index(rec)]]:
                errors.append(f"{rec.migration_id} missing dependency {dep}")
        seen.add(rec.migration_id)
    return len(errors) == 0, errors


def run_standalone_migration(module: str, conn, db_module=None) -> float:
    """Run a single migration module and record timing."""
    fn_name = _MIGRATION_FUNCS.get(module)
    if not fn_name:
        return 0.0
    mod = importlib.import_module(module)
    fn = getattr(mod, fn_name)
    t0 = time.perf_counter()
    fn(conn, db_module)
    ms = (time.perf_counter() - t0) * 1000
    rec = next((r for r in MIGRATION_GRAPH if r.module == module), None)
    if rec:
        record_applied(rec.migration_id, rec.version, ms, _checksum(module))
    return ms
