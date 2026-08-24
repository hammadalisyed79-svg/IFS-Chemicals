"""PART 7 — Master data audit."""

from __future__ import annotations

from tools.v17_2.common import ReportBundle, temp_database


MASTER_TABLES = {
    "customers": ("code", "name"),
    "suppliers": ("code", "name"),
    "products": ("code", "name"),
    "employees": ("code", "full_name"),
    "warehouses": ("code", "name"),
    "machines": ("code", "name"),
    "chart_of_accounts": ("code", "name"),
}


def run_master_data_audit() -> ReportBundle:
    rep = ReportBundle("Master Data Audit — V17.2")
    db, path, _ = temp_database()
    try:
        with db.get_connection() as conn:
            for table, (code_col, name_col) in MASTER_TABLES.items():
                if not conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
                    rep.add(table, "Table exists", "fail", "missing")
                    continue
                total = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
                inactive = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE is_active=0").fetchone()[0] if "is_active" in cols else 0
                dup = conn.execute(
                    f"SELECT {code_col}, COUNT(*) c FROM {table} GROUP BY {code_col} HAVING c>1"
                ).fetchall()
                blank = conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {code_col} IS NULL OR TRIM({code_col})=''"
                ).fetchone()[0]
                rep.add(table, "Record count", "pass", f"total={total} inactive={inactive}")
                rep.add(table, "Duplicate codes", "pass" if not dup else "fail",
                        f"{len(dup)} duplicates" if dup else "none")
                rep.add(table, "Missing codes", "pass" if blank == 0 else "fail", f"blank={blank}")

            # Broken FK sample: sales lines without header
            orphan = conn.execute(
                """SELECT COUNT(*) FROM sales_invoice_items si
                   WHERE NOT EXISTS (SELECT 1 FROM sales_invoices s WHERE s.id=si.invoice_id)"""
            ).fetchone()[0]
            rep.add("Relations", "Orphan sale lines", "pass" if orphan == 0 else "fail", f"count={orphan}")

            # Tax rates
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='tax_rates'").fetchone():
                tax_count = conn.execute("SELECT COUNT(*) FROM tax_rates").fetchone()[0]
            else:
                tax_count = 0
            rep.add("Tax", "Tax rates seeded", "pass" if tax_count else "warn", f"count={tax_count}")

            # Units
            uom_table = "units_of_measure" if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE name='units_of_measure'"
            ).fetchone() else None
            if uom_table:
                units = conn.execute(f"SELECT COUNT(*) FROM {uom_table}").fetchone()[0]
                rep.add("Units", "UOM master", "pass" if units else "warn", f"count={units}")
            else:
                rep.add("Units", "UOM master", "not_certified", "units_of_measure table missing")

    finally:
        import os
        os.unlink(path)

    rep.sections["Verdict"] = f"**AUDIT COMPLETE** — {rep.failed} failures, {rep.passed} passes."
    return rep
