"""Controlled sale/purchase invoice workflow — draft → approval → ledger/stock/GL."""

from datetime import datetime

INVOICE_STATUSES = ("draft", "pending_approval", "approved", "rejected", "cancelled")
EDITABLE_STATUSES = ("draft", "rejected")
WEIGHT_SLIP_FIRST = "first_weigh"
WEIGHT_SLIP_COMPLETE = "completed"
WEIGHT_SLIP_CANCELLED = "cancelled"

# Placeholder party when vehicle is weighed before customer/supplier is known
UNKNOWN_PARTY_CODE = "UNKNOWN"
UNKNOWN_PARTY_NAME = "UNKNOWN PARTY"


def _ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ensure_unknown_parties(user_id=None):
    """Ensure UNKNOWN customer + supplier exist for first-weight placeholder."""
    import database as db

    with db.get_connection() as conn:
        cust = conn.execute(
            "SELECT id FROM customers WHERE UPPER(TRIM(code))=?", (UNKNOWN_PARTY_CODE,),
        ).fetchone()
        if cust:
            cust_id = int(cust["id"])
        else:
            cust_id = db.add_customer(
                {
                    "code": UNKNOWN_PARTY_CODE,
                    "name": UNKNOWN_PARTY_NAME,
                    "city": "",
                    "opening_balance": 0,
                },
                created_by=user_id,
            )
        sup = conn.execute(
            "SELECT id FROM suppliers WHERE UPPER(TRIM(code))=?", (UNKNOWN_PARTY_CODE,),
        ).fetchone()
        if sup:
            sup_id = int(sup["id"])
        else:
            sup_id = db.add_supplier(
                {
                    "code": UNKNOWN_PARTY_CODE,
                    "name": UNKNOWN_PARTY_NAME,
                    "city": "",
                    "opening_balance": 0,
                },
                created_by=user_id,
            )
    return {"customer_id": cust_id, "supplier_id": sup_id}


def unknown_party_id(party_type="customer", user_id=None) -> int:
    ids = ensure_unknown_parties(user_id)
    return ids["customer_id"] if party_type == "customer" else ids["supplier_id"]


def is_unknown_party(party_id, party_type="customer") -> bool:
    if not party_id:
        return True
    import database as db

    table = "customers" if party_type == "customer" else "suppliers"
    with db.get_connection() as conn:
        row = conn.execute(
            f"SELECT code FROM {table} WHERE id=?", (party_id,),
        ).fetchone()
    return bool(row and str(row["code"] or "").strip().upper() == UNKNOWN_PARTY_CODE)


def slip_party_is_unknown(slip) -> bool:
    """True when slip has no party or is linked to UNKNOWN placeholder."""
    if not slip:
        return True
    if slip.get("customer_id"):
        return is_unknown_party(slip["customer_id"], "customer")
    if slip.get("supplier_id"):
        return is_unknown_party(slip["supplier_id"], "supplier")
    return True


def validate_sale_cash_payment(payment_mode, paid_amount, invoice_total):
    """Cash sales must be fully paid (paid = invoice total) before save."""
    mode = (payment_mode or "credit").lower()
    total = round(float(invoice_total or 0), 2)
    paid = round(float(paid_amount or 0), 2)
    if mode != "cash":
        return paid
    if total <= 0:
        raise ValueError("Cash sale requires invoice total greater than zero.")
    if abs(paid - total) > 0.009:
        raise ValueError(
            f"Cash sale: cash paid (Rs. {paid:,.2f}) must equal invoice total (Rs. {total:,.2f}). "
            "Set Payment Mode to Cash and enter the full cash received."
        )
    return total


def get_variance_settings(conn):
    def _g(key, default):
        r = conn.execute("SELECT value FROM system_settings WHERE key=?", (key,)).fetchone()
        return float(r[0]) if r and r[0] not in (None, "") else default

    return {
        "minor_pct": _g("weight_variance_minor_pct", 1.0),
        "limit_pct": _g("weight_variance_limit_pct", 5.0),
    }


def compute_weight_match(physical_kg, invoice_kg, minor_pct=None, limit_pct=None):
    physical = float(physical_kg or 0)
    invoice = float(invoice_kg or 0)
    variance = round(physical - invoice, 3)
    base = invoice if invoice > 0 else (physical if physical > 0 else 1)
    variance_pct = round(abs(variance) / base * 100, 2)
    minor = minor_pct if minor_pct is not None else 1.0
    limit = limit_pct if limit_pct is not None else 5.0
    if invoice <= 0 and physical <= 0:
        status = "matched"
    elif variance_pct <= minor:
        status = "matched"
    elif variance_pct <= limit:
        status = "minor_variance"
    else:
        status = "excess_variance"
    return {
        "physical_weight_kg": physical,
        "invoice_weight_kg": invoice,
        "weight_variance_kg": variance,
        "weight_variance_pct": variance_pct,
        "weight_match_status": status,
    }


def _validate_weight_slip_unique(conn, slip_id, invoice_id, table):
    """Legacy no-op: one slip may link to many invoices (one primary + reference-only)."""
    return


def _is_primary_weight_slip_for_invoice(conn, slip_id, invoice_id, kind="sales") -> bool:
    """True when this invoice owns the slip's weight/variance (slip.reference_*)."""
    if not slip_id or not invoice_id:
        return False
    ref_type = "sales_invoice" if kind == "sales" else "purchase_invoice"
    table = "sales_invoices" if kind == "sales" else "purchase_invoices"
    slip = conn.execute(
        "SELECT reference_type, reference_id FROM weight_slips WHERE id=?",
        (slip_id,),
    ).fetchone()
    if not slip:
        return False
    if slip["reference_type"] in ("sales_invoice", "purchase_invoice") and slip["reference_id"] is not None:
        return (
            slip["reference_type"] == ref_type
            and int(slip["reference_id"]) == int(invoice_id)
        )
    # No primary claimed yet — earliest invoice with this slip owns weight
    row = conn.execute(
        f"SELECT id FROM {table} WHERE weight_slip_id=? ORDER BY id LIMIT 1",
        (slip_id,),
    ).fetchone()
    if row:
        return int(row["id"]) == int(invoice_id)
    return True


def refresh_invoice_weight_match(conn, invoice_id, kind="sales"):
    from db_commercial import invoice_lines_net_weight
    table = "sales_invoices" if kind == "sales" else "purchase_invoices"
    inv = conn.execute(f"SELECT weight_slip_id, total_net_weight FROM {table} WHERE id=?", (invoice_id,)).fetchone()
    if not inv:
        return
    inv_wt = float(inv["total_net_weight"] or invoice_lines_net_weight(conn, invoice_id, kind))
    slip_id = inv["weight_slip_id"]
    # Reference-only link: show slip number on invoice, no variance vs full slip net
    if slip_id and not _is_primary_weight_slip_for_invoice(conn, slip_id, invoice_id, kind):
        match = {
            "physical_weight_kg": 0.0,
            "invoice_weight_kg": inv_wt,
            "weight_variance_kg": 0.0,
            "weight_variance_pct": 0.0,
            "weight_match_status": "reference",
        }
        conn.execute(
            f"""UPDATE {table} SET total_net_weight=?, physical_weight_kg=?, weight_variance_kg=?,
                weight_variance_pct=?, weight_match_status=? WHERE id=?""",
            (inv_wt, 0.0, 0.0, 0.0, "reference", invoice_id),
        )
        return match

    physical = 0.0
    if slip_id:
        ws = conn.execute("SELECT net_weight, status FROM weight_slips WHERE id=?", (slip_id,)).fetchone()
        if ws and float(ws["net_weight"] or 0) > 0:
            physical = float(ws["net_weight"] or 0)
    settings = get_variance_settings(conn)
    match = compute_weight_match(physical, inv_wt, settings["minor_pct"], settings["limit_pct"])
    conn.execute(
        f"""UPDATE {table} SET total_net_weight=?, physical_weight_kg=?, weight_variance_kg=?,
            weight_variance_pct=?, weight_match_status=? WHERE id=?""",
        (inv_wt, match["physical_weight_kg"], match["weight_variance_kg"],
         match["weight_variance_pct"], match["weight_match_status"], invoice_id),
    )
    if slip_id:
        conn.execute(
            "UPDATE weight_slips SET weight_difference=? WHERE id=?",
            (match["weight_variance_kg"], slip_id),
        )
    return match


def save_weight_slip_first(data, user_id=None):
    from database import get_connection
    from db_commercial import save_weight_slip_pro
    data = dict(data)
    vehicle = (data.get("vehicle_no") or "").strip()
    if not vehicle:
        raise ValueError("Vehicle number is required.")
    with get_connection() as conn:
        _validate_vehicle_no_pending(conn, vehicle)
    data["second_weight"] = 0
    data["status"] = WEIGHT_SLIP_FIRST
    return save_weight_slip_pro(data, None, user_id)


def _validate_vehicle_no_pending(conn, vehicle_no, exclude_slip_id=None):
    v = (vehicle_no or "").strip().upper()
    if not v:
        return
    row = conn.execute(
        """SELECT id, document_no FROM weight_slips
           WHERE UPPER(TRIM(COALESCE(vehicle_no,'')))=? AND status=? AND id!=?""",
        (v, WEIGHT_SLIP_FIRST, exclude_slip_id or 0),
    ).fetchone()
    if row:
        raise ValueError(
            f"Vehicle {vehicle_no} already has pending slip {row[1]}. Complete second weight first."
        )


def _infer_reopen_status(slip_row):
    """Restore cancelled slip to pending (1st only) or completed (had 2nd weight)."""
    slip = dict(slip_row) if slip_row else {}
    if float(slip.get("second_weight") or 0) > 0 or float(slip.get("net_weight") or 0) > 0:
        return WEIGHT_SLIP_COMPLETE
    return WEIGHT_SLIP_FIRST


def reopen_weight_slip(slip_id, user_id=None):
    from database import get_connection
    with get_connection() as conn:
        slip = conn.execute("SELECT * FROM weight_slips WHERE id=?", (slip_id,)).fetchone()
        if not slip:
            raise ValueError("Weight slip not found.")
        if slip["status"] != WEIGHT_SLIP_CANCELLED:
            return slip["status"]
        if _slip_is_linked(conn, slip_id):
            raise ValueError("Cannot reopen slip linked to an invoice.")
        new_status = _infer_reopen_status(slip)
        conn.execute(
            "UPDATE weight_slips SET status=?, modified_by=?, modified_at=? WHERE id=?",
            (new_status, user_id, _ts(), slip_id),
        )
        return new_status


def complete_weight_slip(slip_id, second_weight, second_time, user_id=None, *, party_update=None):
    """Complete 2nd weight. Optional party_update={customer_id|supplier_id, party_type}."""
    from database import get_connection
    from db_commercial import save_weight_slip_pro
    with get_connection() as conn:
        slip = conn.execute("SELECT * FROM weight_slips WHERE id=?", (slip_id,)).fetchone()
        if not slip:
            raise ValueError("Weight slip not found.")
        if slip["status"] == WEIGHT_SLIP_CANCELLED:
            if _infer_reopen_status(slip) == WEIGHT_SLIP_COMPLETE:
                raise ValueError(
                    "This slip was cancelled after completion. Open **Edit / Delete**, edit it, and save to reopen."
                )
            slip = dict(slip)
            slip["status"] = WEIGHT_SLIP_FIRST
        elif slip["status"] == WEIGHT_SLIP_COMPLETE:
            raise ValueError("Weight slip already completed.")
        first_w = float(slip["first_weight"] or 0)
        second_w = float(second_weight or 0)
        gross, tare = max(first_w, second_w), min(first_w, second_w)
        net = round(gross - tare, 3)
        pts = _ts()
        data = dict(slip)
        if party_update:
            pt = (party_update.get("party_type") or data.get("party_type") or "customer").lower()
            if pt == "customer":
                cid = party_update.get("customer_id")
                if not cid:
                    raise ValueError("Select the customer for this dispatch.")
                data["customer_id"] = cid
                data["supplier_id"] = None
                data["party_type"] = "customer"
            else:
                sid = party_update.get("supplier_id")
                if not sid:
                    raise ValueError("Select the supplier for this receipt.")
                data["supplier_id"] = sid
                data["customer_id"] = None
                data["party_type"] = "supplier"
        data.update({
            "second_weight": second_w,
            "second_weight_time": second_time or pts,
            "gross_weight": gross,
            "tare_weight": tare,
            "net_weight": net,
            "status": WEIGHT_SLIP_COMPLETE,
            "print_time": pts,
        })
        save_weight_slip_pro(data, slip_id, user_id)
        return slip_id


def get_all_pending_weight_slips():
    """Slips with first weight done, second weight pending."""
    from database import get_connection, rows_to_list
    from db_commercial import _WS_SALES_INV_JOIN, _WS_PURCHASE_INV_JOIN
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            f"""SELECT ws.*, c.name AS customer_name, c.code AS customer_code,
                       s.name AS supplier_name, s.code AS supplier_code, p.name AS product_name,
                       si.document_no AS sales_invoice_no, pi.document_no AS purchase_invoice_no
               FROM weight_slips ws
               LEFT JOIN customers c ON ws.customer_id=c.id
               LEFT JOIN suppliers s ON ws.supplier_id=s.id
               LEFT JOIN products p ON ws.product_id=p.id
               {_WS_SALES_INV_JOIN}
               {_WS_PURCHASE_INV_JOIN}
               WHERE ws.status=?
               ORDER BY ws.slip_date DESC, ws.first_weight_time DESC, ws.id DESC""",
            (WEIGHT_SLIP_FIRST,),
        ).fetchall())


def get_completed_unlinked_slips():
    """Completed IFS weighbridge slips not yet linked to any invoice (imports excluded)."""
    from database import get_connection, rows_to_list
    from db_commercial import _WS_SALES_INV_JOIN, _WS_PURCHASE_INV_JOIN, _WS_EXCLUDE_IMPORTED_SQL
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            f"""SELECT ws.*, c.name AS customer_name, c.code AS customer_code,
                       s.name AS supplier_name, s.code AS supplier_code, p.name AS product_name,
                       si.document_no AS sales_invoice_no, pi.document_no AS purchase_invoice_no
               FROM weight_slips ws
               LEFT JOIN customers c ON ws.customer_id=c.id
               LEFT JOIN suppliers s ON ws.supplier_id=s.id
               LEFT JOIN products p ON ws.product_id=p.id
               {_WS_SALES_INV_JOIN}
               {_WS_PURCHASE_INV_JOIN}
               WHERE ws.status=?
                 AND si.id IS NULL AND pi.id IS NULL
                 AND (ws.reference_type IS NULL OR ws.reference_id IS NULL)
                 {_WS_EXCLUDE_IMPORTED_SQL}
               ORDER BY ws.slip_date DESC, ws.id DESC""",
            (WEIGHT_SLIP_COMPLETE,),
        ).fetchall())


def get_pending_weight_slips(party_type="customer"):
    from database import get_connection, rows_to_list
    col = "customer_id" if party_type == "customer" else "supplier_id"
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            f"""SELECT ws.*, c.name AS customer_name, c.code AS customer_code,
                       s.name AS supplier_name, s.code AS supplier_code, p.name AS product_name
                FROM weight_slips ws
                LEFT JOIN customers c ON ws.customer_id=c.id
                LEFT JOIN suppliers s ON ws.supplier_id=s.id
                LEFT JOIN products p ON ws.product_id=p.id
                WHERE ws.status=? AND ws.{col} IS NOT NULL
                ORDER BY ws.slip_date DESC, ws.id DESC""",
            (WEIGHT_SLIP_FIRST,),
        ).fetchall())


def _slip_is_linked(conn, slip_id):
    si = conn.execute("SELECT id FROM sales_invoices WHERE weight_slip_id=?", (slip_id,)).fetchone()
    pi = conn.execute("SELECT id FROM purchase_invoices WHERE weight_slip_id=?", (slip_id,)).fetchone()
    return bool(si or pi)


def cancel_weight_slip(slip_id, user_id, reason=""):
    from database import get_connection
    with get_connection() as conn:
        slip = conn.execute("SELECT * FROM weight_slips WHERE id=?", (slip_id,)).fetchone()
        if not slip:
            raise ValueError("Weight slip not found.")
        if slip["status"] == WEIGHT_SLIP_CANCELLED:
            return slip_id
        if _slip_is_linked(conn, slip_id):
            from db_commercial import get_weight_slip_invoice_attachment
            att = get_weight_slip_invoice_attachment(slip_id)
            inv = att.get("invoice_no") if att else "an invoice"
            raise ValueError(
                f"Cannot cancel: slip is on invoice **{inv}**. "
                "Detach it on **Weight Scale → Edit / Delete** first."
            )
        note = f" | CANCELLED: {reason}" if reason else " | CANCELLED"
        conn.execute(
            """UPDATE weight_slips SET status=?, remarks=COALESCE(remarks,'') || ?,
               modified_by=?, modified_at=? WHERE id=?""",
            (WEIGHT_SLIP_CANCELLED, note, user_id, _ts(), slip_id),
        )
    return slip_id


def delete_weight_slip(slip_id, user_id):
    from database import get_connection
    with get_connection() as conn:
        if not _is_admin(conn, user_id):
            raise ValueError("Only administrators can delete weight slips.")
        slip = conn.execute("SELECT * FROM weight_slips WHERE id=?", (slip_id,)).fetchone()
        if not slip:
            raise ValueError("Weight slip not found.")
        if _slip_is_linked(conn, slip_id):
            from db_commercial import get_weight_slip_invoice_attachment
            att = get_weight_slip_invoice_attachment(slip_id)
            inv = att.get("invoice_no") if att else "an invoice"
            raise ValueError(
                f"Cannot delete: slip is on invoice **{inv}**. Detach from invoice first."
            )
        gp = conn.execute("SELECT id FROM gate_passes WHERE weight_slip_id=?", (slip_id,)).fetchone()
        if gp:
            raise ValueError("Cannot delete slip linked to a gate pass.")
        conn.execute("DELETE FROM weight_slips WHERE id=?", (slip_id,))


def update_pending_weight_slip(slip_id, data, user_id):
    return update_weight_slip(slip_id, data, user_id, pending_only=True)


def update_weight_slip(slip_id, data, user_id, pending_only=False):
    """Edit unlinked slip (pending, completed, or cancelled — cancelled slips reopen on save)."""
    from db_commercial import save_weight_slip_pro
    from database import get_connection
    with get_connection() as conn:
        slip = conn.execute("SELECT * FROM weight_slips WHERE id=?", (slip_id,)).fetchone()
        if not slip:
            raise ValueError("Weight slip not found.")
        if _slip_is_linked(conn, slip_id):
            from db_commercial import get_weight_slip_invoice_attachment
            att = get_weight_slip_invoice_attachment(slip_id)
            inv = att.get("invoice_no") if att else "an invoice"
            raise ValueError(
                f"Slip is linked to invoice **{inv}**. Use **Detach from invoice** on Weight Scale first."
            )
        if slip["status"] == WEIGHT_SLIP_CANCELLED:
            reopen_weight_slip(slip_id, user_id)
            slip = conn.execute("SELECT * FROM weight_slips WHERE id=?", (slip_id,)).fetchone()
        status = slip["status"]
        if pending_only and status != WEIGHT_SLIP_FIRST:
            raise ValueError("Only pending (first weight) slips can be edited.")
        vehicle = (data.get("vehicle_no") or slip["vehicle_no"] or "").strip()
        if vehicle and status == WEIGHT_SLIP_FIRST:
            _validate_vehicle_no_pending(conn, vehicle, exclude_slip_id=slip_id)
        payload = dict(slip)
        payload.update(data)
        if status == WEIGHT_SLIP_FIRST:
            payload["status"] = WEIGHT_SLIP_FIRST
            payload["second_weight"] = 0
            payload["net_weight"] = 0
            payload["gross_weight"] = float(payload.get("first_weight") or 0)
            payload["tare_weight"] = 0
        elif status == WEIGHT_SLIP_COMPLETE:
            first_w = float(payload.get("first_weight") if payload.get("first_weight") is not None else slip["first_weight"] or 0)
            second_w = float(payload.get("second_weight") if payload.get("second_weight") is not None else slip["second_weight"] or 0)
            gross, tare = max(first_w, second_w), min(first_w, second_w)
            payload.update({
                "first_weight": first_w,
                "second_weight": second_w,
                "gross_weight": gross,
                "tare_weight": tare,
                "net_weight": round(gross - tare, 3),
                "status": WEIGHT_SLIP_COMPLETE,
            })
        else:
            raise ValueError(f"Cannot edit slip with status '{status}'.")
        save_weight_slip_pro(payload, slip_id, user_id)


def _is_admin(conn, user_id):
    row = conn.execute("SELECT role FROM users WHERE id=?", (user_id,)).fetchone()
    return row and row[0] == "admin"


def _invoice_lines_for_validation(conn, invoice_id, kind: str) -> list[dict]:
    if kind == "sales":
        rows = conn.execute(
            """SELECT product_id AS item_id, quantity, rate, amount
               FROM sales_invoice_items WHERE invoice_id=?""",
            (invoice_id,),
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT product_id AS item_id, quantity, rate, amount
               FROM purchase_invoice_items WHERE invoice_id=?""",
            (invoice_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def _invoice_totals_from_row(inv: dict) -> dict:
    return {
        "subtotal": float(inv.get("subtotal") or 0),
        "discount_amt": float(inv.get("discount") or 0),
        "discount_pct": float(inv.get("discount_pct") or 0),
        "taxable": float(inv.get("taxable_amount") or 0),
        "sales_tax": float(inv.get("sales_tax") or 0),
        "further_tax": float(inv.get("further_tax") or 0),
        "extra_tax": float(inv.get("extra_tax") or 0),
        "fed_tax": float(inv.get("fed_tax") or 0),
        "wht_tax": float(inv.get("wht_tax") or 0),
        "total_tax": float(inv.get("tax") or 0),
        "total": float(inv.get("total") or 0),
    }


def _validate_invoice_for_workflow(conn, invoice_id, kind: str, *, stage: str = "approve") -> None:
    from erp_core.transaction_validation import validate_purchase_invoice, validate_sale_invoice

    if kind == "sales":
        inv = conn.execute("SELECT * FROM sales_invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv:
            raise ValueError("Invoice not found.")
        inv = dict(inv)
        lines = _invoice_lines_for_validation(conn, invoice_id, "sales")
        totals = _invoice_totals_from_row(inv)
        vr = validate_sale_invoice(inv, lines, totals, stage=stage)
        vr.raise_if_invalid("Sales invoice")
    else:
        inv = conn.execute("SELECT * FROM purchase_invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv:
            raise ValueError("Invoice not found.")
        inv = dict(inv)
        lines = _invoice_lines_for_validation(conn, invoice_id, "purchase")
        totals = _invoice_totals_from_row(inv)
        vr = validate_purchase_invoice(inv, lines, totals, stage=stage)
        vr.raise_if_invalid("Purchase invoice")


def submit_sale_invoice(invoice_id, user_id):
    from database import get_connection
    with get_connection() as conn:
        inv = conn.execute("SELECT * FROM sales_invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv:
            raise ValueError("Invoice not found.")
        inv = dict(inv)
        if inv["status"] not in EDITABLE_STATUSES:
            raise ValueError(f"Cannot submit invoice in status '{inv['status']}'.")
        if _sale_will_post_cash_book(conn, inv):
            from db_cash_day import assert_cash_day_open_for_invoice
            assert_cash_day_open_for_invoice(inv["invoice_date"], kind="cash sale invoice")
        _validate_invoice_for_workflow(conn, invoice_id, "sales", stage="approve")
        weighbridge = inv.get("weighbridge_required")
        if weighbridge is None:
            weighbridge = 1 if inv.get("weight_slip_id") else 0
        if weighbridge:
            if not inv["weight_slip_id"]:
                raise ValueError("Link a completed weight slip before submitting for approval.")
            ws = conn.execute(
                "SELECT status, net_weight FROM weight_slips WHERE id=?", (inv["weight_slip_id"],)
            ).fetchone()
            if not ws or ws["status"] != WEIGHT_SLIP_COMPLETE:
                raise ValueError("Weight slip must be completed (second weight recorded).")
            if not inv["gate_pass_id"]:
                raise ValueError("Gate pass missing. Save the invoice again to auto-generate gate pass.")
            refresh_invoice_weight_match(conn, invoice_id, "sales")
        conn.execute(
            """UPDATE sales_invoices SET status='pending_approval', submitted_by=?, submitted_at=?,
               modified_by=?, modified_at=? WHERE id=?""",
            (user_id, _ts(), user_id, _ts(), invoice_id),
        )


def submit_purchase_invoice(invoice_id, user_id):
    from database import get_connection
    with get_connection() as conn:
        inv = conn.execute("SELECT * FROM purchase_invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv:
            raise ValueError("Invoice not found.")
        inv = dict(inv)
        if inv["status"] not in EDITABLE_STATUSES:
            raise ValueError(f"Cannot submit invoice in status '{inv['status']}'.")
        if _purchase_will_post_cash_book(inv):
            from db_cash_day import assert_cash_day_open_for_invoice
            assert_cash_day_open_for_invoice(inv["invoice_date"], kind="cash purchase invoice")
        _validate_invoice_for_workflow(conn, invoice_id, "purchase", stage="approve")
        weighbridge = inv.get("weighbridge_required")
        if weighbridge is None:
            weighbridge = 1 if inv.get("weight_slip_id") else 0
        if weighbridge:
            if not inv["weight_slip_id"]:
                raise ValueError("Link a completed weight slip before submitting for approval.")
            ws = conn.execute(
                "SELECT status FROM weight_slips WHERE id=?", (inv["weight_slip_id"],)
            ).fetchone()
            if not ws or ws["status"] != WEIGHT_SLIP_COMPLETE:
                raise ValueError("Weight slip must be completed (second weight recorded).")
            if not inv["gate_pass_id"]:
                raise ValueError("Inward gate pass missing. Save the invoice again to auto-generate.")
            refresh_invoice_weight_match(conn, invoice_id, "purchase")
        conn.execute(
            """UPDATE purchase_invoices SET status='pending_approval', submitted_by=?, submitted_at=?,
               modified_by=?, modified_at=? WHERE id=?""",
            (user_id, _ts(), user_id, _ts(), invoice_id),
        )


def approve_sale_invoice(invoice_id, user_id, override_reason=None):
    import database as db
    from db_v3 import post_sales_invoice_gl
    with db.get_connection() as conn:
        inv = conn.execute("SELECT * FROM sales_invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv:
            raise ValueError("Invoice not found.")
        inv = dict(inv)
        if inv["status"] != "pending_approval":
            raise ValueError("Only pending invoices can be approved.")
        from erp_core.period_lock import assert_period_open
        assert_period_open(
            str(inv["invoice_date"]), user_id, action="approve",
            override_reason=override_reason,
        )
        # Cash Book receipt posts on approval — day must be open first
        if _sale_will_post_cash_book(conn, inv):
            from db_cash_day import assert_cash_day_open_for_invoice
            assert_cash_day_open_for_invoice(inv["invoice_date"], kind="cash sale invoice")
        _validate_invoice_for_workflow(conn, invoice_id, "sales", stage="post")
        weighbridge = inv.get("weighbridge_required")
        if weighbridge is None:
            weighbridge = 1 if inv.get("weight_slip_id") else 0
        if weighbridge:
            if not inv["weight_slip_id"]:
                raise ValueError("Sales invoice must be linked to a completed weight slip.")
            ws = conn.execute("SELECT status, net_weight FROM weight_slips WHERE id=?", (inv["weight_slip_id"],)).fetchone()
            if not ws or ws["status"] != WEIGHT_SLIP_COMPLETE:
                raise ValueError("Weight slip must be completed (second weight recorded).")
            match = refresh_invoice_weight_match(conn, invoice_id, "sales")
            inv = conn.execute("SELECT * FROM sales_invoices WHERE id=?", (invoice_id,)).fetchone()
            settings = get_variance_settings(conn)
            if match["weight_match_status"] == "excess_variance":
                if not override_reason:
                    raise ValueError(
                        f"Weight variance {match['weight_variance_pct']}% exceeds limit {settings['limit_pct']}%. "
                        "Admin override reason required."
                    )
                if not _is_admin(conn, user_id):
                    raise ValueError("Only administrators can approve invoices with excess weight variance.")
        ts = _ts()
        conn.execute(
            """UPDATE sales_invoices SET status='approved', approved_by=?, approved_at=?,
               posted_by=?, posted_at=?, override_by=?, override_reason=?,
               modified_by=?, modified_at=? WHERE id=?""",
            (user_id, ts, user_id, ts,
             user_id if override_reason else None, override_reason or None,
             user_id, ts, invoice_id),
        )
    try:
        _post_sale_effects(invoice_id, user_id)
        post_sales_invoice_gl(invoice_id, user_id)
    except Exception:
        with db.get_connection() as conn:
            _revert_sale_approval_marker(conn, invoice_id, user_id)
        raise
    try:
        from db_audit import log_event
        log_event(
            "sales_invoices", invoice_id, "approve", user_id=user_id, module="Sales",
            document_no=inv["document_no"],
            summary=f"Approved sales invoice {inv['document_no']}",
            details={"override_reason": override_reason} if override_reason else None,
        )
    except Exception:
        pass
    from db_cache import invalidate, invalidate_invoices, invalidate_masters, invalidate_stock
    invalidate_invoices()
    invalidate_stock()
    invalidate("customers")


def approve_purchase_invoice(invoice_id, user_id, override_reason=None):
    import database as db
    from db_v3 import post_purchase_invoice_gl
    with db.get_connection() as conn:
        inv = conn.execute("SELECT * FROM purchase_invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv:
            raise ValueError("Invoice not found.")
        inv = dict(inv)
        if inv["status"] != "pending_approval":
            raise ValueError("Only pending invoices can be approved.")
        from erp_core.period_lock import assert_period_open
        assert_period_open(
            str(inv["invoice_date"]), user_id, action="approve",
            override_reason=override_reason,
        )
        if _purchase_will_post_cash_book(inv):
            from db_cash_day import assert_cash_day_open_for_invoice
            assert_cash_day_open_for_invoice(inv["invoice_date"], kind="cash purchase invoice")
        _validate_invoice_for_workflow(conn, invoice_id, "purchase", stage="post")
        weighbridge = inv.get("weighbridge_required")
        if weighbridge is None:
            weighbridge = 1 if inv.get("weight_slip_id") else 0
        if weighbridge:
            if not inv["weight_slip_id"]:
                raise ValueError("Purchase invoice must be linked to a completed weight slip.")
            ws = conn.execute("SELECT status FROM weight_slips WHERE id=?", (inv["weight_slip_id"],)).fetchone()
            if not ws or ws["status"] != WEIGHT_SLIP_COMPLETE:
                raise ValueError("Weight slip must be completed (second weight recorded).")
            match = refresh_invoice_weight_match(conn, invoice_id, "purchase")
            settings = get_variance_settings(conn)
            if match["weight_match_status"] == "excess_variance":
                if not override_reason:
                    raise ValueError(
                        f"Weight variance {match['weight_variance_pct']}% exceeds limit {settings['limit_pct']}%. "
                        "Admin override reason required."
                    )
                if not _is_admin(conn, user_id):
                    raise ValueError("Only administrators can approve invoices with excess weight variance.")
        ts = _ts()
        conn.execute(
            """UPDATE purchase_invoices SET status='approved', approved_by=?, approved_at=?,
               posted_by=?, posted_at=?, override_by=?, override_reason=?,
               modified_by=?, modified_at=? WHERE id=?""",
            (user_id, ts, user_id, ts,
             user_id if override_reason else None, override_reason or None,
             user_id, ts, invoice_id),
        )
    try:
        _post_purchase_effects(invoice_id, user_id)
        post_purchase_invoice_gl(invoice_id, user_id)
    except Exception:
        with db.get_connection() as conn:
            _revert_purchase_approval_marker(conn, invoice_id, user_id)
        raise
    try:
        from db_audit import log_event
        log_event(
            "purchase_invoices", invoice_id, "approve", user_id=user_id, module="Purchase",
            document_no=inv["document_no"],
            summary=f"Approved purchase invoice {inv['document_no']}",
            details={"override_reason": override_reason} if override_reason else None,
        )
    except Exception:
        pass
    from db_cache import invalidate, invalidate_invoices, invalidate_stock
    invalidate_invoices()
    invalidate_stock()
    invalidate("suppliers")


def reject_sale_invoice(invoice_id, user_id, reason=""):
    from database import get_connection
    from db_v3 import reverse_sales_order_delivery
    with get_connection() as conn:
        inv = conn.execute("SELECT status, order_id FROM sales_invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv or inv["status"] != "pending_approval":
            raise ValueError("Only pending invoices can be rejected.")
        if inv["order_id"]:
            reverse_sales_order_delivery(conn, inv["order_id"], invoice_id)
        conn.execute(
            """UPDATE sales_invoices SET status='rejected', rejected_by=?, rejected_at=?,
               notes=COALESCE(notes,'') || ?, modified_by=?, modified_at=? WHERE id=?""",
            (user_id, _ts(), f"\nRejected: {reason}" if reason else "", user_id, _ts(), invoice_id),
        )
        inv = conn.execute("SELECT document_no FROM sales_invoices WHERE id=?", (invoice_id,)).fetchone()
    try:
        from db_audit import log_event
        doc = inv["document_no"] if inv else ""
        log_event(
            "sales_invoices", invoice_id, "reject", user_id=user_id, module="Sales",
            document_no=doc, summary=f"Rejected sales invoice {doc}", details={"reason": reason},
        )
    except Exception:
        pass


def reject_purchase_invoice(invoice_id, user_id, reason=""):
    from database import get_connection
    from db_v3 import reverse_purchase_order_delivery
    with get_connection() as conn:
        inv = conn.execute("SELECT status, order_id FROM purchase_invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv or inv["status"] != "pending_approval":
            raise ValueError("Only pending invoices can be rejected.")
        if inv["order_id"]:
            reverse_purchase_order_delivery(conn, inv["order_id"], invoice_id)
        conn.execute(
            """UPDATE purchase_invoices SET status='rejected', rejected_by=?, rejected_at=?,
               notes=COALESCE(notes,'') || ?, modified_by=?, modified_at=? WHERE id=?""",
            (user_id, _ts(), f"\nRejected: {reason}" if reason else "", user_id, _ts(), invoice_id),
        )
        inv = conn.execute("SELECT document_no FROM purchase_invoices WHERE id=?", (invoice_id,)).fetchone()
    try:
        from db_audit import log_event
        doc = inv["document_no"] if inv else ""
        log_event(
            "purchase_invoices", invoice_id, "reject", user_id=user_id, module="Purchase",
            document_no=doc, summary=f"Rejected purchase invoice {doc}", details={"reason": reason},
        )
    except Exception:
        pass


def _reverse_invoice_payment_entries(conn, document_no):
    """Remove auto-posted cash/bank entries created on invoice approval."""
    for table in ("cash_receipts", "cash_payments", "bank_receipts", "bank_payments"):
        conn.execute(f"DELETE FROM {table} WHERE reference_no=?", (document_no,))


def unapprove_sale_invoice(invoice_id, user_id, reason=""):
    """Admin only: reverse approved posting and reopen invoice for amendment."""
    import database as db
    with db.get_connection() as conn:
        if not _is_admin(conn, user_id):
            raise ValueError("Only administrators can unapprove approved invoices.")
        inv = conn.execute("SELECT * FROM sales_invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv:
            raise ValueError("Invoice not found.")
        if inv["status"] != "approved":
            raise ValueError("Only approved invoices can be unapproved.")
        if not (reason or "").strip():
            raise ValueError("Reason is required to unapprove an invoice.")
        _reverse_sale_effects(conn, invoice_id, user_id)
        conn.execute(
            "DELETE FROM general_ledger WHERE reference_type='sales_invoice' AND reference_id=?",
            (invoice_id,),
        )
        _reverse_invoice_payment_entries(conn, inv["document_no"])
        note = f"\nUnapproved: {reason.strip()}"
        conn.execute(
            """UPDATE sales_invoices SET status='draft',
               unapproved_by=?, unapproved_at=?, unapproved_reason=?,
               notes=COALESCE(notes,'') || ?, modified_by=?, modified_at=? WHERE id=?""",
            (user_id, _ts(), reason.strip(), note, user_id, _ts(), invoice_id),
        )
    try:
        from db_audit import log_event
        log_event(
            "sales_invoices", invoice_id, "unapprove", user_id=user_id, module="Sales",
            document_no=inv["document_no"], summary=f"Unapproved sales invoice {inv['document_no']}",
            details={"reason": reason},
        )
    except Exception:
        pass


def unapprove_purchase_invoice(invoice_id, user_id, reason=""):
    """Admin only: reverse approved posting and reopen invoice for amendment."""
    import database as db
    with db.get_connection() as conn:
        if not _is_admin(conn, user_id):
            raise ValueError("Only administrators can unapprove approved invoices.")
        inv = conn.execute("SELECT * FROM purchase_invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv:
            raise ValueError("Invoice not found.")
        if inv["status"] != "approved":
            raise ValueError("Only approved invoices can be unapproved.")
        if not (reason or "").strip():
            raise ValueError("Reason is required to unapprove an invoice.")
        _reverse_purchase_effects(conn, invoice_id, user_id)
        conn.execute(
            "DELETE FROM general_ledger WHERE reference_type='purchase_invoice' AND reference_id=?",
            (invoice_id,),
        )
        _reverse_invoice_payment_entries(conn, inv["document_no"])
        note = f"\nUnapproved: {reason.strip()}"
        conn.execute(
            """UPDATE purchase_invoices SET status='draft',
               unapproved_by=?, unapproved_at=?, unapproved_reason=?,
               notes=COALESCE(notes,'') || ?, modified_by=?, modified_at=? WHERE id=?""",
            (user_id, _ts(), reason.strip(), note, user_id, _ts(), invoice_id),
        )
    try:
        from db_audit import log_event
        log_event(
            "purchase_invoices", invoice_id, "unapprove", user_id=user_id, module="Purchase",
            document_no=inv["document_no"], summary=f"Unapproved purchase invoice {inv['document_no']}",
            details={"reason": reason},
        )
    except Exception:
        pass


def cancel_sale_invoice(invoice_id, user_id):
    import database as db
    with db.get_connection() as conn:
        inv = conn.execute("SELECT * FROM sales_invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv:
            raise ValueError("Invoice not found.")
        if inv["status"] == "cancelled":
            return
        if inv["status"] == "approved":
            _reverse_sale_effects(conn, invoice_id, user_id)
            conn.execute(
                "DELETE FROM general_ledger WHERE reference_type='sales_invoice' AND reference_id=?",
                (invoice_id,),
            )
        if inv["order_id"]:
            from db_v3 import reverse_sales_order_delivery
            reverse_sales_order_delivery(conn, inv["order_id"], invoice_id)
        conn.execute(
            """UPDATE sales_invoices SET status='cancelled', cancelled_by=?, cancelled_at=?,
               modified_by=?, modified_at=? WHERE id=?""",
            (user_id, _ts(), user_id, _ts(), invoice_id),
        )


def cancel_purchase_invoice(invoice_id, user_id):
    import database as db
    with db.get_connection() as conn:
        inv = conn.execute("SELECT * FROM purchase_invoices WHERE id=?", (invoice_id,)).fetchone()
        if not inv:
            raise ValueError("Invoice not found.")
        if inv["status"] == "cancelled":
            return
        if inv["status"] == "approved":
            _reverse_purchase_effects(conn, invoice_id, user_id)
            conn.execute(
                "DELETE FROM general_ledger WHERE reference_type='purchase_invoice' AND reference_id=?",
                (invoice_id,),
            )
        if inv["order_id"]:
            from db_v3 import reverse_purchase_order_delivery
            reverse_purchase_order_delivery(conn, inv["order_id"], invoice_id)
        conn.execute(
            """UPDATE purchase_invoices SET status='cancelled', cancelled_by=?, cancelled_at=?,
               modified_by=?, modified_at=? WHERE id=?""",
            (user_id, _ts(), user_id, _ts(), invoice_id),
        )


def _is_counter_cash_customer(conn, customer_id) -> bool:
    """Retail / SALE IN CASH master — cash on approval even if saved as credit.

    Match code 100013 or exact cash-sale names only (not 'M. ALI SALE IN CASH').
    """
    if not customer_id:
        return False
    row = conn.execute(
        "SELECT code, name FROM customers WHERE id=?", (customer_id,)
    ).fetchone()
    if not row:
        return False
    code = str(row["code"] or "").strip()
    name = str(row["name"] or "").strip().upper()
    if code == "100013":
        return True
    return name in ("SALE IN CASH", "CASH SALE", "CASH SALES")


def _sale_will_post_cash_book(conn, inv) -> bool:
    """True when approving this sale will insert a Cash Book receipt."""
    if _is_counter_cash_customer(conn, inv.get("customer_id")):
        return True
    paid = float(inv.get("paid_amount") or 0)
    mode = (inv.get("payment_mode") or "credit").lower()
    return paid > 0.009 and mode == "cash"


def _purchase_will_post_cash_book(inv) -> bool:
    paid = float(inv.get("paid_amount") or 0)
    mode = (inv.get("payment_mode") or "credit").lower()
    return paid > 0.009 and mode == "cash"


def _revert_sale_approval_marker(conn, invoice_id, user_id):
    conn.execute(
        """UPDATE sales_invoices SET status='pending_approval',
           approved_by=NULL, approved_at=NULL, posted_by=NULL, posted_at=NULL,
           modified_by=?, modified_at=? WHERE id=? AND status='approved'""",
        (user_id, _ts(), invoice_id),
    )


def _revert_purchase_approval_marker(conn, invoice_id, user_id):
    conn.execute(
        """UPDATE purchase_invoices SET status='pending_approval',
           approved_by=NULL, approved_at=NULL, posted_by=NULL, posted_at=NULL,
           modified_by=?, modified_at=? WHERE id=? AND status='approved'""",
        (user_id, _ts(), invoice_id),
    )


def _post_sale_effects(invoice_id, user_id):
    import database as db
    with db.get_connection() as conn:
        inv = db.row_to_dict(conn.execute("SELECT * FROM sales_invoices WHERE id=?", (invoice_id,)).fetchone())
        if not inv:
            return
        wh = db._default_warehouse_id(conn)
        items = conn.execute("SELECT * FROM sales_invoice_items WHERE invoice_id=?", (invoice_id,)).fetchall()
        update_stock = not inv.get("dn_id")
        if update_stock:
            for r in items:
                db._adjust_warehouse_stock(conn, r["product_id"], wh, -r["quantity"])
                db._record_movement(conn, r["product_id"], wh, "out", r["quantity"],
                                    "sales_invoice", invoice_id, inv["document_no"], user_id)
        total = float(inv["total"])
        paid = float(inv.get("paid_amount") or 0)
        mode = (inv.get("payment_mode") or "credit").lower()
        # Counter cash party often imported/saved as credit with paid=0 — still cash in hand.
        if paid <= 0.009 and _is_counter_cash_customer(conn, inv.get("customer_id")):
            paid = total
            mode = "cash"
            conn.execute(
                "UPDATE sales_invoices SET paid_amount=?, payment_mode='cash' WHERE id=?",
                (paid, invoice_id),
            )
            inv["paid_amount"] = paid
            inv["payment_mode"] = "cash"
        conn.execute(
            "UPDATE customers SET current_balance=current_balance+? WHERE id=?",
            (total - paid, inv["customer_id"]),
        )
        if paid > 0:
            # Avoid duplicate cash/bank rows if approval is retried
            exists = conn.execute(
                "SELECT 1 FROM cash_receipts WHERE reference_no=? LIMIT 1",
                (inv["document_no"],),
            ).fetchone() or conn.execute(
                "SELECT 1 FROM bank_receipts WHERE reference_no=? LIMIT 1",
                (inv["document_no"],),
            ).fetchone()
            if not exists:
                # Counter cash (SALE IN CASH): cash book + GL only — party ledger is
                # settled via paid_amount on the invoice (same as FMYE NIL balance).
                link_party = not _is_counter_cash_customer(conn, inv.get("customer_id"))
                pty = ("customer", inv["customer_id"]) if link_party else (None, None)
                if mode == "cash":
                    db._add_cash_receipt(
                        conn, inv["invoice_date"], f"Sale {inv['document_no']}",
                        inv["document_no"], paid, user_id,
                        party_type=pty[0], party_id=pty[1],
                    )
                elif mode == "bank":
                    db._add_bank_receipt(
                        conn, inv["invoice_date"], f"Sale {inv['document_no']}",
                        inv["document_no"], paid, None, user_id,
                        party_type=pty[0], party_id=pty[1],
                    )


def settle_counter_cash_customer_ledgers(user_id=None) -> dict:
    """Backfill: mark SALE IN CASH style invoices as fully paid so party ledger is NIL.

    FMYE posts cash sales to Cash + Sale A/C without leaving AR on party 100013.
    IFS imported those invoices as credit/unpaid — this aligns paid_amount and balance.
    """
    import database as db
    with db.get_connection() as conn:
        parties = conn.execute(
            """SELECT id, code, name FROM customers
               WHERE code='100013'
                  OR UPPER(TRIM(name)) IN ('SALE IN CASH','CASH SALE','CASH SALES')"""
        ).fetchall()
        party_ids = [int(r["id"]) for r in parties]
        if not party_ids:
            return {"parties": 0, "invoices": 0, "receipts_unlinked": 0, "fmye_cleared": 0}

        placeholders = ",".join("?" * len(party_ids))
        cur = conn.execute(
            f"""UPDATE sales_invoices
                SET paid_amount=total, payment_mode='cash'
                WHERE customer_id IN ({placeholders})
                  AND status='approved'
                  AND COALESCE(paid_amount,0) < total - 0.009""",
            party_ids,
        )
        inv_n = cur.rowcount

        # Receipts already settle invoice via paid_amount — do not also credit party ledger
        cur2 = conn.execute(
            f"""UPDATE cash_receipts SET party_type=NULL, party_id=NULL
                WHERE party_type='customer' AND party_id IN ({placeholders})""",
            party_ids,
        )
        cur3 = conn.execute(
            f"""UPDATE bank_receipts SET party_type=NULL, party_id=NULL
                WHERE party_type='customer' AND party_id IN ({placeholders})""",
            party_ids,
        )
        unlink_n = (cur2.rowcount or 0) + (cur3.rowcount or 0)

        # FMYE import skipped SL/JVR debit sides (treated as invoice duplicates) but kept
        # transfer credits on 100013 — remove those orphans so party ledger matches FMYE NIL.
        db._ensure_fmye_party_entries_table(conn)
        cur4 = conn.execute(
            f"""DELETE FROM fmye_party_entries
                WHERE party_type='customer' AND party_id IN ({placeholders})""",
            party_ids,
        )
        fmye_n = cur4.rowcount or 0

    # Recalc balances from ledger for these parties only
    for pid in party_ids:
        _, entries = db.get_customer_ledger(pid)
        closing = float(entries[-1]["balance"]) if entries else 0.0
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE customers SET current_balance=?, modified_at=? WHERE id=?",
                (closing, db._now(), pid),
            )
    return {
        "parties": len(party_ids),
        "invoices": inv_n,
        "receipts_unlinked": unlink_n,
        "fmye_cleared": fmye_n,
        "party_ids": party_ids,
    }


def _reverse_sale_effects(conn, invoice_id, user_id):
    import database as db
    inv = db.row_to_dict(conn.execute("SELECT * FROM sales_invoices WHERE id=?", (invoice_id,)).fetchone())
    if not inv:
        return
    wh = db._default_warehouse_id(conn)
    items = conn.execute("SELECT * FROM sales_invoice_items WHERE invoice_id=?", (invoice_id,)).fetchall()
    if not inv.get("dn_id"):
        for r in items:
            db._adjust_warehouse_stock(conn, r["product_id"], wh, r["quantity"])
    total = float(inv["total"])
    paid = float(inv.get("paid_amount") or 0)
    conn.execute(
        "UPDATE customers SET current_balance=current_balance-? WHERE id=?",
        (total - paid, inv["customer_id"]),
    )


def _post_purchase_effects(invoice_id, user_id):
    import database as db
    with db.get_connection() as conn:
        inv = db.row_to_dict(conn.execute("SELECT * FROM purchase_invoices WHERE id=?", (invoice_id,)).fetchone())
        if not inv:
            return
        wh = db._default_warehouse_id(conn)
        update_stock = not inv.get("grn_id")
        items = conn.execute("SELECT * FROM purchase_invoice_items WHERE invoice_id=?", (invoice_id,)).fetchall()
        if update_stock:
            from db_stock_costing import apply_purchase_inbound_cost
            for r in items:
                rate = float(r["rate"] or 0)
                qty = float(r["quantity"] or 0)
                # Weighted average for on-hand; last purchase rate on product master
                apply_purchase_inbound_cost(conn, wh, r["product_id"], qty, rate)
                db._adjust_warehouse_stock(conn, r["product_id"], wh, qty)
                db._record_movement(conn, r["product_id"], wh, "in", qty,
                                    "purchase_invoice", invoice_id, inv["document_no"], user_id)
        else:
            # GRN already increased stock + WAC — refresh last purchase rate only
            from db_stock_costing import apply_purchase_inbound_cost
            for r in items:
                apply_purchase_inbound_cost(
                    conn, wh, r["product_id"], 0, float(r["rate"] or 0),
                    update_last_rate=True,
                )
        total = float(inv["total"])
        paid = float(inv.get("paid_amount") or 0)
        conn.execute(
            "UPDATE suppliers SET current_balance=current_balance-? WHERE id=?",
            (total - paid, inv["supplier_id"]),
        )
        if paid > 0:
            mode = inv.get("payment_mode") or "credit"
            if mode == "cash":
                db._add_cash_payment(conn, inv["invoice_date"], f"Purchase {inv['document_no']}",
                                     inv["document_no"], paid, user_id)
            elif mode == "bank":
                db._add_bank_payment(conn, inv["invoice_date"], f"Purchase {inv['document_no']}",
                                     inv["document_no"], paid, user_id)


def _reverse_purchase_effects(conn, invoice_id, user_id):
    import database as db
    inv = db.row_to_dict(conn.execute("SELECT * FROM purchase_invoices WHERE id=?", (invoice_id,)).fetchone())
    if not inv:
        return
    wh = db._default_warehouse_id(conn)
    items = conn.execute("SELECT * FROM purchase_invoice_items WHERE invoice_id=?", (invoice_id,)).fetchall()
    if not inv.get("grn_id"):
        for r in items:
            db._adjust_warehouse_stock(conn, r["product_id"], wh, -r["quantity"])
    total = float(inv["total"])
    paid = float(inv.get("paid_amount") or 0)
    conn.execute(
        "UPDATE suppliers SET current_balance=current_balance+? WHERE id=?",
        (total - paid, inv["supplier_id"]),
    )


def generate_gate_pass_from_sale(sale_id, user_id, require_approved=False):
    from db_commercial import build_gate_pass_sale_remarks, ensure_gate_pass_schema, save_gate_pass
    import database as db
    ensure_gate_pass_schema()
    sale = db.get_sale(sale_id)
    if not sale:
        raise ValueError("Sale invoice not found.")
    if require_approved and sale.get("status") != "approved":
        raise ValueError("Gate pass can only be generated from an approved sales invoice.")
    existing = db.get_gate_passes(sales_invoice_id=sale_id)
    pass_id = existing[0]["id"] if existing else None
    ws = db.get_weight_slip_pro(sale.get("weight_slip_id")) if sale.get("weight_slip_id") else {}
    items = sale.get("items") or []
    desc = ", ".join(
        f"{i['item_name']} x {i['quantity']} ({float(i.get('net_weight') or 0):,.3f} kg)"
        for i in items[:5]
    )
    from db_commercial import sale_weighbridge_active
    if (sale.get("weight_match_status") or "") == "reference":
        # Reference-only: GP weight = this invoice's lines, not full slip net
        phys_wt = float(sale.get("total_net_weight") or 0)
    else:
        phys_wt = float(sale.get("physical_weight_kg") or ws.get("net_weight") or 0)
        if not sale_weighbridge_active(sale):
            phys_wt = 0.0
    vehicle = (ws.get("vehicle_no") or sale.get("vehicle_no") or "").strip() or None
    driver = (ws.get("driver_name") or sale.get("driver_name") or "").strip() or None
    driver_contact = (sale.get("driver_contact") or "").strip() or None
    data = {
        "pass_type": "material_out",
        "pass_date": sale["sale_date"],
        "pass_time": _ts()[11:19],
        "sales_invoice_id": sale_id,
        "weight_slip_id": sale.get("weight_slip_id"),
        "customer_id": sale["customer_id"],
        "party_name": sale.get("customer_name"),
        "vehicle_no": vehicle,
        "driver_name": driver,
        "driver_contact": driver_contact,
        "material_desc": desc,
        "quantity": sum(float(i["quantity"]) for i in items),
        "weight": phys_wt,
        "remarks": build_gate_pass_sale_remarks(sale, ws),
        "notify_dispatch": True,  # notify even when regenerating an existing GP
    }
    if sale.get("delivery_note_id"):
        data["delivery_note_id"] = sale["delivery_note_id"]
    gid = save_gate_pass(data, pass_id, user_id, skip_approval_check=True)
    with db.get_connection() as conn:
        conn.execute("UPDATE sales_invoices SET gate_pass_id=? WHERE id=?", (gid, sale_id))
    return gid


def generate_gate_pass_from_purchase(purchase_id, user_id, require_approved=False):
    from db_commercial import ensure_gate_pass_schema, save_gate_pass
    import database as db
    ensure_gate_pass_schema()
    pur = db.get_purchase(purchase_id)
    if not pur:
        raise ValueError("Purchase invoice not found.")
    if require_approved and pur.get("status") != "approved":
        raise ValueError("Inward gate pass requires an approved purchase invoice.")
    existing = db.get_gate_passes(purchase_invoice_id=purchase_id)
    pass_id = existing[0]["id"] if existing else None
    ws = db.get_weight_slip_pro(pur.get("weight_slip_id")) if pur.get("weight_slip_id") else {}
    items = pur.get("items") or []
    desc = ", ".join(
        f"{i['item_name']} x {i['quantity']} ({float(i.get('net_weight') or 0):,.3f} kg)"
        for i in items[:5]
    )
    inv_wt = float(pur.get("total_net_weight") or 0)
    if (pur.get("weight_match_status") or "") == "reference":
        phys = inv_wt
        remark_parts = [
            f"Invoice {pur['invoice_no']}",
            f"Slip {ws.get('document_no') or '—'} (reference)",
            f"Inv wt {inv_wt:,.3f} kg | Slip ref only (no variance)",
        ]
    else:
        phys = float(pur.get("physical_weight_kg") or ws.get("net_weight") or 0)
        var_kg = float(pur.get("weight_variance_kg") or round(phys - inv_wt, 3))
        remark_parts = [
            f"Invoice {pur['invoice_no']}",
            f"Slip {ws.get('document_no') or '—'}",
            f"Inv wt {inv_wt:,.3f} kg | Phys {phys:,.3f} kg | Var {var_kg:+,.3f} kg",
        ]
    pur_notes = (pur.get("notes") or "").strip()
    if pur_notes:
        remark_parts.append(pur_notes)
    data = {
        "pass_type": "material_in",
        "pass_date": pur["purchase_date"],
        "pass_time": _ts()[11:19],
        "purchase_invoice_id": purchase_id,
        "weight_slip_id": pur.get("weight_slip_id"),
        "supplier_id": pur["supplier_id"],
        "party_name": pur.get("supplier_name"),
        "vehicle_no": ws.get("vehicle_no"),
        "driver_name": ws.get("driver_name"),
        "material_desc": desc,
        "quantity": sum(float(i["quantity"]) for i in items),
        "weight": phys,
        "remarks": " | ".join(remark_parts),
    }
    if pur.get("grn_id"):
        data["grn_id"] = pur["grn_id"]
    gid = save_gate_pass(data, pass_id, user_id, skip_approval_check=True)
    with db.get_connection() as conn:
        conn.execute("UPDATE purchase_invoices SET gate_pass_id=? WHERE id=?", (gid, purchase_id))
    return gid


def get_sales_by_status(status=None):
    from database import get_connection, rows_to_list
    q = """SELECT s.id, s.document_no AS invoice_no, s.invoice_date AS sale_date, s.customer_id,
                  s.subtotal, s.tax, s.total, s.status, s.weight_match_status, s.total_net_weight,
                  s.physical_weight_kg, s.weight_variance_kg, s.weight_variance_pct, s.gate_pass_id,
                  c.name AS customer_name, ws.document_no AS weight_slip_no,
                  gp.document_no AS gate_pass_no
           FROM sales_invoices s
           JOIN customers c ON s.customer_id=c.id
           LEFT JOIN weight_slips ws ON s.weight_slip_id=ws.id
           LEFT JOIN gate_passes gp ON s.gate_pass_id=gp.id WHERE 1=1"""
    p = []
    if status:
        q += " AND s.status=?"; p.append(status)
    q += " ORDER BY s.invoice_date DESC, s.id DESC"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


def get_purchases_by_status(status=None):
    from database import get_connection, rows_to_list
    q = """SELECT p.id, p.document_no AS invoice_no, p.invoice_date AS purchase_date, p.supplier_id,
                  p.total, p.status, p.weight_match_status, p.total_net_weight, p.physical_weight_kg,
                  p.weight_variance_kg, s.name AS supplier_name, ws.document_no AS weight_slip_no
           FROM purchase_invoices p
           JOIN suppliers s ON p.supplier_id=s.id
           LEFT JOIN weight_slips ws ON p.weight_slip_id=ws.id WHERE 1=1"""
    params = []
    if status:
        q += " AND p.status=?"; params.append(status)
    q += " ORDER BY p.invoice_date DESC, p.id DESC"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, params).fetchall())
