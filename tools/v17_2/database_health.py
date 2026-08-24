"""PART 13 — Database health."""

from __future__ import annotations

from tools.v17_2.common import ReportBundle, temp_database


def run_database_health() -> ReportBundle:
    rep = ReportBundle("Database Health Report — V17.2")
    db, path, _ = temp_database()
    try:
        with db.get_connection() as conn:
            fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            rep.add("Integrity", "Foreign keys ON", "pass" if fk else "fail", f"PRAGMA foreign_keys={fk}")

            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()]
            rep.add("Schema", "Table count", "pass", f"{len(tables)} tables")

            # Indexes
            idx = conn.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'"
            ).fetchone()[0]
            rep.add("Indexes", "Count", "pass", f"{idx} indexes")

            # Orphan checks
            checks = [
                ("sales_invoice_items", "invoice_id", "sales_invoices", "id"),
                ("purchase_invoice_items", "invoice_id", "purchase_invoices", "id"),
                ("bom_formula_lines", "bom_id", "bom_formulas", "id"),
            ]
            for child, fk_col, parent, pk in checks:
                if child not in tables:
                    continue
                orphans = conn.execute(
                    f"""SELECT COUNT(*) FROM {child} c
                        WHERE NOT EXISTS (SELECT 1 FROM {parent} p WHERE p.{pk}=c.{fk_col})"""
                ).fetchone()[0]
                rep.add("Orphans", f"{child}→{parent}", "pass" if orphans == 0 else "fail", f"count={orphans}")

            # Duplicate document numbers
            for t, col in [("sales_invoices", "document_no"), ("customers", "code")]:
                if t not in tables:
                    continue
                dups = conn.execute(
                    f"SELECT {col}, COUNT(*) c FROM {t} GROUP BY {col} HAVING c>1"
                ).fetchall()
                rep.add("Duplicates", t, "pass" if not dups else "fail", f"{len(dups)} dup keys")

            # Integrity check
            ic = conn.execute("PRAGMA integrity_check").fetchone()[0]
            rep.add("SQLite", "integrity_check", "pass" if ic == "ok" else "fail", ic)

            # Migration history
            if "erp_migration_history" in tables:
                hist = conn.execute("SELECT COUNT(*) FROM erp_migration_history").fetchone()[0]
                rep.add("Migrations", "History rows", "pass", f"{hist}")

            from infrastructure.migrations.engine import verify_graph
            ok, errs = verify_graph()
            rep.add("Migrations", "Dependency graph", "pass" if ok else "fail", str(errs) or "valid")

    finally:
        import os
        os.unlink(path)

    rep.sections["Verdict"] = f"**{'DATABASE HEALTHY' if rep.failed == 0 else 'ISSUES FOUND'}** — {rep.failed} failures."
    return rep
