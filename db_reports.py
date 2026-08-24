"""Extended report queries for Reporting & Printing Center."""

from database import get_connection, rows_to_list, row_to_dict, _product_stock_join, _product_stock_sql


def get_purchase_tax_report(from_date=None, to_date=None):
    q = """SELECT document_no AS invoice_no, invoice_date, subtotal, discount, taxable_amount,
                  sales_tax, further_tax, extra_tax, fed_tax, wht_tax, total
           FROM purchase_invoices WHERE status='approved'"""
    p = []
    if from_date:
        q += " AND invoice_date>=?"
        p.append(from_date)
    if to_date:
        q += " AND invoice_date<=?"
        p.append(to_date)
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


def get_sales_invoice_register(from_date=None, to_date=None, customer_id=None, product_id=None,
                               customer_group_id=None, product_group_id=None):
    q = """SELECT s.document_no AS invoice_no, s.invoice_date, c.name AS customer,
                  cg.name AS customer_group, p.code AS product_code, p.name AS product,
                  pg.name AS product_group,
                  si.quantity, si.net_weight,
                  si.rate, si.amount, si.line_discount, si.tax_amount,
                  s.total_net_weight AS invoice_total_weight, ws.document_no AS weight_slip_no,
                  ws.net_weight AS physical_weight, ws.weight_difference AS weight_variance,
                  s.total AS invoice_total
           FROM sales_invoice_items si
           JOIN sales_invoices s ON si.invoice_id=s.id
           JOIN customers c ON s.customer_id=c.id
           JOIN products p ON si.product_id=p.id
           LEFT JOIN master_groups cg ON c.group_id=cg.id AND cg.entity_type='customer'
           LEFT JOIN master_groups pg ON p.group_id=pg.id AND pg.entity_type='product'
           LEFT JOIN weight_slips ws ON s.weight_slip_id=ws.id WHERE 1=1"""
    params = []
    if from_date:
        q += " AND s.invoice_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND s.invoice_date<=?"
        params.append(to_date)
    if customer_id:
        q += " AND s.customer_id=?"
        params.append(customer_id)
    if product_id:
        q += " AND si.product_id=?"
        params.append(product_id)
    if customer_group_id:
        q += " AND c.group_id=?"
        params.append(customer_group_id)
    if product_group_id:
        q += " AND p.group_id=?"
        params.append(product_group_id)
    q += " ORDER BY s.invoice_date DESC, s.document_no"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, params).fetchall())


def get_purchase_invoice_register(from_date=None, to_date=None, supplier_id=None, product_id=None,
                                  supplier_group_id=None, product_group_id=None):
    q = """SELECT pi.document_no AS invoice_no, pi.invoice_date, s.name AS supplier,
                  sg.name AS supplier_group, p.code AS product_code, p.name AS product,
                  pg.name AS product_group,
                  pii.quantity, pii.net_weight,
                  pii.rate, pii.amount, pii.line_discount, pii.tax_amount,
                  pi.total_net_weight AS invoice_total_weight, ws.document_no AS weight_slip_no,
                  ws.net_weight AS physical_weight, ws.weight_difference AS weight_variance,
                  pi.total AS invoice_total
           FROM purchase_invoice_items pii
           JOIN purchase_invoices pi ON pii.invoice_id=pi.id
           JOIN suppliers s ON pi.supplier_id=s.id
           JOIN products p ON pii.product_id=p.id
           LEFT JOIN master_groups sg ON s.group_id=sg.id AND sg.entity_type='supplier'
           LEFT JOIN master_groups pg ON p.group_id=pg.id AND pg.entity_type='product'
           LEFT JOIN weight_slips ws ON pi.weight_slip_id=ws.id WHERE 1=1"""
    params = []
    if from_date:
        q += " AND pi.invoice_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND pi.invoice_date<=?"
        params.append(to_date)
    if supplier_id:
        q += " AND pi.supplier_id=?"
        params.append(supplier_id)
    if product_id:
        q += " AND pii.product_id=?"
        params.append(product_id)
    if supplier_group_id:
        q += " AND s.group_id=?"
        params.append(supplier_group_id)
    if product_group_id:
        q += " AND p.group_id=?"
        params.append(product_group_id)
    q += " ORDER BY pi.invoice_date DESC, pi.document_no"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, params).fetchall())


def get_item_wise_sale_detail(from_date=None, to_date=None, customer_id=None, product_id=None,
                              customer_group_id=None, product_group_id=None):
    """Line-level sales grouped by product (Finance Manager Item Wise Sales Detail layout)."""
    q = """SELECT p.id AS product_id, p.code AS product_code, p.name AS product_name,
                  s.invoice_date AS date, s.document_no AS invoice_no,
                  CASE WHEN LOWER(COALESCE(s.payment_mode, '')) = 'cash'
                       THEN 'SALE IN CASH' ELSE c.name END AS name,
                  COALESCE(c.city, '') AS city,
                  si.quantity AS quantity, si.rate AS rate, si.amount AS amount
           FROM sales_invoice_items si
           JOIN sales_invoices s ON si.invoice_id = s.id
           JOIN customers c ON s.customer_id = c.id
           JOIN products p ON si.product_id = p.id
           WHERE COALESCE(s.status, 'approved') = 'approved'"""
    params = []
    if from_date:
        q += " AND s.invoice_date >= ?"
        params.append(from_date)
    if to_date:
        q += " AND s.invoice_date <= ?"
        params.append(to_date)
    if customer_id:
        q += " AND s.customer_id = ?"
        params.append(customer_id)
    if product_id:
        q += " AND si.product_id = ?"
        params.append(product_id)
    if customer_group_id:
        q += " AND c.group_id = ?"
        params.append(customer_group_id)
    if product_group_id:
        q += " AND p.group_id = ?"
        params.append(product_group_id)
    q += " ORDER BY p.code, s.invoice_date, s.document_no, si.id"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, params).fetchall())


def get_item_wise_purchase_detail(from_date=None, to_date=None, supplier_id=None, product_id=None,
                                  supplier_group_id=None, product_group_id=None):
    """Line-level purchases grouped by product (Finance Manager Item Wise Purchase Detail layout)."""
    q = """SELECT p.id AS product_id, p.code AS product_code, p.name AS product_name,
                  pi.invoice_date AS date, pi.document_no AS invoice_no,
                  s.name AS name, COALESCE(s.city, '') AS city,
                  pii.quantity AS quantity,
                  COALESCE(pii.net_weight, 0) AS net_weight,
                  pii.rate AS rate, pii.amount AS amount
           FROM purchase_invoice_items pii
           JOIN purchase_invoices pi ON pii.invoice_id = pi.id
           JOIN suppliers s ON pi.supplier_id = s.id
           JOIN products p ON pii.product_id = p.id
           WHERE COALESCE(pi.status, 'approved') = 'approved'"""
    params = []
    if from_date:
        q += " AND pi.invoice_date >= ?"
        params.append(from_date)
    if to_date:
        q += " AND pi.invoice_date <= ?"
        params.append(to_date)
    if supplier_id:
        q += " AND pi.supplier_id = ?"
        params.append(supplier_id)
    if product_id:
        q += " AND pii.product_id = ?"
        params.append(product_id)
    if supplier_group_id:
        q += " AND s.group_id = ?"
        params.append(supplier_group_id)
    if product_group_id:
        q += " AND p.group_id = ?"
        params.append(product_group_id)
    q += " ORDER BY p.code, pi.invoice_date, pi.document_no, pii.id"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, params).fetchall())


def get_product_wise_purchase(from_date=None, to_date=None, supplier_id=None,
                              supplier_group_id=None, product_group_id=None, view_mode="detail"):
    from db_report_groups import summarize_product_sales

    q = """SELECT p.code, p.name, p.group_id, mg.code AS group_code, mg.name AS group_name,
                  SUM(pii.quantity) AS qty, SUM(pii.amount) AS amount
           FROM purchase_invoice_items pii
           JOIN purchase_invoices pi ON pii.invoice_id=pi.id
           JOIN products p ON pii.product_id=p.id
           LEFT JOIN master_groups mg ON p.group_id=mg.id AND mg.entity_type='product'
           WHERE 1=1"""
    params = []
    if from_date:
        q += " AND pi.invoice_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND pi.invoice_date<=?"
        params.append(to_date)
    if supplier_id:
        q += " AND pi.supplier_id=?"
        params.append(supplier_id)
    if supplier_group_id:
        q += " AND pi.supplier_id IN (SELECT id FROM suppliers WHERE group_id=?)"
        params.append(supplier_group_id)
    if product_group_id:
        q += " AND p.group_id=?"
        params.append(product_group_id)
    q += " GROUP BY p.id ORDER BY amount DESC"
    with get_connection() as conn:
        rows = rows_to_list(conn.execute(q, params).fetchall())
    return summarize_product_sales(rows, view_mode)


def get_sales_returns_report(from_date=None, to_date=None, customer_id=None, customer_group_id=None):
    q = """SELECT sr.document_no AS return_no, sr.return_date, c.name AS customer,
                  si.document_no AS invoice_no,
                  sr.subtotal, sr.total, sr.notes
           FROM sales_returns sr
           JOIN customers c ON sr.customer_id=c.id
           LEFT JOIN sales_invoices si ON sr.invoice_id=si.id
           WHERE 1=1"""
    params = []
    if from_date:
        q += " AND sr.return_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND sr.return_date<=?"
        params.append(to_date)
    if customer_id:
        q += " AND sr.customer_id=?"
        params.append(customer_id)
    if customer_group_id:
        q += " AND c.group_id=?"
        params.append(customer_group_id)
    q += " ORDER BY sr.return_date DESC, sr.id DESC"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, params).fetchall())


def get_purchase_returns_report(from_date=None, to_date=None, supplier_id=None, supplier_group_id=None):
    q = """SELECT pr.document_no AS return_no, pr.return_date, s.name AS supplier,
                  pi.document_no AS invoice_no,
                  pr.subtotal, pr.total, pr.notes
           FROM purchase_returns pr
           JOIN suppliers s ON pr.supplier_id=s.id
           LEFT JOIN purchase_invoices pi ON pr.invoice_id=pi.id
           WHERE 1=1"""
    params = []
    if from_date:
        q += " AND pr.return_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND pr.return_date<=?"
        params.append(to_date)
    if supplier_id:
        q += " AND pr.supplier_id=?"
        params.append(supplier_id)
    if supplier_group_id:
        q += " AND s.group_id=?"
        params.append(supplier_group_id)
    q += " ORDER BY pr.return_date DESC, pr.id DESC"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, params).fetchall())


def get_warehouse_stock(warehouse_id=None):
    unit = """COALESCE(wac.avg_cost, p.purchase_price, 0)"""
    q = f"""SELECT w.name AS warehouse, p.code, p.name, ws.quantity, u.symbol AS unit,
                   p.purchase_price, {unit} AS unit_cost,
                   (ws.quantity * ({unit})) AS value
            FROM warehouse_stock ws
            JOIN warehouses w ON ws.warehouse_id=w.id
            JOIN products p ON ws.product_id=p.id
            LEFT JOIN warehouse_product_avg_cost wac
              ON wac.warehouse_id = ws.warehouse_id AND wac.product_id = ws.product_id
            LEFT JOIN units_of_measure u ON p.unit_id=u.id WHERE p.is_active=1"""
    params = []
    if warehouse_id:
        q += " AND ws.warehouse_id=?"
        params.append(warehouse_id)
    q += " ORDER BY w.name, p.name"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, params).fetchall())


def get_reorder_report():
    stk = _product_stock_join("p")
    sc = _product_stock_sql("p")
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            f"""SELECT p.code, p.name, {sc} AS stock_qty,
                       p.reorder_level, p.purchase_price
                FROM products p {stk} WHERE p.is_active=1 AND p.reorder_level>0
                AND {sc} <= p.reorder_level ORDER BY p.name"""
        ).fetchall())


def get_negative_stock_report():
    stk = _product_stock_join("p")
    sc = _product_stock_sql("p")
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            f"""SELECT p.code, p.name, {sc} AS stock_qty, u.symbol AS unit
                FROM products p {stk}
                LEFT JOIN units_of_measure u ON p.unit_id=u.id
                WHERE p.is_active=1 AND {sc} < 0 ORDER BY stock_qty"""
        ).fetchall())


def get_stock_ledger(product_id=None, from_date=None, to_date=None):
    q = """SELECT im.movement_date AS date, im.reference_no AS ref, im.movement_type,
                  im.quantity, im.reference_type, im.reason, p.code, p.name
           FROM inventory_movements im
           JOIN products p ON im.product_id=p.id WHERE 1=1"""
    params = []
    if product_id:
        q += " AND im.product_id=?"
        params.append(product_id)
    if from_date:
        q += " AND im.movement_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND im.movement_date<=?"
        params.append(to_date)
    q += " ORDER BY im.movement_date, im.id"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, params).fetchall())


def get_bom_cost_sheet():
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            """SELECT b.document_no AS bom_no, fp.name AS finished_product, b.standard_output_qty,
                      rp.name AS raw_material, bl.quantity AS rm_qty, bl.standard_cost,
                      (bl.quantity * bl.standard_cost) AS line_cost
               FROM bom_formula_lines bl
               JOIN bom_formulas b ON bl.bom_id=b.id
               JOIN products fp ON b.finished_product_id=fp.id
               JOIN products rp ON bl.raw_product_id=rp.id
               ORDER BY b.document_no, rp.name"""
        ).fetchall())


def get_production_register(from_date=None, to_date=None):
    q = """SELECT po.document_no, po.order_date, fp.name AS product, po.planned_qty,
                  po.actual_qty, po.wastage_qty, po.actual_cost, po.cost_per_unit, po.status
           FROM production_orders po
           JOIN products fp ON po.finished_product_id=fp.id WHERE 1=1"""
    params = []
    if from_date:
        q += " AND po.order_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND po.order_date<=?"
        params.append(to_date)
    q += " ORDER BY po.order_date DESC"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, params).fetchall())


def get_rm_consumption(from_date=None, to_date=None, production_order_id=None):
    q = """SELECT po.document_no, po.batch_no, po.order_date, fp.name AS finished_product,
                  rm.code AS raw_material_code, rm.name AS raw_material,
                  pmi.quantity AS consumed_qty, pmi.weight, pmi.rate, pmi.amount
           FROM production_material_issues pmi
           JOIN production_orders po ON pmi.production_order_id=po.id
           JOIN products fp ON po.finished_product_id=fp.id
           JOIN products rm ON pmi.product_id=rm.id WHERE 1=1"""
    params = []
    if production_order_id:
        q += " AND po.id=?"
        params.append(int(production_order_id))
    if from_date:
        q += " AND po.order_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND po.order_date<=?"
        params.append(to_date)
    q += " ORDER BY po.order_date, po.document_no, rm.name"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, params).fetchall())


def list_production_orders_with_consumption(from_date=None, to_date=None):
    """Production orders that have RM issues — for consumption-by-order picker."""
    q = """SELECT DISTINCT po.id, po.document_no, po.batch_no, po.order_date, po.status,
                  po.planned_qty, po.actual_qty, fp.name AS product_name
           FROM production_orders po
           JOIN products fp ON po.finished_product_id = fp.id
           JOIN production_material_issues pmi ON pmi.production_order_id = po.id
           WHERE 1=1"""
    params = []
    if from_date:
        q += " AND po.order_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND po.order_date<=?"
        params.append(to_date)
    q += " ORDER BY po.order_date DESC, po.id DESC"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, params).fetchall())


def get_production_consumption_by_order(production_order_id):
    """RM consumption for one production order (consumption note by PRO number)."""
    if not production_order_id:
        return []
    return get_rm_consumption(production_order_id=int(production_order_id))


def get_finished_goods_report(from_date=None, to_date=None):
    q = """SELECT po.document_no, po.order_date, fp.name AS product,
                  pfr.quantity AS qty_received, po.cost_per_unit,
                  (pfr.quantity * po.cost_per_unit) AS value
           FROM production_finished_receipts pfr
           JOIN production_orders po ON pfr.production_order_id=po.id
           JOIN products fp ON po.finished_product_id=fp.id WHERE 1=1"""
    params = []
    if from_date:
        q += " AND po.order_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND po.order_date<=?"
        params.append(to_date)
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, params).fetchall())


def get_journal_register(from_date=None, to_date=None):
    q = """SELECT jv.document_no, jv.voucher_date, jv.description, jv.total_debit, jv.total_credit, jv.status
           FROM journal_vouchers jv WHERE 1=1"""
    params = []
    if from_date:
        q += " AND jv.voucher_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND jv.voucher_date<=?"
        params.append(to_date)
    q += " ORDER BY jv.voucher_date DESC"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, params).fetchall())


def get_gate_pass_register(pass_type=None, from_date=None, to_date=None):
    q = """SELECT gp.document_no, gp.pass_date, gp.pass_type, gp.vehicle_no, gp.driver_name,
                  gp.party_name, gp.material_desc, gp.quantity, gp.weight, gp.status,
                  si.document_no AS sales_invoice_no, pi.document_no AS purchase_invoice_no,
                  dn.document_no AS delivery_note_no, grn.document_no AS grn_no
           FROM gate_passes gp
           LEFT JOIN sales_invoices si ON gp.sales_invoice_id=si.id
           LEFT JOIN purchase_invoices pi ON gp.purchase_invoice_id=pi.id
           LEFT JOIN delivery_notes dn ON gp.delivery_note_id=dn.id
           LEFT JOIN goods_receipt_notes grn ON gp.grn_id=grn.id
           WHERE 1=1"""
    params = []
    if pass_type:
        q += " AND gp.pass_type=?"
        params.append(pass_type)
    if from_date:
        q += " AND gp.pass_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND gp.pass_date<=?"
        params.append(to_date)
    q += " ORDER BY gp.pass_date DESC"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, params).fetchall())


def get_weight_report_by_vehicle(from_date=None, to_date=None):
    q = """SELECT vehicle_no, COUNT(*) AS slips, SUM(net_weight) AS total_net
           FROM weight_slips WHERE 1=1"""
    params = []
    if from_date:
        q += " AND slip_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND slip_date<=?"
        params.append(to_date)
    q += " GROUP BY vehicle_no ORDER BY total_net DESC"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, params).fetchall())


def get_weight_report_by_party(from_date=None, to_date=None, party="customer"):
    col = "customer_id" if party == "customer" else "supplier_id"
    join = "customers c ON ws.customer_id=c.id" if party == "customer" else "suppliers c ON ws.supplier_id=c.id"
    q = f"""SELECT c.name AS party, COUNT(*) AS slips, SUM(ws.net_weight) AS total_net
            FROM weight_slips ws JOIN {join} WHERE ws.{col} IS NOT NULL"""
    params = []
    if from_date:
        q += " AND ws.slip_date>=?"
        params.append(from_date)
    if to_date:
        q += " AND ws.slip_date<=?"
        params.append(to_date)
    q += " GROUP BY c.id ORDER BY total_net DESC"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, params).fetchall())


def get_weight_variance_report(from_date=None, to_date=None, kind=None):
    rows = get_weight_variance_report_all(from_date, to_date)
    if kind == "sales":
        return [r for r in rows if r.get("doc_type") == "Sales"]
    if kind == "purchase":
        return [r for r in rows if r.get("doc_type") == "Purchase"]
    return rows


def get_weight_variance_report_all(from_date=None, to_date=None):
    """Invoices linked to weight slips with physical vs invoice weight variance."""
    parts = []
    for kind, inv_t, party_t, party_c in [
        ("Sales", "sales_invoices", "customers", "customer"),
        ("Purchase", "purchase_invoices", "suppliers", "supplier"),
    ]:
        ref = "sales_invoice" if kind == "Sales" else "purchase_invoice"
        q = f"""SELECT '{kind}' AS doc_type, i.document_no AS invoice_no, i.invoice_date,
                       pt.name AS {party_c}, ws.document_no AS weight_slip_no,
                       i.total_net_weight AS invoice_weight_kg, ws.net_weight AS physical_weight_kg,
                       ws.weight_difference AS variance_kg, ws.vehicle_no
                FROM {inv_t} i
                JOIN {party_t} pt ON i.{"customer" if kind == "Sales" else "supplier"}_id=pt.id
                JOIN weight_slips ws ON i.weight_slip_id=ws.id
                WHERE i.weight_slip_id IS NOT NULL"""
        p = []
        if from_date:
            q += " AND i.invoice_date>=?"
            p.append(from_date)
        if to_date:
            q += " AND i.invoice_date<=?"
            p.append(to_date)
        parts.append((q, p))
    rows = []
    with get_connection() as conn:
        for q, p in parts:
            rows.extend(rows_to_list(conn.execute(q, p).fetchall()))
    rows.sort(key=lambda r: (r.get("invoice_date") or "", r.get("invoice_no") or ""), reverse=True)
    return rows


def _table_exists(conn, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,),
    ).fetchone()
    return bool(row)


def _table_columns(conn, name: str) -> set[str]:
    if not _table_exists(conn, name):
        return set()
    return {r[1] for r in conn.execute(f"PRAGMA table_info({name})").fetchall()}


def _party_display(conn, party_type, party_id) -> str:
    if not party_type or not party_id:
        return ""
    pt = str(party_type).lower()
    try:
        pid = int(party_id)
    except (TypeError, ValueError):
        return ""
    if pt == "customer":
        row = conn.execute(
            "SELECT code, name FROM customers WHERE id=?", (pid,),
        ).fetchone()
        if not row:
            return ""
        return f"{row['code']} - {row['name']}" if row["code"] else (row["name"] or "")
    if pt == "supplier":
        row = conn.execute(
            "SELECT code, name FROM suppliers WHERE id=?", (pid,),
        ).fetchone()
        if not row:
            return ""
        return f"{row['code']} - {row['name']}" if row["code"] else (row["name"] or "")
    if pt == "employee":
        try:
            row = conn.execute(
                "SELECT code, full_name FROM employees WHERE id=?", (pid,),
            ).fetchone()
        except Exception:
            row = conn.execute(
                "SELECT full_name FROM employees WHERE id=?", (pid,),
            ).fetchone()
            if row:
                return row["full_name"] or ""
            return ""
        if not row:
            return ""
        name = row["full_name"] or ""
        code = (row["code"] or "").strip() if "code" in row.keys() else ""
        return f"{code} - {name}" if code else name
    if pt in ("expense", "account", "gl"):
        return _gl_account_display(conn, pid)
    return ""


def _gl_account_display(conn, account_id) -> str:
    if not account_id:
        return ""
    try:
        aid = int(account_id)
    except (TypeError, ValueError):
        return ""
    row = conn.execute(
        "SELECT code, name FROM chart_of_accounts WHERE id=?", (aid,),
    ).fetchone()
    if not row:
        return ""
    code = (row["code"] or "").strip()
    name = (row["name"] or "").strip()
    if code and name:
        return f"{code} - {name}"
    return name or code


def _gl_contra_heads(conn, document_no, exclude_account_id=None) -> str:
    """
    Non-cash/bank GL heads posted for a cash/bank voucher (reference_no = document_no).
    Used when party_type was not stored (typical FMYE import).
    """
    doc = (document_no or "").strip()
    if not doc or not _table_exists(conn, "general_ledger"):
        return ""
    try:
        excl = int(exclude_account_id) if exclude_account_id not in (None, "") else None
    except (TypeError, ValueError):
        excl = None
    # Typical cash / cash-in-hand codes to skip when picking the contra head
    cash_like = {"000000", "1000", "100000"}
    rows = conn.execute(
        """SELECT a.id, a.code, a.name, gl.debit, gl.credit
           FROM general_ledger gl
           JOIN chart_of_accounts a ON gl.account_id=a.id
           WHERE gl.reference_no=? OR gl.reference_no=?
           ORDER BY ABS(COALESCE(gl.debit,0)+COALESCE(gl.credit,0)) DESC, gl.id""",
        (doc, f"FMYE-{doc}" if not doc.upper().startswith("FMYE-") else doc),
    ).fetchall()
    heads = []
    seen = set()
    for r in rows:
        code = (r["code"] or "").strip()
        if code in cash_like:
            continue
        if excl is not None and int(r["id"]) == excl:
            continue
        # Skip pure cash/bank book side when name looks like cash
        name_l = (r["name"] or "").strip().lower()
        if name_l in ("cash a/c", "cash in hand", "cash"):
            continue
        label = f"{code} - {r['name']}" if code else (r["name"] or "")
        if label and label not in seen:
            seen.add(label)
            heads.append(label)
        if len(heads) >= 2:
            break
    return " + ".join(heads)


def _cash_bank_party_label(conn, row: dict) -> str:
    """Party / GL head for cash & bank vouchers."""
    pt = row.get("party_type")
    pid = row.get("party_id")
    party = _party_display(conn, pt, pid)
    if party:
        return party
    # FMYE / legacy: resolve contra GL from posted ledger
    contra = _gl_contra_heads(
        conn,
        row.get("document_no") or row.get("reference_no"),
        exclude_account_id=row.get("account_id"),
    )
    if contra:
        return contra
    # Last resort: cash/bank account itself
    return _gl_account_display(conn, row.get("account_id"))


def _journal_party_contra(conn, voucher_id) -> str:
    """Debit account(s) → Credit account(s) for journal voucher."""
    if not voucher_id or not _table_exists(conn, "journal_voucher_lines"):
        return ""
    lines = conn.execute(
        """SELECT a.code, a.name, jvl.debit, jvl.credit
           FROM journal_voucher_lines jvl
           JOIN chart_of_accounts a ON jvl.account_id=a.id
           WHERE jvl.voucher_id=?
           ORDER BY jvl.id""",
        (voucher_id,),
    ).fetchall()
    if not lines:
        return ""

    def _fmt(r):
        code = (r["code"] or "").strip()
        name = (r["name"] or "").strip()
        return f"{code} - {name}" if code and name else (name or code)

    debits = [_fmt(r) for r in lines if float(r["debit"] or 0) > 0.005]
    credits = [_fmt(r) for r in lines if float(r["credit"] or 0) > 0.005]
    # Prefer unique labels, keep order
    def _uniq(seq):
        out, seen = [], set()
        for s in seq:
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return out

    debits, credits = _uniq(debits), _uniq(credits)
    left = " + ".join(debits[:3]) + (" …" if len(debits) > 3 else "")
    right = " + ".join(credits[:3]) + (" …" if len(credits) > 3 else "")
    if left and right:
        return f"{left} -> {right}"
    return left or right


def _user_display(conn, user_id) -> str:
    if not user_id:
        return ""
    row = conn.execute(
        "SELECT COALESCE(full_name, username) FROM users WHERE id=?", (user_id,),
    ).fetchone()
    return row[0] if row else ""


def _voucher_row(
    *,
    sort_time: str,
    module: str,
    voucher_type: str,
    voucher_no: str,
    voucher_date: str,
    action: str,
    party: str = "",
    amount=None,
    status: str = "",
    user: str = "",
    particulars: str = "",
    source_table: str = "",
    record_id=None,
) -> dict:
    amt = float(amount) if amount not in (None, "") else None
    return {
        "sort_time": (sort_time or voucher_date or "")[:19],
        "kind": "Transaction",
        "module": module,
        "voucher_type": voucher_type,
        "voucher_no": voucher_no or "",
        "voucher_date": voucher_date or "",
        "action": action or "",
        "party": party or "",
        "amount": amt,
        "status": status or "",
        "user": user or "",
        "particulars": particulars or "",
        "source_table": source_table,
        "record_id": record_id,
    }


def _fetch_vouchers(conn, day: str, sql: str, params: tuple, spec: dict) -> list[dict]:
    """Run a dated voucher query; map columns via spec keys."""
    if not _table_exists(conn, spec["table"]):
        return []
    try:
        raw = rows_to_list(conn.execute(sql, params).fetchall())
    except Exception:
        return []
    out = []
    for r in raw:
        if spec.get("resolve_gl_head"):
            party = _cash_bank_party_label(conn, r)
        elif spec.get("resolve_jv_parties"):
            party = _journal_party_contra(conn, r.get("id"))
        else:
            party = r.get("party") or ""
            if not party and spec.get("party_type_field"):
                party = _party_display(
                    conn, r.get(spec["party_type_field"]), r.get(spec.get("party_id_field", "party_id")),
                )
        st = r.get("sort_time") or r.get("created_at") or r.get("modified_at") or f"{day} 12:00:00"
        vtype = r.get("voucher_type") if spec.get("dynamic_type") else spec["voucher_type"]
        particulars = (r.get("description") or r.get("notes") or r.get("particulars") or "")[:200]
        # Cash/bank receipts for sales: reference_no is source of truth for invoice link
        ref = (r.get("reference_no") or "").strip()
        if (
            spec.get("table") in ("cash_receipts", "bank_receipts")
            and ref.upper().startswith("SAL")
        ):
            particulars = f"Sale {ref}"
        out.append(_voucher_row(
            sort_time=str(st)[:19],
            module=spec["module"],
            voucher_type=vtype or spec["voucher_type"],
            voucher_no=r.get("document_no") or r.get("voucher_no") or "",
            voucher_date=r.get(spec["date_field"]) or day,
            action=spec.get("action_label", "On register"),
            party=party,
            amount=r.get("amount") if r.get("amount") is not None else r.get("total"),
            status=r.get("status") or "",
            user=_user_display(conn, r.get("created_by")),
            particulars=particulars,
            source_table=spec["table"],
            record_id=r.get("id"),
        ))
    return out


# Financial vouchers only (daily checking register — no sign-in / master / logistics noise)
_FINANCIAL_AUDIT_TABLES = frozenset({
    "sales_invoices", "purchase_invoices", "sales_returns", "purchase_returns",
    "cash_receipts", "cash_payments", "bank_receipts", "bank_payments",
    "journal_vouchers", "party_transfers", "expense_bills", "general_ledger",
})
_FINANCIAL_AUDIT_ACTIONS = frozenset({
    "create", "update", "delete", "approve", "unapprove", "reject", "post", "reverse",
})


def get_daily_activity_report(activity_date: str, *, include_workflow_audit: bool = False) -> list[dict]:
    """
    Single-day financial transaction register for voucher checking:
    sales, cash sales, returns, purchases, cash/bank book, journals, party transfers.
    Excludes sign-in, master data, gate pass, weighbridge, production, etc.
    """
    day = (activity_date or "")[:10]
    if not day:
        return []

    rows: list[dict] = []

    with get_connection() as conn:
        si_cols = _table_columns(conn, "sales_invoices")
        pay_mode_sql = ""
        if "payment_mode" in si_cols:
            pay_mode_sql = ", s.payment_mode"
        sales_type_sql = (
            """CASE WHEN LOWER(COALESCE(s.payment_mode, '')) = 'cash' THEN 'Cash Sale'
                    ELSE 'Sales Invoice' END AS voucher_type"""
            if "payment_mode" in si_cols
            else "'Sales Invoice' AS voucher_type"
        )
        specs = [
            {
                "table": "sales_invoices",
                "module": "Sales",
                "voucher_type": "Sales Invoice",
                "date_field": "invoice_date",
                "dynamic_type": True,
                "sql": f"""SELECT s.id, s.document_no, s.invoice_date, s.status, s.total AS amount,
                                 s.notes AS particulars, s.created_at, s.modified_at, s.created_by,
                                 c.name AS party {pay_mode_sql},
                                 {sales_type_sql}
                          FROM sales_invoices s
                          LEFT JOIN customers c ON s.customer_id = c.id
                          WHERE date(s.invoice_date) = date(?)""",
            },
            {
                "table": "purchase_invoices",
                "module": "Purchase",
                "voucher_type": "Purchase Invoice",
                "date_field": "invoice_date",
                "sql": """SELECT p.id, p.document_no, p.invoice_date, p.status, p.total AS amount,
                                 p.notes AS particulars, p.created_at, p.modified_at, p.created_by,
                                 s.name AS party
                          FROM purchase_invoices p
                          LEFT JOIN suppliers s ON p.supplier_id = s.id
                          WHERE date(p.invoice_date) = date(?)""",
            },
            {
                "table": "sales_returns",
                "module": "Sales",
                "voucher_type": "Sales Return",
                "date_field": "return_date",
                "sql": """SELECT r.id, r.document_no, r.return_date, '' AS status, r.total AS amount,
                                 r.notes AS particulars, r.created_at, r.modified_at, r.created_by,
                                 c.name AS party
                          FROM sales_returns r
                          LEFT JOIN customers c ON r.customer_id = c.id
                          WHERE date(r.return_date) = date(?)""",
            },
            {
                "table": "purchase_returns",
                "module": "Purchase",
                "voucher_type": "Purchase Return",
                "date_field": "return_date",
                "sql": """SELECT r.id, r.document_no, r.return_date, '' AS status, r.total AS amount,
                                 r.notes AS particulars, r.created_at, r.modified_at, r.created_by,
                                 s.name AS party
                          FROM purchase_returns r
                          LEFT JOIN suppliers s ON r.supplier_id = s.id
                          WHERE date(r.return_date) = date(?)""",
            },
            {
                "table": "cash_receipts",
                "module": "Finance",
                "voucher_type": "Cash Receipt",
                "date_field": "receipt_date",
                "party_type_field": "party_type",
                "party_id_field": "party_id",
                "resolve_gl_head": True,
                "sql": """SELECT id, document_no, receipt_date, description AS particulars,
                                 reference_no, amount, created_at, modified_at, created_by,
                                 party_type, party_id, account_id, '' AS status
                          FROM cash_receipts WHERE date(receipt_date) = date(?)""",
            },
            {
                "table": "cash_payments",
                "module": "Finance",
                "voucher_type": "Cash Payment",
                "date_field": "payment_date",
                "party_type_field": "party_type",
                "party_id_field": "party_id",
                "resolve_gl_head": True,
                "sql": """SELECT id, document_no, payment_date, description AS particulars,
                                 reference_no, amount, created_at, modified_at, created_by,
                                 party_type, party_id, account_id, '' AS status
                          FROM cash_payments WHERE date(payment_date) = date(?)""",
            },
            {
                "table": "bank_receipts",
                "module": "Finance",
                "voucher_type": "Bank Receipt",
                "date_field": "receipt_date",
                "party_type_field": "party_type",
                "party_id_field": "party_id",
                "resolve_gl_head": True,
                "sql": """SELECT id, document_no, receipt_date, description AS particulars,
                                 reference_no, amount, created_at, modified_at, created_by,
                                 party_type, party_id, account_id, '' AS status
                          FROM bank_receipts WHERE date(receipt_date) = date(?)""",
            },
            {
                "table": "bank_payments",
                "module": "Finance",
                "voucher_type": "Bank Payment",
                "date_field": "payment_date",
                "party_type_field": "party_type",
                "party_id_field": "party_id",
                "resolve_gl_head": True,
                "sql": """SELECT id, document_no, payment_date, description AS particulars,
                                 reference_no, amount, created_at, modified_at, created_by,
                                 party_type, party_id, account_id, '' AS status
                          FROM bank_payments WHERE date(payment_date) = date(?)""",
            },
            {
                "table": "expense_bills",
                "module": "Finance",
                "voucher_type": "Expense Bill",
                "date_field": "bill_date",
                "party_type_field": "party_type",
                "party_id_field": "party_id",
                "sql": """SELECT b.id, b.document_no, b.bill_date, b.status,
                                 b.total_amount AS amount, b.created_at, b.posted_at AS modified_at,
                                 b.created_by, b.party_type, b.party_id, b.settlement,
                                 CASE
                                   WHEN TRIM(COALESCE(b.reference_no,'')) != ''
                                        AND TRIM(COALESCE(b.description,'')) != ''
                                     THEN b.reference_no || ' — ' || b.description
                                   WHEN TRIM(COALESCE(b.reference_no,'')) != ''
                                     THEN b.reference_no
                                   ELSE COALESCE(b.description, '')
                                 END AS particulars
                          FROM expense_bills b
                          WHERE date(b.bill_date) = date(?)""",
            },
            {
                "table": "journal_vouchers",
                "module": "Finance",
                "voucher_type": "Journal Voucher",
                "date_field": "voucher_date",
                "resolve_jv_parties": True,
                "sql": """SELECT id, document_no, voucher_date, description AS particulars,
                                 total_debit AS amount, status, created_at, modified_at, created_by
                          FROM journal_vouchers WHERE date(voucher_date) = date(?)""",
            },
            {
                "table": "party_transfers",
                "module": "Finance",
                "voucher_type": "Party Transfer",
                "date_field": "transfer_date",
                "sql": """SELECT id, document_no, transfer_date, description AS particulars,
                                 amount, transfer_type AS status, created_at, created_by,
                                 from_party_type, from_party_id, to_party_type, to_party_id
                          FROM party_transfers WHERE date(transfer_date) = date(?)""",
            },
        ]

        for spec in specs:
            if spec["table"] == "party_transfers":
                if not _table_exists(conn, "party_transfers"):
                    continue
                raw = rows_to_list(conn.execute(spec["sql"], (day,)).fetchall())
                for r in raw:
                    fp = _party_display(conn, r.get("from_party_type"), r.get("from_party_id"))
                    tp = _party_display(conn, r.get("to_party_type"), r.get("to_party_id"))
                    party = f"{fp} -> {tp}".strip(" ->")
                    rows.append(_voucher_row(
                        sort_time=str(r.get("created_at") or f"{day} 12:00:00")[:19],
                        module="Finance",
                        voucher_type="Party Transfer",
                        voucher_no=r.get("document_no") or "",
                        voucher_date=r.get("transfer_date") or day,
                        action="On register",
                        party=party,
                        amount=r.get("amount"),
                        status=r.get("status") or "",
                        user=_user_display(conn, r.get("created_by")),
                        particulars=(r.get("particulars") or "")[:200],
                        source_table="party_transfers",
                        record_id=r.get("id"),
                    ))
                continue
            rows.extend(_fetch_vouchers(conn, day, spec["sql"], (day,), spec))

    if include_workflow_audit:
        from db_audit import search_audit_log, ACTION_LABELS, TABLE_LABELS

        for a in search_audit_log(day, day, limit=2000):
            if a.get("table_name") not in _FINANCIAL_AUDIT_TABLES:
                continue
            if a.get("action") not in _FINANCIAL_AUDIT_ACTIONS:
                continue
            rows.append({
                "sort_time": (a.get("created_at") or "")[:19],
                "kind": "Workflow",
                "module": a.get("module") or _module_from_table(a.get("table_name")),
                "voucher_type": a.get("entity") or TABLE_LABELS.get(a.get("table_name"), ""),
                "voucher_no": a.get("document_no") or "",
                "voucher_date": day,
                "action": a.get("action_label") or ACTION_LABELS.get(a.get("action"), ""),
                "party": "",
                "amount": None,
                "status": a.get("action") or "",
                "user": a.get("user_name") or a.get("username") or "",
                "particulars": (a.get("summary") or "")[:200],
                "source_table": a.get("table_name") or "",
                "record_id": a.get("record_id"),
            })

    # Heading-wise order: module → voucher type → time → voucher no
    _module_rank = {"Sales": 0, "Purchase": 1, "Finance": 2}
    _type_rank = {
        "Sales Invoice": 0, "Cash Sale": 1, "Sales Return": 2,
        "Purchase Invoice": 10, "Purchase Return": 11,
        "Cash Receipt": 20, "Cash Payment": 21, "Bank Receipt": 22, "Bank Payment": 23,
        "Expense Bill": 25,
        "Journal Voucher": 30, "Party Transfer": 31,
    }
    rows.sort(key=lambda r: (
        _module_rank.get(r.get("module") or "", 50),
        _type_rank.get(r.get("voucher_type") or "", 90),
        r.get("voucher_type") or "",
        r.get("sort_time") or "",
        r.get("voucher_no") or "",
    ))
    for i, r in enumerate(rows, start=1):
        r["line_no"] = i
        r["time"] = r.get("sort_time", "")
        for drop in ("sort_time", "kind", "source_table", "record_id"):
            r.pop(drop, None)
    return rows


def _module_from_table(table_name: str | None) -> str:
    m = {
        "sales_invoices": "Sales",
        "purchase_invoices": "Purchase",
        "sales_returns": "Sales",
        "purchase_returns": "Purchase",
        "cash_receipts": "Finance",
        "cash_payments": "Finance",
        "bank_receipts": "Finance",
        "bank_payments": "Finance",
        "journal_vouchers": "Finance",
        "expense_bills": "Finance",
        "gate_passes": "Gate Pass",
        "weight_slips": "Weighbridge",
        "production_orders": "Production",
        "party_transfers": "Finance",
        "customers": "Masters",
        "suppliers": "Masters",
        "products": "Masters",
        "users": "Admin",
        "fiscal_years": "Finance",
    }
    return m.get(table_name or "", "System")


def get_customer_due_aging(
    as_of=None,
    *,
    customer_id=None,
    customer_group_id=None,
    include_drafts: bool = False,
) -> list[dict]:
    """Customer balance due aging: 0-15, 16-30, 31-45, 46-60, 61-90, Over 90 days.

    Ages each party's **net receivable** (same dual-role netting as Customer Outstanding:
    customer + linked supplier, +Dr/−Cr). Receipts are assumed to clear oldest sales
    invoices first. Unallocated remainder (opening / no invoices) goes to Over 90.
    Total Due matches Customer Outstanding for that party.
    """
    from datetime import date, datetime

    as_of = str(as_of or date.today())[:10]
    try:
        as_of_d = datetime.strptime(as_of, "%Y-%m-%d").date()
    except ValueError:
        as_of_d = date.today()
        as_of = as_of_d.isoformat()

    statuses = ("approved", "posted")
    if include_drafts:
        statuses = ("approved", "posted", "draft", "pending_approval")
    placeholders = ",".join("?" * len(statuses))

    with get_connection() as conn:
        cust_clause = ""
        cust_params: list = []
        if customer_id:
            cust_clause += " AND c.id=?"
            cust_params.append(int(customer_id))
        if customer_group_id:
            cust_clause += " AND c.group_id=?"
            cust_params.append(int(customer_group_id))

        bal_rows = rows_to_list(conn.execute(
            f"""
            SELECT c.id AS customer_id, c.code, c.name, c.phone,
                   COALESCE(c.current_balance, 0) AS customer_balance,
                   mg.code AS group_code, mg.name AS group_name
            FROM customers c
            LEFT JOIN master_groups mg ON c.group_id = mg.id AND mg.entity_type='customer'
            WHERE c.is_active=1
              {cust_clause}
            """,
            cust_params,
        ).fetchall())

        # Linked supplier balances by party code (dual-role netting)
        sup_by_code = {
            (r.get("code") or "").strip().upper(): float(r.get("current_balance") or 0)
            for r in rows_to_list(conn.execute(
                """SELECT code, current_balance FROM suppliers WHERE is_active=1"""
            ).fetchall())
            if (r.get("code") or "").strip()
        }

        inv_params: list = [*statuses, as_of]
        inv_clause = ""
        if customer_id:
            inv_clause += " AND c.id=?"
            inv_params.append(int(customer_id))
        if customer_group_id:
            inv_clause += " AND c.group_id=?"
            inv_params.append(int(customer_group_id))

        inv_rows = rows_to_list(conn.execute(
            f"""
            SELECT c.id AS customer_id,
                   s.invoice_date,
                   COALESCE(s.total, 0) - COALESCE(s.paid_amount, 0) AS due_amt
            FROM sales_invoices s
            JOIN customers c ON c.id = s.customer_id
            WHERE c.is_active=1
              AND LOWER(COALESCE(s.status, '')) IN ({placeholders})
              AND COALESCE(s.invoice_date, '') <= ?
              AND (COALESCE(s.total, 0) - COALESCE(s.paid_amount, 0)) > 0.009
              {inv_clause}
            ORDER BY c.id, s.invoice_date, s.id
            """,
            inv_params,
        ).fetchall())

    buckets = {
        "days_0_15": (0, 15),
        "days_16_30": (16, 30),
        "days_31_45": (31, 45),
        "days_46_60": (46, 60),
        "days_61_90": (61, 90),
    }

    def empty_row(base: dict, *, net_balance: float, dual_role: bool) -> dict:
        return {
            "customer_id": base.get("customer_id"),
            "code": base.get("code") or "",
            "name": base.get("name") or "",
            "phone": base.get("phone") or "",
            "group_code": base.get("group_code") or "",
            "group_name": base.get("group_name") or "",
            "customer_balance": round(float(base.get("customer_balance") or 0), 2),
            "current_balance": round(net_balance, 2),
            "dual_role": dual_role,
            "days_0_15": 0.0,
            "days_16_30": 0.0,
            "days_31_45": 0.0,
            "days_46_60": 0.0,
            "days_61_90": 0.0,
            "over_90": 0.0,
            "total_due": 0.0,
            "as_of": as_of,
        }

    def bucket_for_age(age: int) -> str:
        for key, (lo, hi) in buckets.items():
            if lo <= age <= hi:
                return key
        return "over_90"

    by_cust: dict[int, dict] = {}
    for r in bal_rows:
        cid = int(r["customer_id"])
        code_key = (r.get("code") or "").strip().upper()
        cbal = float(r.get("customer_balance") or 0)
        sbal = float(sup_by_code.get(code_key) or 0) if code_key else 0.0
        dual = bool(code_key and code_key in sup_by_code)
        net = round(cbal + sbal, 2) if dual else round(cbal, 2)
        if net <= 0.009:
            continue
        by_cust[cid] = empty_row(r, net_balance=net, dual_role=dual)

    invs_by_cust: dict[int, list] = {}
    for r in inv_rows:
        cid = int(r["customer_id"])
        if cid not in by_cust:
            continue
        invs_by_cust.setdefault(cid, []).append({
            "invoice_date": r.get("invoice_date"),
            "due_amt": round(float(r.get("due_amt") or 0), 2),
        })

    out = []
    for cid, row in by_cust.items():
        balance = float(row["current_balance"] or 0)
        if balance <= 0.009:
            continue
        invs = invs_by_cust.get(cid, [])  # already oldest → newest
        inv_sum = round(sum(i["due_amt"] for i in invs), 2)
        # Assume receipts / set-offs clear oldest invoices first; age remaining net due
        to_clear = max(0.0, round(inv_sum - balance, 2))
        for inv in invs:
            if to_clear <= 0.009:
                break
            clear = min(inv["due_amt"], to_clear)
            inv["due_amt"] = round(inv["due_amt"] - clear, 2)
            to_clear = round(to_clear - clear, 2)
        for inv in invs:
            due = inv["due_amt"]
            if due <= 0.009:
                continue
            inv_d = str(inv.get("invoice_date") or "")[:10]
            try:
                d0 = datetime.strptime(inv_d, "%Y-%m-%d").date()
                age = (as_of_d - d0).days
            except ValueError:
                age = 999
            if age < 0:
                age = 0
            key = bucket_for_age(age)
            row[key] = round(row[key] + due, 2)
        aged = (
            row["days_0_15"] + row["days_16_30"] + row["days_31_45"]
            + row["days_46_60"] + row["days_61_90"] + row["over_90"]
        )
        if balance > aged + 0.009:
            row["over_90"] = round(row["over_90"] + (balance - aged), 2)
        row["total_due"] = round(
            row["days_0_15"] + row["days_16_30"] + row["days_31_45"]
            + row["days_46_60"] + row["days_61_90"] + row["over_90"],
            2,
        )
        if row["total_due"] > 0.009:
            out.append(row)

    out.sort(key=lambda r: (-float(r["total_due"]), r.get("code") or ""))
    return out
