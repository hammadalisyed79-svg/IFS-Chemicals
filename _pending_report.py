import json
from collections import defaultdict
import database

database.init_db()

PENDING_STATUSES = {
    "draft", "pending", "pending_approval", "open", "issued", "in_progress",
    "unposted", "submitted", "approved",  # approved but maybe not posted - we'll include non-posted
}

# Statuses that mean "done" / not pending for listing focus
DONE = {"posted", "cancelled", "canceled", "completed", "closed", "rejected", "void"}

def row_dict(r):
    if r is None:
        return None
    if hasattr(r, "keys"):
        return {k: r[k] for k in r.keys()}
    return dict(r)

def cols(conn, table):
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]

def status_counts(conn, table, status_col="status"):
    try:
        rows = conn.execute(
            f"SELECT COALESCE({status_col}, '(null)') AS st, COUNT(*) AS n FROM {table} GROUP BY 1 ORDER BY n DESC"
        ).fetchall()
        return [(r[0], r[1]) for r in rows]
    except Exception as e:
        return [("ERROR", str(e))]

reports = {}

with database.get_connection() as conn:
    tables_interest = [
        "sales_invoices", "purchase_invoices", "sales_returns", "purchase_returns",
        "job_cards", "production_orders", "production_finished_receipts",
        "production_material_issues", "erp_draft_registry",
    ]
    for t in tables_interest:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)
        ).fetchone()
        if not exists:
            print(f"TABLE MISSING: {t}")
            continue
        c = cols(conn, t)
        print(f"\n=== {t} columns ===")
        print(", ".join(c))
        print("status counts:", status_counts(conn, t))

print("\n" + "="*60)
print("DETAILED PENDING LISTS")
print("="*60)

with database.get_connection() as conn:
    # Sales invoices
    q = """
    SELECT si.document_no, si.invoice_date, c.name AS party, si.status, si.total
    FROM sales_invoices si
    LEFT JOIN customers c ON c.id = si.customer_id
    WHERE LOWER(COALESCE(si.status,'')) NOT IN ('posted','cancelled','canceled','completed','closed','rejected','void')
    ORDER BY si.invoice_date DESC, si.id DESC
    """
    rows = [row_dict(r) for r in conn.execute(q).fetchall()]
    print(f"\n## Sales invoices pending ({len(rows)})")
    for r in rows:
        print(f"  {r}")

    q = """
    SELECT pi.document_no, pi.invoice_date, s.name AS party, pi.status, pi.total
    FROM purchase_invoices pi
    LEFT JOIN suppliers s ON s.id = pi.supplier_id
    WHERE LOWER(COALESCE(pi.status,'')) NOT IN ('posted','cancelled','canceled','completed','closed','rejected','void')
    ORDER BY pi.invoice_date DESC, pi.id DESC
    """
    rows = [row_dict(r) for r in conn.execute(q).fetchall()]
    print(f"\n## Purchase invoices pending ({len(rows)})")
    for r in rows:
        print(f"  {r}")

    # sales returns - discover date/total cols
    sr_cols = set(cols(conn, "sales_returns"))
    date_col = "return_date" if "return_date" in sr_cols else ("document_date" if "document_date" in sr_cols else "invoice_date" if "invoice_date" in sr_cols else None)
    amt = "total" if "total" in sr_cols else ("grand_total" if "grand_total" in sr_cols else "NULL")
    party_join = "LEFT JOIN customers c ON c.id = sr.customer_id" if "customer_id" in sr_cols else ""
    party_sel = "c.name AS party" if "customer_id" in sr_cols else "NULL AS party"
    q = f"""
    SELECT sr.document_no, sr.{date_col} AS doc_date, {party_sel}, sr.status, {amt} AS amount
    FROM sales_returns sr
    {party_join}
    WHERE LOWER(COALESCE(sr.status,'')) NOT IN ('posted','cancelled','canceled','completed','closed','rejected','void')
    ORDER BY sr.id DESC
    """
    rows = [row_dict(r) for r in conn.execute(q).fetchall()]
    print(f"\n## Sales returns pending ({len(rows)})")
    for r in rows:
        print(f"  {r}")

    pr_cols = set(cols(conn, "purchase_returns"))
    date_col = "return_date" if "return_date" in pr_cols else ("document_date" if "document_date" in pr_cols else None)
    amt = "total" if "total" in pr_cols else "NULL"
    party_join = "LEFT JOIN suppliers s ON s.id = pr.supplier_id" if "supplier_id" in pr_cols else ""
    party_sel = "s.name AS party" if "supplier_id" in pr_cols else "NULL AS party"
    q = f"""
    SELECT pr.document_no, pr.{date_col} AS doc_date, {party_sel}, pr.status, {amt} AS amount
    FROM purchase_returns pr
    {party_join}
    WHERE LOWER(COALESCE(pr.status,'')) NOT IN ('posted','cancelled','canceled','completed','closed','rejected','void')
    ORDER BY pr.id DESC
    """
    rows = [row_dict(r) for r in conn.execute(q).fetchall()]
    print(f"\n## Purchase returns pending ({len(rows)})")
    for r in rows:
        print(f"  {r}")

    # job cards
    jc_cols = set(cols(conn, "job_cards"))
    q = """
    SELECT jc.document_no, jc.job_date, jc.job_name, jc.job_type, jc.status,
           COALESCE(jc.total_material_cost,0)+COALESCE(jc.total_overhead_cost,0) AS amount,
           p.name AS product
    FROM job_cards jc
    LEFT JOIN products p ON p.id = jc.finished_product_id
    WHERE LOWER(COALESCE(jc.status,'')) NOT IN ('posted','cancelled','canceled','completed','closed','rejected','void')
    ORDER BY jc.job_date DESC, jc.id DESC
    """
    try:
        rows = [row_dict(r) for r in conn.execute(q).fetchall()]
    except Exception as e:
        # fallback simpler
        q2 = """
        SELECT jc.document_no, jc.job_date, jc.job_name, jc.job_type, jc.status
        FROM job_cards jc
        WHERE LOWER(COALESCE(jc.status,'')) NOT IN ('posted','cancelled','canceled','completed','closed','rejected','void')
        ORDER BY jc.id DESC
        """
        rows = [row_dict(r) for r in conn.execute(q2).fetchall()]
        print(f"  (job_cards amount query fallback: {e})")
    print(f"\n## Job cards pending ({len(rows)})")
    for r in rows:
        print(f"  {r}")

    # production orders
    po_cols = cols(conn, "production_orders")
    print(f"\nproduction_orders cols: {po_cols}")
    q = """
    SELECT po.document_no, po.order_date, po.status, po.quantity, po.cost_per_unit,
           p.name AS product, po.production_line
    FROM production_orders po
    LEFT JOIN products p ON p.id = po.finished_product_id
    WHERE LOWER(COALESCE(po.status,'')) NOT IN ('posted','cancelled','canceled','completed','closed','rejected','void')
    ORDER BY po.id DESC
    """
    try:
        rows = [row_dict(r) for r in conn.execute(q).fetchall()]
    except Exception as e:
        print(f"  production_orders query error: {e}")
        # try discover
        rows = [row_dict(r) for r in conn.execute(
            "SELECT * FROM production_orders WHERE LOWER(COALESCE(status,'')) NOT IN ('posted','cancelled','canceled','completed','closed','rejected','void') LIMIT 50"
        ).fetchall()]
    print(f"\n## Production orders pending ({len(rows)})")
    for r in rows:
        print(f"  {r}")

# Dashboard
print("\n" + "="*60)
print("get_dashboard_stats / pending_breakdown")
print("="*60)
stats = database.get_dashboard_stats()
pb = stats.get("pending_breakdown") or {}
print("pending_approvals total:", stats.get("pending_approvals"))
print("pending_breakdown:")
for k, v in sorted(pb.items()):
    print(f"  {k}: {v}")
