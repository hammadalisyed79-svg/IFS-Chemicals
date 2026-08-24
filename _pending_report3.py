import database
database.init_db()
with database.get_connection() as conn:
    cols = [r[1] for r in conn.execute("PRAGMA table_info(general_ledger)").fetchall()]
    print("GL cols:", cols)
    # find doc ref columns
    for c in cols:
        if "doc" in c.lower() or "ref" in c.lower() or "source" in c.lower() or "voucher" in c.lower():
            print(" candidate", c)
    # try common patterns
    for sql in [
        "SELECT COUNT(DISTINCT si.document_no) FROM sales_invoices si WHERE EXISTS (SELECT 1 FROM general_ledger g WHERE g.document_no=si.document_no)",
        "SELECT COUNT(DISTINCT si.document_no) FROM sales_invoices si WHERE EXISTS (SELECT 1 FROM general_ledger g WHERE g.ref_no=si.document_no)",
        "SELECT COUNT(DISTINCT si.document_no) FROM sales_invoices si WHERE EXISTS (SELECT 1 FROM general_ledger g WHERE g.source_document=si.document_no)",
    ]:
        try:
            print(sql.split("WHERE")[1][:60], "=>", conn.execute(sql).fetchone()[0])
        except Exception as e:
            print("fail", e)

    n_si = conn.execute("SELECT COUNT(*) FROM sales_invoices").fetchone()[0]
    n_pi = conn.execute("SELECT COUNT(*) FROM purchase_invoices").fetchone()[0]
    print("totals SI/PI", n_si, n_pi)

    print("erp_draft_registry", conn.execute("SELECT COUNT(*) FROM erp_draft_registry").fetchone()[0])
    for t in ["ifs_batch_tickets","ifs_reactor_batches","ifs_spray_dryer_batches","ifs_toll_production","ifs_gravure_runs","ifs_corrugated_runs","ifs_pet_blowing_runs","weight_slips"]:
        ex = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()
        if not ex: continue
        c = [r[1] for r in conn.execute(f"PRAGMA table_info({t})").fetchall()]
        cnt = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        st = ""
        if "status" in c and cnt:
            st = [tuple(r) for r in conn.execute(f"SELECT status, COUNT(*) FROM {t} GROUP BY 1").fetchall()]
        print(f"{t}: {cnt} status={st}")
