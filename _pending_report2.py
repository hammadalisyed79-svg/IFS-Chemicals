import database
database.init_db()

def rd(r):
    return {k: r[k] for k in r.keys()} if r is not None else None

with database.get_connection() as conn:
    print("=== SALES INVOICES ===")
    for label, sql in [
        ("by status", "SELECT status, COUNT(*) n FROM sales_invoices GROUP BY 1"),
        ("by approval_status", "SELECT COALESCE(approval_status,'(null)') a, COUNT(*) n FROM sales_invoices GROUP BY 1"),
        ("posted_at null vs set", "SELECT CASE WHEN posted_at IS NULL OR posted_at='' THEN 'unposted' ELSE 'posted' END p, COUNT(*) n FROM sales_invoices GROUP BY 1"),
        ("status x posted", "SELECT status, CASE WHEN posted_at IS NULL OR posted_at='' THEN 'unposted' ELSE 'has_posted_at' END p, COUNT(*) n FROM sales_invoices GROUP BY 1,2"),
        ("draft/pending only", "SELECT status, approval_status, COUNT(*) n FROM sales_invoices WHERE LOWER(COALESCE(status,'')) IN ('draft','pending_approval','pending','submitted') OR LOWER(COALESCE(approval_status,'')) IN ('draft','pending','pending_approval','submitted') GROUP BY 1,2"),
    ]:
        print(label, [tuple(r) for r in conn.execute(sql).fetchall()])

    print("\n=== PURCHASE INVOICES ===")
    for label, sql in [
        ("by status", "SELECT status, COUNT(*) n FROM purchase_invoices GROUP BY 1"),
        ("by approval_status", "SELECT COALESCE(approval_status,'(null)') a, COUNT(*) n FROM purchase_invoices GROUP BY 1"),
        ("posted_at", "SELECT CASE WHEN posted_at IS NULL OR posted_at='' THEN 'unposted' ELSE 'posted' END p, COUNT(*) n FROM purchase_invoices GROUP BY 1"),
        ("draft/pending", "SELECT status, approval_status, COUNT(*) n FROM purchase_invoices WHERE LOWER(COALESCE(status,'')) IN ('draft','pending_approval','pending','submitted') OR LOWER(COALESCE(approval_status,'')) IN ('draft','pending','pending_approval','submitted') GROUP BY 1,2"),
    ]:
        print(label, [tuple(r) for r in conn.execute(sql).fetchall()])

    print("\n=== SALES RETURNS ===")
    print("by approval_status", [tuple(r) for r in conn.execute("SELECT COALESCE(approval_status,'(null)'), COUNT(*) FROM sales_returns GROUP BY 1").fetchall()])
    print("total", conn.execute("SELECT COUNT(*) FROM sales_returns").fetchone()[0])
    rows = conn.execute("""
        SELECT sr.document_no, sr.return_date, c.name party, sr.approval_status, sr.total
        FROM sales_returns sr LEFT JOIN customers c ON c.id=sr.customer_id
        WHERE LOWER(COALESCE(sr.approval_status,'draft')) NOT IN ('approved','posted','cancelled','canceled','completed','closed','rejected','void')
           OR sr.approval_status IS NULL OR sr.approval_status=''
        ORDER BY sr.id DESC LIMIT 100
    """).fetchall()
    print(f"pending-ish returns ({len(rows)} shown):")
    for r in rows: print(" ", rd(r))

    print("\n=== PURCHASE RETURNS ===")
    print("by approval_status", [tuple(r) for r in conn.execute("SELECT COALESCE(approval_status,'(null)'), COUNT(*) FROM purchase_returns GROUP BY 1").fetchall()])
    print("total", conn.execute("SELECT COUNT(*) FROM purchase_returns").fetchone()[0])
    rows = conn.execute("""
        SELECT pr.document_no, pr.return_date, s.name party, pr.approval_status, pr.total
        FROM purchase_returns pr LEFT JOIN suppliers s ON s.id=pr.supplier_id
        WHERE LOWER(COALESCE(pr.approval_status,'draft')) NOT IN ('approved','posted','cancelled','canceled','completed','closed','rejected','void')
           OR pr.approval_status IS NULL OR pr.approval_status=''
        ORDER BY pr.id DESC LIMIT 100
    """).fetchall()
    print(f"pending-ish returns ({len(rows)} shown):")
    for r in rows: print(" ", rd(r))

    print("\n=== JOB CARDS ===")
    print("count", conn.execute("SELECT COUNT(*) FROM job_cards").fetchone()[0])
    print("by status", [tuple(r) for r in conn.execute("SELECT COALESCE(status,'(null)'), COUNT(*) FROM job_cards GROUP BY 1").fetchall()])

    print("\n=== PRODUCTION ORDERS ===")
    print("count", conn.execute("SELECT COUNT(*) FROM production_orders").fetchone()[0])
    print("by status", [tuple(r) for r in conn.execute("SELECT COALESCE(status,'(null)'), COUNT(*) FROM production_orders GROUP BY 1").fetchall()])
    print("by approval_status", [tuple(r) for r in conn.execute("SELECT COALESCE(approval_status,'(null)'), COUNT(*) FROM production_orders GROUP BY 1").fetchall()])

    # Sample of sales with posted_at null if any, and draft
    print("\n=== SI draft/pending_approval list ===")
    rows = conn.execute("""
        SELECT document_no, invoice_date, status, approval_status, posted_at, total
        FROM sales_invoices
        WHERE LOWER(status) IN ('draft','pending_approval','pending','submitted')
           OR LOWER(COALESCE(approval_status,'')) IN ('draft','pending','pending_approval','submitted')
        ORDER BY id DESC LIMIT 200
    """).fetchall()
    print(f"count listed {len(rows)}")
    for r in rows: print(" ", rd(r))

    print("\n=== PI draft/pending_approval list ===")
    rows = conn.execute("""
        SELECT document_no, invoice_date, status, approval_status, posted_at, total
        FROM purchase_invoices
        WHERE LOWER(status) IN ('draft','pending_approval','pending','submitted')
           OR LOWER(COALESCE(approval_status,'')) IN ('draft','pending','pending_approval','submitted')
        ORDER BY id DESC LIMIT 200
    """).fetchall()
    print(f"count listed {len(rows)}")
    for r in rows: print(" ", rd(r))

    # How many SI have posted_at?
    print("\nSI posted_at sample:", [rd(r) for r in conn.execute("SELECT document_no, status, approval_status, posted_at, posted_by FROM sales_invoices ORDER BY id DESC LIMIT 5").fetchall()])
    print("PI posted_at sample:", [rd(r) for r in conn.execute("SELECT document_no, status, approval_status, posted_at, posted_by FROM purchase_invoices ORDER BY id DESC LIMIT 5").fetchall()])

# dashboard
stats = database.get_dashboard_stats()
print("\n=== DASHBOARD pending_breakdown ===")
print("pending_approvals:", stats.get("pending_approvals"))
for k,v in sorted((stats.get("pending_breakdown") or {}).items()):
    print(f"  {k}: {v}")
