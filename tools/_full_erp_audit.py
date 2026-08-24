"""Full ERP operational audit — no Streamlit UI required."""
from __future__ import annotations

import json
import os
import ssl
import traceback
import urllib.request
from datetime import datetime

# ensure names used in except/http blocks are bound

out = {
    "when": datetime.now().isoformat(timespec="seconds"),
    "checks": [],
    "modules": {},
    "stats": {},
    "issues": [],
}


def add(cat, name, status, detail=""):
    out["checks"].append(
        {"category": cat, "name": name, "status": status, "detail": str(detail)[:300]}
    )
    if status == "fail":
        out["issues"].append(f"{cat}: {name} — {detail}")


def main():
    import database as db

    path = getattr(db, "DB_PATH", None) or getattr(db, "DATABASE_PATH", None)
    if not path:
        for cand in ("ifs_erp.db", "data/ifs_erp.db", "database/ifs_erp.db", "erp.db"):
            if os.path.exists(cand):
                path = cand
                break
    out["db_path"] = str(path)
    out["db_mb"] = round(os.path.getsize(path) / 1e6, 2) if path and os.path.exists(path) else None
    add(
        "Infra",
        "Database file",
        "pass" if out["db_mb"] else "fail",
        f"{path} ({out['db_mb']} MB)",
    )

    for mod, label in [
        ("database", "Core database"),
        ("db_v3", "Finance/GL v3"),
        ("db_hr", "HR/Payroll"),
        ("db_commercial", "Commercial"),
        ("db_invoice_workflow", "Invoice workflow"),
        ("db_cash_day", "Cash day control"),
        ("db_reports", "Reports"),
        ("db_stock_costing", "Stock costing"),
    ]:
        try:
            __import__(mod)
            add("Imports", label, "pass")
            out["modules"][label] = "ok"
        except Exception as e:
            add("Imports", label, "fail", str(e)[:200])
            out["modules"][label] = str(e)[:120]

    try:
        with db.get_connection() as conn:
            add("Database", "Connect", "pass")
            fk = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            add("Database", "Foreign keys ON", "pass" if fk else "warn", str(fk))
            iq = conn.execute("PRAGMA integrity_check").fetchone()[0]
            add("Database", "Integrity check", "pass" if iq == "ok" else "fail", iq[:120])
            tables = [
                r[0]
                for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY 1"
                ).fetchall()
            ]
            out["stats"]["tables"] = len(tables)
            add("Database", "Tables present", "pass", f"{len(tables)} tables")

            # Flexible critical-table aliases across schema generations
            aliases = {
                "customers": ["customers"],
                "suppliers": ["suppliers"],
                "products": ["products", "items"],
                "coa": ["chart_of_accounts", "accounts"],
                "gl": ["general_ledger", "ledger_entries", "gl_entries"],
                "sales_inv": ["sales_invoices", "sale_invoices"],
                "purchase_inv": ["purchase_invoices"],
                "sales_orders": ["sales_orders"],
                "users": ["users"],
                "employees": ["employees"],
                "cash_advances": ["cash_advances"],
                "cash_payments": ["cash_payments"],
                "cash_receipts": ["cash_receipts"],
                "jv": ["journal_vouchers", "journal_entries"],
            }
            missing = []
            resolved = {}
            for key, opts in aliases.items():
                hit = next((t for t in opts if t in tables), None)
                resolved[key] = hit
                if not hit and key not in ("cash_advances", "employees", "jv"):
                    missing.append(key)
            add(
                "Schema",
                "Critical tables",
                "pass" if not missing else "fail",
                "missing: " + ", ".join(missing) if missing else "all present",
            )

            for key, t in resolved.items():
                if t:
                    out["stats"][t] = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]

            gl_t = resolved.get("gl")
            if gl_t:
                cols = {r[1] for r in conn.execute(f"PRAGMA table_info({gl_t})").fetchall()}
                dcol = "debit" if "debit" in cols else ("dr_amount" if "dr_amount" in cols else None)
                ccol = "credit" if "credit" in cols else ("cr_amount" if "cr_amount" in cols else None)
                if dcol and ccol:
                    bal = conn.execute(
                        f"SELECT ROUND(SUM({dcol})-SUM({ccol}),2) FROM {gl_t}"
                    ).fetchone()[0]
                    add(
                        "GL",
                        "Ledger balanced (all-time)",
                        "pass" if abs(bal or 0) < 0.05 else "fail",
                        f"net {bal}",
                    )

            so_t = resolved.get("sales_orders")
            if so_t:
                try:
                    from db_v3 import get_sales_orders_for_invoice

                    sos = get_sales_orders_for_invoice()
                    so18 = [s for s in sos if s.get("document_no") == "SO-0018"]
                    detail = (
                        f"SO-0018 {'visible' if so18 else 'missing'}; "
                        f"open/partial pickable={len(sos)}"
                    )
                    add(
                        "Sales",
                        "Partial SO in invoice picker",
                        "pass" if so18 else "warn",
                        detail,
                    )
                except Exception as e:
                    add("Sales", "Partial SO in invoice picker", "fail", str(e)[:160])

            if resolved.get("cash_advances"):
                row = conn.execute(
                    """SELECT COUNT(*), ROUND(COALESCE(SUM(outstanding_amount),0),2)
                       FROM cash_advances WHERE status IN ('open','partial')"""
                ).fetchone()
                add(
                    "Finance",
                    "Cash Advance module",
                    "pass",
                    f"open={row[0]} outstanding={row[1] or 0}",
                )
            else:
                add("Finance", "Cash Advance module", "fail", "table missing")

            if resolved.get("users"):
                cols = {r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()}
                if "is_active" in cols:
                    u = conn.execute("SELECT COUNT(*) FROM users WHERE is_active=1").fetchone()[0]
                else:
                    u = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
                add("Security", "Active users", "pass" if u > 0 else "fail", f"{u} active")

            if resolved.get("customers"):
                cols = {r[1] for r in conn.execute("PRAGMA table_info(customers)").fetchall()}
                if "is_active" in cols:
                    n = conn.execute("SELECT COUNT(*) FROM customers WHERE is_active=1").fetchone()[0]
                else:
                    n = out["stats"].get("customers", 0)
                add("Masters", "Active customers", "pass", str(n))
            if resolved.get("suppliers"):
                cols = {r[1] for r in conn.execute("PRAGMA table_info(suppliers)").fetchall()}
                if "is_active" in cols:
                    n = conn.execute("SELECT COUNT(*) FROM suppliers WHERE is_active=1").fetchone()[0]
                else:
                    n = out["stats"].get("suppliers", 0)
                add("Masters", "Active suppliers", "pass", str(n))

            # Recent activity with flexible column names
            activity = []
            si = resolved.get("sales_inv")
            if si:
                cols = {r[1] for r in conn.execute(f"PRAGMA table_info({si})").fetchall()}
                dcol = "invoice_date" if "invoice_date" in cols else (
                    "sale_date" if "sale_date" in cols else None
                )
                if dcol:
                    activity.append(
                        (
                            "Sales invoices last 7d",
                            f"SELECT COUNT(*) FROM {si} WHERE {dcol}>=date('now','-7 day')",
                        )
                    )
            pi = resolved.get("purchase_inv")
            if pi:
                cols = {r[1] for r in conn.execute(f"PRAGMA table_info({pi})").fetchall()}
                dcol = "invoice_date" if "invoice_date" in cols else None
                if dcol:
                    activity.append(
                        (
                            "Purchase invoices last 7d",
                            f"SELECT COUNT(*) FROM {pi} WHERE {dcol}>=date('now','-7 day')",
                        )
                    )
            if resolved.get("cash_payments") and resolved.get("cash_receipts"):
                activity.append(
                    (
                        "Cash vouchers last 7d",
                        """SELECT
                            (SELECT COUNT(*) FROM cash_payments WHERE payment_date>=date('now','-7 day'))
                          + (SELECT COUNT(*) FROM cash_receipts WHERE receipt_date>=date('now','-7 day'))""",
                    )
                )
            if gl_t:
                cols = {r[1] for r in conn.execute(f"PRAGMA table_info({gl_t})").fetchall()}
                dcol = "entry_date" if "entry_date" in cols else (
                    "txn_date" if "txn_date" in cols else (
                        "voucher_date" if "voucher_date" in cols else None
                    )
                )
                if dcol:
                    activity.append(
                        (
                            "GL lines last 7d",
                            f"SELECT COUNT(*) FROM {gl_t} WHERE {dcol}>=date('now','-7 day')",
                        )
                    )
            for label, sql in activity:
                try:
                    out["stats"][label] = conn.execute(sql).fetchone()[0]
                    add("Activity", label, "pass", str(out["stats"][label]))
                except Exception as e:
                    add("Activity", label, "warn", str(e)[:100])

            coa = resolved.get("coa")
            if coa:
                adv = conn.execute(
                    f"""SELECT code, name FROM {coa}
                        WHERE code IN ('100180','1000180')
                           OR UPPER(name) LIKE '%ADVANCE PAYMENT%'
                        LIMIT 5"""
                ).fetchall()
                add(
                    "Finance",
                    "Advance Payments GL",
                    "pass" if adv else "warn",
                    str([dict(r) for r in adv])[:160],
                )

    except Exception:
        add("Database", "Connect", "fail", traceback.format_exc()[-300:])

    for url, label in [
        ("http://127.0.0.1:8501/_stcore/health", "Streamlit health"),
        ("https://127.0.0.1/_stcore/health", "HTTPS proxy"),
    ]:
        try:
            req = urllib.request.Request(url, method="GET")
            ctx = ssl._create_unverified_context() if url.startswith("https") else None
            with urllib.request.urlopen(req, timeout=8, context=ctx) as r:
                body = r.read()[:80]
                add(
                    "Runtime",
                    label,
                    "pass" if r.status == 200 else "warn",
                    f"{r.status} {body!r}",
                )
        except Exception as e:
            add("Runtime", label, "fail", str(e)[:160])

    # Page map smoke (avoid executing Streamlit page bodies)
    try:
        import ast

        with open("app.py", encoding="utf-8") as f:
            tree = ast.parse(f.read())
        page_keys = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id.upper() in {
                        "PAGES",
                        "PAGE_MAP",
                        "ROUTES",
                        "NAV_PAGES",
                    }:
                        if isinstance(node.value, ast.Dict):
                            for k in node.value.keys:
                                if isinstance(k, ast.Constant) and isinstance(k.value, str):
                                    page_keys.append(k.value)
        out["stats"]["registered_pages"] = len(page_keys)
        add("UI", "Registered pages", "pass" if page_keys else "warn", f"{len(page_keys)} pages")
        for need in (
            "Cash Book",
            "Sales Invoices",
            "Cash Advance",
            "Sales Orders",
            "Expense Bill",
        ):
            add(
                "UI",
                f"Page: {need}",
                "pass" if need in page_keys else "warn",
                "mapped" if need in page_keys else "not in PAGE map",
            )
    except Exception as e:
        add("UI", "Registered pages", "warn", str(e)[:160])

    passed = sum(1 for c in out["checks"] if c["status"] == "pass")
    failed = sum(1 for c in out["checks"] if c["status"] == "fail")
    warned = sum(1 for c in out["checks"] if c["status"] == "warn")
    out["summary"] = {
        "total": len(out["checks"]),
        "pass": passed,
        "fail": failed,
        "warn": warned,
        "score": round(100.0 * passed / max(1, len(out["checks"])), 1),
    }
    os.makedirs("reports", exist_ok=True)
    path_out = "reports/full_erp_audit_2026-08-22.json"
    with open(path_out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print(json.dumps(out["summary"], indent=2))
    print("FAILS:")
    for i in out["issues"]:
        print(" -", i)
    print("WARNS:")
    for c in out["checks"]:
        if c["status"] == "warn":
            print(" -", f"{c['category']}: {c['name']} — {c['detail'][:120]}")
    print("STATS:")
    print(json.dumps(out["stats"], indent=2, default=str)[:2500])
    print("WROTE", path_out)


if __name__ == "__main__":
    main()
