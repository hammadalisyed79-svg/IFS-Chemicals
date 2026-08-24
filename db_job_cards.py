"""Job cards — BOM-style: produced item + raw material consumption lines."""

from __future__ import annotations

from pathlib import Path

SCHEMA_JOB_CARDS_PATH = Path(__file__).parent / "schema_job_cards.sql"

JOB_TYPES = {
    "gravure": "Gravure / Wrapper",
    "corrugated": "Corrugated Box (Plant Packages)",
}

DOC_TYPE_BY_JOB = {"gravure": "JCG", "corrugated": "JCC"}

RAW_PRODUCT_TYPE = "raw"
# Consumption lines use any active product from Products master (same as BOM components).
CONSUMPTION_EXCLUDED_TYPES = frozenset({"service"})


def now():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _product_type(row):
    return (row.get("product_type") or row.get("item_type") or "").lower()


def is_consumption_product(product_id, conn=None):
    """True if product exists and may be used on a job card consumption line."""
    if not product_id:
        return False
    from database import get_connection

    def _check(c):
        row = c.execute(
            "SELECT product_type, is_active FROM products WHERE id=?", (product_id,)
        ).fetchone()
        if not row:
            return False
        ptype = (row[0] or "").lower()
        if ptype in CONSUMPTION_EXCLUDED_TYPES:
            return False
        return row[1] is None or int(row[1]) == 1

    if conn is not None:
        return _check(conn)
    with get_connection() as c:
        return _check(c)


def is_raw_material_product(product_id, conn=None):
    """Legacy helper — raw type only."""
    if not product_id:
        return False
    from database import get_connection

    def _check(c):
        row = c.execute("SELECT product_type FROM products WHERE id=?", (product_id,)).fetchone()
        return row and (row[0] or "").lower() == RAW_PRODUCT_TYPE

    if conn is not None:
        return _check(conn)
    with get_connection() as c:
        return _check(c)


def get_raw_material_items(active_only=True):
    """All saved products eligible for job card consumption (not only type=raw)."""
    from database import get_items

    return [
        r for r in get_items(active_only=active_only)
        if _product_type(r) not in CONSUMPTION_EXCLUDED_TYPES
    ]


def get_finished_product_items(active_only=True):
    from database import get_items

    rows = [
        r for r in get_items(active_only=active_only)
        if (r.get("product_type") or r.get("item_type") or "").lower() == "finished"
    ]
    return rows or get_items(active_only=active_only)


def _purchase_rate(conn, product_id):
    row = conn.execute("SELECT purchase_price, name FROM products WHERE id=?", (product_id,)).fetchone()
    if not row:
        return 0.0, ""
    return float(row[0] or 0), row[1] or ""


def _line_amount(qty, rate):
    return round(float(qty or 0) * float(rate or 0), 2)


def _normalize_material_lines(lines, conn):
    out = []
    for i, ln in enumerate(lines or []):
        pid = ln.get("product_id")
        qty = float(ln.get("quantity") if ln.get("quantity") is not None else ln.get("qty_used") or 0)
        if not pid or qty <= 0:
            continue
        if not is_consumption_product(pid, conn):
            _, name = _purchase_rate(conn, pid)
            raise ValueError(f"Invalid or inactive product: {name or pid}")
        rate = float(ln.get("rate") or 0)
        if rate <= 0:
            rate, _ = _purchase_rate(conn, pid)
        _, pname = _purchase_rate(conn, pid)
        out.append({
            "line_no": i + 1,
            "product_id": pid,
            "item_name": pname,
            "qty_used": qty,
            "rate": rate,
            "amount": _line_amount(qty, rate),
        })
    return out


def get_material_lines(jc):
    """Unified consumption lines (new + legacy reel rows)."""
    lines = []
    for ln in jc.get("consumable_lines") or []:
        qty = float(ln.get("qty_used") or 0)
        if ln.get("product_id") and qty > 0:
            lines.append({
                "product_id": ln["product_id"],
                "product_code": ln.get("product_code"),
                "product_name": ln.get("product_name") or ln.get("item_name"),
                "quantity": qty,
                "rate": float(ln.get("rate") or 0),
                "amount": float(ln.get("amount") or 0),
            })
    for ln in jc.get("reel_lines") or []:
        qty = float(ln.get("weight_kg") or 0)
        if ln.get("product_id") and qty > 0:
            lines.append({
                "product_id": ln["product_id"],
                "product_code": ln.get("product_code"),
                "product_name": ln.get("product_name") or ln.get("paper_type"),
                "quantity": qty,
                "rate": float(ln.get("rate") or 0),
                "amount": float(ln.get("amount") or 0),
            })
    return lines


def bom_material_lines(finished_product_id, output_qty):
    """Load consumption lines from approved BOM (like production order)."""
    from database import get_connection
    from db_v3 import get_bom_list, get_bom, calc_bom_requirements

    if not finished_product_id or output_qty <= 0:
        return []
    approved = [
        b for b in get_bom_list()
        if b.get("finished_product_id") == finished_product_id and b.get("status") == "approved"
    ]
    if not approved:
        return []
    bom = approved[0]
    detail = get_bom(bom["id"])
    rate_map = {
        l["raw_product_id"]: float(l.get("standard_cost") or 0)
        for l in (detail.get("lines") or [])
    }
    reqs = calc_bom_requirements(bom["id"], output_qty)
    lines = []
    with get_connection() as conn:
        for r in reqs:
            pid = r.get("product_id")
            if not pid or not is_consumption_product(pid, conn):
                continue
            rate = rate_map.get(pid) or 0
            if rate <= 0:
                rate, _ = _purchase_rate(conn, pid)
            lines.append({
                "product_id": pid,
                "quantity": float(r.get("quantity") or 0),
                "rate": rate,
            })
    return lines


def apply_job_cards(conn, db_module):
    if SCHEMA_JOB_CARDS_PATH.exists():
        conn.executescript(SCHEMA_JOB_CARDS_PATH.read_text(encoding="utf-8"))
    for doc_type in ("JCG", "JCC"):
        if not conn.execute(
            "SELECT 1 FROM document_sequences WHERE doc_type=?", (doc_type,)
        ).fetchone():
            conn.execute(
                "INSERT INTO document_sequences(doc_type, prefix, last_number, padding) VALUES(?,?,?,?)",
                (doc_type, doc_type, 0, 4),
            )
    if hasattr(db_module, "DOC_NUMBER_SOURCES"):
        db_module.DOC_NUMBER_SOURCES.setdefault("JCG", [("job_cards", "document_no")])
        db_module.DOC_NUMBER_SOURCES.setdefault("JCC", [("job_cards", "document_no")])


def save_job_card(data, material_lines, job_id=None, user_id=None):
    from database import get_connection, ensure_document_no

    job_type = data["job_type"]
    doc_type = DOC_TYPE_BY_JOB[job_type]
    finished_qty = float(data.get("finished_qty") or 0)
    ts = now()

    with get_connection() as conn:
        lines = _normalize_material_lines(material_lines, conn)
        if not lines:
            raise ValueError("Add at least one product consumption line with quantity.")
        mat_cost = round(sum(ln["amount"] for ln in lines), 2)
        cpu = round(mat_cost / finished_qty, 4) if finished_qty else 0
        job_name = (data.get("job_name") or "").strip()
        if not job_name and data.get("finished_product_id"):
            _, job_name = _purchase_rate(conn, data["finished_product_id"])

        fields = (
            data["job_date"], job_name, data.get("finished_product_id"), data.get("warehouse_id"),
            finished_qty, mat_cost, mat_cost, cpu,
            data.get("remarks"), user_id, ts,
        )
        if job_id:
            row = conn.execute("SELECT status FROM job_cards WHERE id=?", (job_id,)).fetchone()
            if not row:
                raise ValueError("Job card not found.")
            if row[0] != "draft":
                raise ValueError("Only draft job cards can be edited.")
            conn.execute(
                """UPDATE job_cards SET job_date=?, job_name=?, finished_product_id=?, warehouse_id=?,
                   finished_qty=?, total_reel_cost=0, total_consumable_cost=?, total_material_cost=?,
                   cost_per_unit=?, remarks=?, modified_by=?, modified_at=? WHERE id=?""",
                (*fields, job_id),
            )
            conn.execute("DELETE FROM job_card_reel_lines WHERE job_card_id=?", (job_id,))
            conn.execute("DELETE FROM job_card_consumable_lines WHERE job_card_id=?", (job_id,))
        else:
            doc_no = ensure_document_no(doc_type, data.get("document_no"), conn)
            cur = conn.execute(
                """INSERT INTO job_cards(document_no, job_type, job_date, job_name, finished_product_id,
                   warehouse_id, finished_qty, total_reel_cost, total_consumable_cost, total_material_cost,
                   cost_per_unit, remarks, created_by)
                   VALUES(?,?,?,?,?,?,?,0,?,?,?,?,?)""",
                (
                    doc_no, job_type, data["job_date"], job_name, data.get("finished_product_id"),
                    data.get("warehouse_id"), finished_qty, mat_cost, mat_cost, cpu,
                    data.get("remarks"), user_id,
                ),
            )
            job_id = cur.lastrowid

        for ln in lines:
            conn.execute(
                """INSERT INTO job_card_consumable_lines(job_card_id,line_no,section,product_id,item_name,
                   issued_qty,returned_qty,qty_used,rate,amount) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (
                    job_id, ln["line_no"], "material", ln["product_id"], ln["item_name"],
                    ln["qty_used"], 0, ln["qty_used"], ln["rate"], ln["amount"],
                ),
            )
        return job_id


def get_job_card(job_id):
    from database import get_connection, row_to_dict, rows_to_list

    with get_connection() as conn:
        h = row_to_dict(conn.execute(
            """SELECT jc.*, p.code AS finished_product_code, p.name AS finished_product_name
               FROM job_cards jc
               LEFT JOIN products p ON jc.finished_product_id=p.id WHERE jc.id=?""",
            (job_id,),
        ).fetchone())
        if not h:
            return None
        h["reel_lines"] = rows_to_list(conn.execute(
            """SELECT rl.*, p.code AS product_code, p.name AS product_name
               FROM job_card_reel_lines rl LEFT JOIN products p ON rl.product_id=p.id
               WHERE rl.job_card_id=? ORDER BY rl.line_no""",
            (job_id,),
        ).fetchall())
        h["consumable_lines"] = rows_to_list(conn.execute(
            """SELECT cl.*, p.code AS product_code, p.name AS product_name
               FROM job_card_consumable_lines cl LEFT JOIN products p ON cl.product_id=p.id
               WHERE cl.job_card_id=? ORDER BY cl.line_no""",
            (job_id,),
        ).fetchall())
        h["material_lines"] = get_material_lines(h)
        return h


def get_job_cards(job_type=None, from_date=None, to_date=None, status=None):
    from database import get_connection, rows_to_list

    q = """SELECT jc.*, p.name AS finished_product_name, p.code AS finished_product_code
           FROM job_cards jc LEFT JOIN products p ON jc.finished_product_id=p.id WHERE 1=1"""
    params = []
    if job_type:
        q += " AND jc.job_type=?"; params.append(job_type)
    if from_date:
        q += " AND jc.job_date>=?"; params.append(from_date)
    if to_date:
        q += " AND jc.job_date<=?"; params.append(to_date)
    if status:
        q += " AND jc.status=?"; params.append(status)
    q += " ORDER BY jc.job_date DESC, jc.id DESC"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, params).fetchall())


def _job_card_stock_shortages(lines, warehouse_id, conn):
    """Lines where required qty exceeds warehouse stock (informational only)."""
    import database as db

    wh = warehouse_id or db._default_warehouse_id(conn)
    out = []
    for ln in lines:
        qty = float(ln["quantity"])
        pid = ln["product_id"]
        row = conn.execute(
            "SELECT COALESCE(quantity,0) FROM warehouse_stock WHERE warehouse_id=? AND product_id=?",
            (wh, pid),
        ).fetchone()
        avail = float(row[0]) if row else 0.0
        if avail < qty:
            name = ln.get("product_name") or ln.get("product_code") or pid
            out.append(f"Insufficient stock: {name} (available {avail:g}, need {qty:g})")
    return out


def job_card_stock_warnings(jc):
    """Stock shortfalls for a draft job card (does not block posting)."""
    lines = get_material_lines(jc)
    if not lines:
        return []
    from database import get_connection

    with get_connection() as conn:
        return _job_card_stock_shortages(lines, jc.get("warehouse_id"), conn)


def post_job_card(job_id, user_id=None):
    """Post job card to stock. Returns stock warning messages (post always proceeds)."""
    import database as db
    from db_v3 import post_gl, gl_account_code

    jc = get_job_card(job_id)
    if not jc:
        raise ValueError("Job card not found.")
    if jc["status"] != "draft":
        raise ValueError("Job card is already posted.")
    lines = get_material_lines(jc)
    if not lines:
        raise ValueError("No consumption lines to post.")

    warnings = []
    with db.get_connection() as conn:
        wh = jc.get("warehouse_id") or db._default_warehouse_id(conn)
        warnings = _job_card_stock_shortages(lines, wh, conn)
        total_mat = 0.0
        for ln in lines:
            qty = float(ln["quantity"])
            pid = ln["product_id"]
            if not is_consumption_product(pid, conn):
                raise ValueError(f"Invalid product for consumption: {ln.get('product_name')}")
            rate = float(ln.get("rate") or 0)
            if rate <= 0:
                rate, _ = _purchase_rate(conn, pid)
            total_mat += qty * rate
            db._adjust_warehouse_stock(conn, pid, wh, -qty)
            db._record_movement(conn, pid, wh, "out", qty, "job_card", job_id, jc["document_no"], user_id)

        fg_qty = float(jc.get("finished_qty") or 0)
        fg_id = jc.get("finished_product_id")
        if fg_qty <= 0 or not fg_id:
            raise ValueError("Produced item and production quantity are required to post.")
        conn.execute(
            "INSERT OR REPLACE INTO product_batches(batch_no,product_id,warehouse_id,quantity,mfg_date,created_by) "
            "VALUES(?,?,?,?,date('now'),?)",
            (jc["document_no"], fg_id, wh, fg_qty, user_id),
        )
        db._adjust_warehouse_stock(conn, fg_id, wh, fg_qty)
        db._record_movement(conn, fg_id, wh, "in", fg_qty, "job_card", job_id, jc["document_no"], user_id)
        try:
            post_gl(conn, jc["job_date"], gl_account_code("fg_inv"), total_mat, 0,
                    "Job card FG", "job_card", job_id, jc["document_no"], user_id)
            post_gl(conn, jc["job_date"], gl_account_code("raw_inv"), 0, total_mat,
                    "Job card consumption", "job_card", job_id, jc["document_no"], user_id)
        except Exception:
            pass
        conn.execute(
            """UPDATE job_cards SET status='posted', posted_by=?, posted_at=?, total_material_cost=?,
               cost_per_unit=?, modified_at=? WHERE id=?""",
            (user_id, now(), total_mat, (total_mat / fg_qty if fg_qty else 0), now(), job_id),
        )
    return warnings


def delete_job_card(job_id):
    from database import get_connection

    with get_connection() as conn:
        row = conn.execute("SELECT status FROM job_cards WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise ValueError("Job card not found.")
        if row[0] != "draft":
            raise ValueError("Only draft job cards can be deleted.")
        conn.execute("DELETE FROM job_cards WHERE id=?", (job_id,))
