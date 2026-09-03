"""Commercial readiness: taxation, weighbridge, gate pass, dashboard, backup."""

import shutil
from datetime import datetime
from pathlib import Path

SCHEMA_COMMERCIAL_PATH = Path(__file__).parent / "schema_commercial.sql"


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def next_weight_slip_no(conn=None):
    """Reference format: W20260531-0003 (daily sequence, no reuse after delete)."""
    from database import get_connection
    ymd = datetime.now().strftime("%Y%m%d")

    def _run(c):
        row = c.execute(
            """SELECT MAX(CAST(SUBSTR(document_no, 11) AS INTEGER))
               FROM weight_slips WHERE document_no LIKE ?""",
            (f"W{ymd}-%",),
        ).fetchone()
        seq = int(row[0] or 0) + 1
        return f"W{ymd}-{seq:04d}"

    if conn is not None:
        return _run(conn)
    with get_connection() as conn:
        return _run(conn)


def slip_transaction_type(slip_row):
    """Map slip to SALE / PURCHASE like reference weight scale software."""
    if slip_row.get("customer_id"):
        return "SALE"
    if slip_row.get("supplier_id"):
        return "PURCHASE"
    pt = (slip_row.get("party_type") or "").lower()
    if pt == "customer":
        return "SALE"
    if pt == "supplier":
        return "PURCHASE"
    return "GENERAL"


def _commercial_ver(conn):
    r = conn.execute("SELECT value FROM schema_meta WHERE key='commercial_version'").fetchone()
    return int(r[0]) if r else 0


def apply_commercial(conn, db_module):
    ver = _commercial_ver(conn)
    if ver < 1:
        if SCHEMA_COMMERCIAL_PATH.exists():
            conn.executescript(SCHEMA_COMMERCIAL_PATH.read_text(encoding="utf-8"))
        _extend_columns(conn)
        _seed_commercial(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('commercial_version','1') "
            "ON CONFLICT(key) DO UPDATE SET value='1'"
        )
    if _commercial_ver(conn) < 2:
        _apply_tax_v2(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('commercial_version','2') "
            "ON CONFLICT(key) DO UPDATE SET value='2'"
        )
    if _commercial_ver(conn) < 3:
        _apply_gate_pass_links_v3(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('commercial_version','3') "
            "ON CONFLICT(key) DO UPDATE SET value='3'"
        )
    if _commercial_ver(conn) < 4:
        _apply_weight_invoice_v4(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('commercial_version','4') "
            "ON CONFLICT(key) DO UPDATE SET value='4'"
        )
    if _commercial_ver(conn) < 5:
        _apply_invoice_workflow_v5(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('commercial_version','5') "
            "ON CONFLICT(key) DO UPDATE SET value='5'"
        )
    if _commercial_ver(conn) < 6:
        _add_col(conn, "sales_invoices", "weighbridge_required", "INTEGER DEFAULT 1")
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('commercial_version','6') "
            "ON CONFLICT(key) DO UPDATE SET value='6'"
        )
    if _commercial_ver(conn) < 7:
        _add_col(conn, "purchase_invoices", "weighbridge_required", "INTEGER DEFAULT 1")
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('commercial_version','7') "
            "ON CONFLICT(key) DO UPDATE SET value='7'"
        )
    if _commercial_ver(conn) < 8:
        for t in ("sales_invoices", "purchase_invoices"):
            for col, ddl in [
                ("unapproved_by", "INTEGER"),
                ("unapproved_at", "TEXT"),
                ("unapproved_reason", "TEXT"),
            ]:
                _add_col(conn, t, col, ddl)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('commercial_version','8') "
            "ON CONFLICT(key) DO UPDATE SET value='8'"
        )
    if _commercial_ver(conn) < 9:
        _apply_gate_pass_full_columns(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('commercial_version','9') "
            "ON CONFLICT(key) DO UPDATE SET value='9'"
        )
    if _commercial_ver(conn) < 10:
        _apply_gate_pass_full_columns(conn)
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('commercial_version','10') "
            "ON CONFLICT(key) DO UPDATE SET value='10'"
        )
    if _commercial_ver(conn) < 11:
        for col, ddl in [
            ("vehicle_no", "TEXT"),
            ("driver_name", "TEXT"),
            ("driver_contact", "TEXT"),
            ("dispatch_remarks", "TEXT"),
        ]:
            _add_col(conn, "sales_invoices", col, ddl)
        _add_col(conn, "gate_passes", "driver_contact", "TEXT")
        conn.execute(
            "INSERT INTO schema_meta(key,value) VALUES('commercial_version','11') "
            "ON CONFLICT(key) DO UPDATE SET value='11'"
        )
    ensure_gate_pass_schema(conn)
    if _col_exists(conn, "weight_slips", "status"):
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ws_status ON weight_slips(status)")
    if _col_exists(conn, "gate_passes", "status"):
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gp_status ON gate_passes(status)")


def _col_exists(conn, table, col):
    return col in [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]


def _add_col(conn, table, col, ddl):
    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
        if not _col_exists(conn, table, col):
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


def _extend_columns(conn):
    for t, col, ddl in [
        ("sales_invoices", "discount_pct", "REAL DEFAULT 0"),
        ("sales_invoices", "tax_rate_id", "INTEGER"),
        ("purchase_invoices", "discount_pct", "REAL DEFAULT 0"),
        ("purchase_invoices", "tax_rate_id", "INTEGER"),
        ("weight_slips", "slip_time", "TEXT"),
        ("weight_slips", "vehicle_no", "TEXT"),
        ("weight_slips", "customer_id", "INTEGER"),
        ("weight_slips", "supplier_id", "INTEGER"),
        ("weight_slips", "product_id", "INTEGER"),
        ("weight_slips", "party_type", "TEXT"),
        ("weight_slips", "first_weight_time", "TEXT"),
        ("weight_slips", "second_weight_time", "TEXT"),
        ("weight_slips", "print_time", "TEXT"),
        ("weight_slips", "save_time", "TEXT"),
        ("weight_slips", "weight_difference", "REAL DEFAULT 0"),
    ]:
        _add_col(conn, t, col, ddl)


def _seed_commercial(conn):
    conn.execute("INSERT OR IGNORE INTO document_sequences(doc_type,prefix,padding) VALUES('GP','GP',4)")


def _apply_gate_pass_links_v3(conn):
    for col, ddl in [
        ("sales_invoice_id", "INTEGER REFERENCES sales_invoices(id)"),
        ("purchase_invoice_id", "INTEGER REFERENCES purchase_invoices(id)"),
        ("delivery_note_id", "INTEGER REFERENCES delivery_notes(id)"),
        ("grn_id", "INTEGER REFERENCES goods_receipt_notes(id)"),
    ]:
        _add_col(conn, "gate_passes", col, ddl)


def ensure_gate_pass_schema(conn=None):
    """Add missing gate_passes columns on legacy DBs (safe to call before any gate pass SQL)."""
    from database import get_connection
    if conn is not None:
        _apply_gate_pass_full_columns(conn)
        return
    with get_connection() as c:
        _apply_gate_pass_full_columns(c)


def _apply_gate_pass_full_columns(conn):
    """Older DBs created gate_passes before customer/supplier/product columns existed."""
    if not conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='gate_passes'"
    ).fetchone():
        return
    for col, ddl in [
        ("pass_time", "TEXT"),
        ("vehicle_no", "TEXT"),
        ("driver_name", "TEXT"),
        ("party_name", "TEXT"),
        ("customer_id", "INTEGER REFERENCES customers(id)"),
        ("supplier_id", "INTEGER REFERENCES suppliers(id)"),
        ("product_id", "INTEGER REFERENCES products(id)"),
        ("material_desc", "TEXT"),
        ("quantity", "REAL DEFAULT 0"),
        ("weight", "REAL DEFAULT 0"),
        ("weight_slip_id", "INTEGER REFERENCES weight_slips(id)"),
        ("sales_invoice_id", "INTEGER REFERENCES sales_invoices(id)"),
        ("purchase_invoice_id", "INTEGER REFERENCES purchase_invoices(id)"),
        ("delivery_note_id", "INTEGER REFERENCES delivery_notes(id)"),
        ("grn_id", "INTEGER REFERENCES goods_receipt_notes(id)"),
        ("status", "TEXT DEFAULT 'open'"),
        ("approved_by", "INTEGER"),
        ("approved_at", "TEXT"),
        ("remarks", "TEXT"),
        ("driver_contact", "TEXT"),
        ("modified_by", "INTEGER"),
        ("modified_at", "TEXT"),
    ]:
        _add_col(conn, "gate_passes", col, ddl)


GATE_PASS_OUTWARD = ("material_out", "fg_dispatch")
GATE_PASS_INWARD = ("material_in",)
# Packaging / raw-material inward passes — not shown on dashboard Approvals badge.
GATE_PASS_PENDING_TYPES = GATE_PASS_OUTWARD


def gate_pass_pending_count_sql() -> str:
    """Open outward gate passes for dashboard pending count (excludes packaging material in)."""
    types = ", ".join(f"'{t}'" for t in GATE_PASS_PENDING_TYPES)
    return f"""SELECT COUNT(*) FROM gate_passes gp
                   LEFT JOIN customers c ON c.id = gp.customer_id
                   WHERE gp.status='open'
                     AND gp.pass_type IN ({types})
                     AND UPPER(TRIM(COALESCE(c.code,''))) != '100013'
                     AND UPPER(TRIM(COALESCE(c.name, gp.party_name, '')))
                         NOT IN ('SALE IN CASH', 'CASH SALE', 'CASH SALES')"""


def _apply_weight_invoice_v4(conn):
    for t, col, ddl in [
        ("sales_invoices", "weight_slip_id", "INTEGER REFERENCES weight_slips(id)"),
        ("sales_invoices", "total_net_weight", "REAL DEFAULT 0"),
        ("purchase_invoices", "weight_slip_id", "INTEGER REFERENCES weight_slips(id)"),
        ("purchase_invoices", "total_net_weight", "REAL DEFAULT 0"),
    ]:
        _add_col(conn, t, col, ddl)


def _apply_invoice_workflow_v5(conn):
    inv_cols = [
        ("submitted_by", "INTEGER"), ("submitted_at", "TEXT"),
        ("approved_by", "INTEGER"), ("approved_at", "TEXT"),
        ("rejected_by", "INTEGER"), ("rejected_at", "TEXT"),
        ("cancelled_by", "INTEGER"), ("cancelled_at", "TEXT"),
        ("override_by", "INTEGER"), ("override_reason", "TEXT"),
        ("physical_weight_kg", "REAL DEFAULT 0"),
        ("weight_variance_kg", "REAL DEFAULT 0"),
        ("weight_variance_pct", "REAL DEFAULT 0"),
        ("weight_match_status", "TEXT"),
        ("gate_pass_id", "INTEGER"),
    ]
    for t in ("sales_invoices", "purchase_invoices"):
        for col, ddl in inv_cols:
            _add_col(conn, t, col, ddl)
    _add_col(conn, "weight_slips", "status", "TEXT DEFAULT 'completed'")
    for key, val in [("weight_variance_minor_pct", "1"), ("weight_variance_limit_pct", "5")]:
        conn.execute(
            "INSERT OR IGNORE INTO system_settings(key,value) VALUES(?,?)",
            (key, val),
        )
    conn.execute("UPDATE sales_invoices SET status='approved' WHERE status IN ('posted', '') OR status IS NULL")
    conn.execute("UPDATE purchase_invoices SET status='approved' WHERE status IN ('posted', '') OR status IS NULL")


def enrich_line_weights(conn, line_items):
    """Fill net_weight on lines from qty × standard_weight when missing."""
    out = []
    for li in line_items:
        row = dict(li)
        pid = row.get("item_id") or row.get("product_id")
        qty = float(row.get("quantity") or 0)
        nw = float(row.get("net_weight") or 0)
        if pid and nw <= 0:
            pr = conn.execute("SELECT standard_weight FROM products WHERE id=?", (pid,)).fetchone()
            sw = float(pr[0] or 0) if pr else 0
            if sw > 0:
                nw = round(qty * sw, 3)
            elif qty > 0:
                nw = qty
        row["net_weight"] = nw
        out.append(row)
    return out


def invoice_lines_net_weight(conn, invoice_id, kind="sales"):
    table = "sales_invoice_items" if kind == "sales" else "purchase_invoice_items"
    col = "invoice_id"
    r = conn.execute(f"SELECT COALESCE(SUM(net_weight),0) FROM {table} WHERE {col}=?", (invoice_id,)).fetchone()
    return float(r[0] or 0)


def invoice_primary_product_id(conn, invoice_id, kind="sales"):
    """Main line product on invoice (highest net weight line) for slip item sync."""
    table = "sales_invoice_items" if kind == "sales" else "purchase_invoice_items"
    row = conn.execute(
        f"""SELECT product_id FROM {table}
            WHERE invoice_id=? AND product_id IS NOT NULL
            ORDER BY COALESCE(net_weight, 0) DESC, id ASC LIMIT 1""",
        (invoice_id,),
    ).fetchone()
    return int(row[0]) if row and row[0] else None


def link_weight_slip_to_invoice(slip_id, ref_type, ref_id, user_id=None, *, as_primary=None):
    """Link weight slip ↔ sales/purchase invoice.

    One slip may attach to many invoices:
    - **Primary** (default when slip has no owner): full net weight + variance on this invoice;
      updates weight_slips.reference_*.
    - **Reference-only**: invoice shows the slip number only; no weight split/variance.
      Used when the slip is already primary on another invoice (or as_primary=False).
    """
    from database import get_connection
    from db_invoice_workflow import (
        _is_primary_weight_slip_for_invoice,
        refresh_invoice_weight_match,
    )
    if ref_type not in ("sales_invoice", "purchase_invoice") or not ref_id:
        return
    kind = "sales" if ref_type == "sales_invoice" else "purchase"
    inv_table = "sales_invoices" if kind == "sales" else "purchase_invoices"
    with get_connection() as conn:
        slip = conn.execute(
            "SELECT net_weight, status, reference_type, reference_id FROM weight_slips WHERE id=?",
            (slip_id,),
        ).fetchone()
        if not slip:
            return
        if slip["status"] != "completed" or float(slip["net_weight"] or 0) <= 0:
            raise ValueError("Only completed slips with net weight can be linked to an invoice.")
        inv_row = conn.execute(
            f"SELECT weight_slip_id FROM {inv_table} WHERE id=?", (ref_id,),
        ).fetchone()
        if inv_row and inv_row["weight_slip_id"] and int(inv_row["weight_slip_id"]) != int(slip_id):
            raise ValueError("That invoice already has a different weight slip linked.")

        has_primary = (
            slip["reference_type"] in ("sales_invoice", "purchase_invoice")
            and slip["reference_id"] is not None
        )
        same_primary = (
            has_primary
            and slip["reference_type"] == ref_type
            and int(slip["reference_id"]) == int(ref_id)
        )
        if as_primary is None:
            claim_primary = (not has_primary) or same_primary
        else:
            claim_primary = bool(as_primary)
            if claim_primary and has_primary and not same_primary:
                # Re-save / Submit for Approval on an invoice that already has this slip:
                # keep reference-only instead of failing (do not steal another invoice's primary).
                already_on_this = (
                    inv_row
                    and inv_row["weight_slip_id"]
                    and int(inv_row["weight_slip_id"]) == int(slip_id)
                )
                if already_on_this:
                    claim_primary = False
                else:
                    raise ValueError(
                        "This weight slip already has a primary invoice. "
                        "Attach as reference-only, or detach the primary invoice first."
                    )

        inv_wt = invoice_lines_net_weight(conn, ref_id, kind)
        conn.execute(
            f"UPDATE {inv_table} SET weight_slip_id=?, total_net_weight=? WHERE id=?",
            (slip_id, inv_wt, ref_id),
        )

        if claim_primary:
            physical = float(slip["net_weight"] or 0)
            variance = round(physical - inv_wt, 3)
            pid = invoice_primary_product_id(conn, ref_id, kind)
            if kind == "sales":
                inv = conn.execute(
                    "SELECT customer_id FROM sales_invoices WHERE id=?", (ref_id,),
                ).fetchone()
                cust_id = inv["customer_id"] if inv else None
                conn.execute(
                    """UPDATE weight_slips SET reference_type=?, reference_id=?, weight_difference=?,
                       product_id=COALESCE(?, product_id), customer_id=COALESCE(?, customer_id),
                       supplier_id=NULL, party_type='customer', modified_at=?, modified_by=? WHERE id=?""",
                    (ref_type, ref_id, variance, pid, cust_id, now(), user_id, slip_id),
                )
            else:
                inv = conn.execute(
                    "SELECT supplier_id FROM purchase_invoices WHERE id=?", (ref_id,),
                ).fetchone()
                sup_id = inv["supplier_id"] if inv else None
                conn.execute(
                    """UPDATE weight_slips SET reference_type=?, reference_id=?, weight_difference=?,
                       product_id=COALESCE(?, product_id), supplier_id=COALESCE(?, supplier_id),
                       customer_id=NULL, party_type='supplier', modified_at=?, modified_by=? WHERE id=?""",
                    (ref_type, ref_id, variance, pid, sup_id, now(), user_id, slip_id),
                )
            refresh_invoice_weight_match(conn, ref_id, kind)
        else:
            # Reference-only: do not move slip.reference_* or overwrite weight_difference
            refresh_invoice_weight_match(conn, ref_id, kind)


def get_weight_slip_invoice_attachment(slip_id):
    """Return the **primary** sales/purchase invoice for this slip, if any."""
    from database import get_connection, row_to_dict

    with get_connection() as conn:
        slip = conn.execute(
            "SELECT reference_type, reference_id FROM weight_slips WHERE id=?", (slip_id,),
        ).fetchone()
        if slip and slip["reference_type"] in ("sales_invoice", "purchase_invoice") and slip["reference_id"]:
            kind = "sales" if slip["reference_type"] == "sales_invoice" else "purchase"
            table = "sales_invoices" if kind == "sales" else "purchase_invoices"
            row = conn.execute(
                f"""SELECT id, document_no AS invoice_no, status, gate_pass_id, ? AS kind,
                           'primary' AS link_role
                    FROM {table} WHERE id=?""",
                (kind, slip["reference_id"]),
            ).fetchone()
            if row:
                return row_to_dict(row)
        # Fallback: earliest invoice still pointing at this slip
        row = conn.execute(
            """SELECT id, document_no AS invoice_no, status, gate_pass_id, 'sales' AS kind,
                      'primary' AS link_role
               FROM sales_invoices WHERE weight_slip_id=? ORDER BY id LIMIT 1""",
            (slip_id,),
        ).fetchone()
        if row:
            return row_to_dict(row)
        row = conn.execute(
            """SELECT id, document_no AS invoice_no, status, gate_pass_id, 'purchase' AS kind,
                      'primary' AS link_role
               FROM purchase_invoices WHERE weight_slip_id=? ORDER BY id LIMIT 1""",
            (slip_id,),
        ).fetchone()
        if row:
            return row_to_dict(row)
    return None


def list_weight_slip_invoice_attachments(slip_id):
    """All invoices that reference this slip (primary first, then reference-only)."""
    from database import get_connection, rows_to_list

    primary = get_weight_slip_invoice_attachment(slip_id)
    primary_key = (primary["kind"], int(primary["id"])) if primary else None
    out = []
    with get_connection() as conn:
        for kind, table in (("sales", "sales_invoices"), ("purchase", "purchase_invoices")):
            for row in rows_to_list(conn.execute(
                f"""SELECT id, document_no AS invoice_no, status, gate_pass_id, ? AS kind
                    FROM {table} WHERE weight_slip_id=? ORDER BY id""",
                (kind, slip_id),
            )):
                role = "primary" if primary_key == (kind, int(row["id"])) else "reference"
                row["link_role"] = role
                out.append(row)
    # Ensure primary is first
    out.sort(key=lambda r: (0 if r.get("link_role") == "primary" else 1, r.get("id") or 0))
    return out


def detach_weight_slip_from_invoice(slip_id, user_id=None, invoice_id=None, kind=None):
    """Remove slip from a **draft** invoice. If primary is detached, promote another link or clear."""
    from database import get_connection
    from db_invoice_workflow import refresh_invoice_weight_match

    attachments = list_weight_slip_invoice_attachments(slip_id)
    if not attachments:
        raise ValueError("This weight slip is not attached to an invoice.")

    if invoice_id and kind:
        att = next(
            (a for a in attachments if int(a["id"]) == int(invoice_id) and a["kind"] == kind),
            None,
        )
        if not att:
            raise ValueError("That invoice is not linked to this weight slip.")
    else:
        att = get_weight_slip_invoice_attachment(slip_id) or attachments[0]

    status = (att.get("status") or "draft").lower()
    if status != "draft":
        if status == "approved":
            raise ValueError(
                f"Invoice **{att.get('invoice_no')}** is **approved**. "
                "Administrator must **unapprove** the invoice first (Sales/Purchase → Edit / Delete), "
                "then detach the slip here, correct it, re-attach on the invoice, save, and submit for approval again."
            )
        if status == "pending_approval":
            raise ValueError(
                f"Invoice **{att.get('invoice_no')}** is **pending approval**. "
                "Reject it from **Sale/Purchase Approval** first. If it was already approved, use **Unapprove** instead."
            )
        raise ValueError(
            f"Invoice **{att.get('invoice_no')}** is **{status}**. "
            "Detach is only allowed when the invoice is **draft** (e.g. after admin unapprove)."
        )
    kind = att["kind"]
    inv_id = att["id"]
    was_primary = att.get("link_role") == "primary"
    inv_table = "sales_invoices" if kind == "sales" else "purchase_invoices"
    gp_col = "sales_invoice_id" if kind == "sales" else "purchase_invoice_id"
    with get_connection() as conn:
        conn.execute(f"UPDATE {inv_table} SET weight_slip_id=NULL WHERE id=?", (inv_id,))
        conn.execute(
            f"UPDATE gate_passes SET weight_slip_id=NULL WHERE weight_slip_id=? AND {gp_col}=?",
            (slip_id, inv_id),
        )
        if was_primary:
            nxt = conn.execute(
                """SELECT id, kind FROM (
                     SELECT id, 'sales' AS kind FROM sales_invoices WHERE weight_slip_id=?
                     UNION ALL
                     SELECT id, 'purchase' AS kind FROM purchase_invoices WHERE weight_slip_id=?
                   ) ORDER BY id LIMIT 1""",
                (slip_id, slip_id),
            ).fetchone()
            if nxt:
                nkind = nxt["kind"]
                nid = int(nxt["id"])
                nref = "sales_invoice" if nkind == "sales" else "purchase_invoice"
                conn.execute(
                    """UPDATE weight_slips SET reference_type=?, reference_id=?,
                       modified_by=?, modified_at=? WHERE id=?""",
                    (nref, nid, user_id, now(), slip_id),
                )
                refresh_invoice_weight_match(conn, nid, nkind)
            else:
                conn.execute(
                    """UPDATE weight_slips SET reference_type=NULL, reference_id=NULL,
                       weight_difference=0, modified_by=?, modified_at=? WHERE id=?""",
                    (user_id, now(), slip_id),
                )
        refresh_invoice_weight_match(conn, inv_id, kind)
    try:
        from db_audit import log_event
        log_event(
            "weight_slips", slip_id, "detach_invoice", user_id=user_id, module="Weight Scale",
            document_no=att.get("invoice_no"),
            summary=f"Detached slip from {kind} invoice {att.get('invoice_no')} ({att.get('link_role')})",
        )
    except Exception:
        pass
    return att


def backfill_slip_items_from_linked_invoices(user_id=None):
    """Set slip product/party from linked sales or purchase invoices (fixes older links)."""
    from database import get_connection
    seen = set()
    n = 0
    with get_connection() as conn:
        pairs = []
        for row in conn.execute(
            """SELECT ws.id, ws.reference_type, ws.reference_id
               FROM weight_slips ws
               WHERE ws.reference_type IN ('sales_invoice','purchase_invoice')
                 AND ws.reference_id IS NOT NULL"""
        ).fetchall():
            pairs.append((row["id"], row["reference_type"], int(row["reference_id"])))
        for row in conn.execute(
            "SELECT ws.id, si.id FROM weight_slips ws JOIN sales_invoices si ON si.weight_slip_id=ws.id"
        ).fetchall():
            pairs.append((row["id"], "sales_invoice", int(row[1])))
        for row in conn.execute(
            "SELECT ws.id, pi.id FROM weight_slips ws JOIN purchase_invoices pi ON pi.weight_slip_id=ws.id"
        ).fetchall():
            pairs.append((row["id"], "purchase_invoice", int(row[1])))
    for slip_id, ref_type, ref_id in pairs:
        key = (slip_id, ref_type, ref_id)
        if key in seen:
            continue
        seen.add(key)
        try:
            link_weight_slip_to_invoice(slip_id, ref_type, ref_id, user_id)
            n += 1
        except Exception:
            pass
    return n


def get_invoice_weight_info(invoice_id, kind="sales"):
    from database import get_connection, row_to_dict
    from db_invoice_workflow import _is_primary_weight_slip_for_invoice

    inv_table = "sales_invoices" if kind == "sales" else "purchase_invoices"
    with get_connection() as conn:
        inv = row_to_dict(conn.execute(f"SELECT * FROM {inv_table} WHERE id=?", (invoice_id,)).fetchone())
        if not inv:
            return {}
        inv_wt = float(inv.get("total_net_weight") or invoice_lines_net_weight(conn, invoice_id, kind))
        slip_id = inv.get("weight_slip_id")
        physical = variance = slip_no = None
        match_status = inv.get("weight_match_status")
        if slip_id:
            ws = row_to_dict(conn.execute(
                "SELECT document_no, net_weight FROM weight_slips WHERE id=?", (slip_id,)
            ).fetchone())
            if ws:
                slip_no = ws.get("document_no")
            # Reference-only: show slip number, no physical/variance vs full slip net
            if not _is_primary_weight_slip_for_invoice(conn, slip_id, invoice_id, kind):
                return {
                    "invoice_weight_kg": inv_wt,
                    "physical_weight_kg": 0.0,
                    "weight_variance_kg": 0.0,
                    "weight_variance_pct": 0.0,
                    "weight_match_status": "reference",
                    "weight_slip_id": slip_id,
                    "weight_slip_no": slip_no,
                    "link_role": "reference",
                }
            if ws:
                physical = float(ws.get("net_weight") or 0)
        if float(inv.get("physical_weight_kg") or 0) > 0:
            physical = float(inv["physical_weight_kg"])
        if physical is not None:
            variance = round(physical - inv_wt, 3)
        elif inv_wt:
            variance = 0.0
        return {
            "invoice_weight_kg": inv_wt,
            "physical_weight_kg": physical,
            "weight_variance_kg": variance,
            "weight_variance_pct": float(inv.get("weight_variance_pct") or 0),
            "weight_match_status": match_status,
            "weight_slip_id": slip_id,
            "weight_slip_no": slip_no,
            "link_role": "primary" if slip_id else None,
        }


def _apply_tax_v2(conn):
    for t, col, ddl in [
        ("sales_invoices", "fed_tax", "REAL DEFAULT 0"),
        ("sales_invoices", "taxable_amount", "REAL DEFAULT 0"),
        ("purchase_invoices", "fed_tax", "REAL DEFAULT 0"),
        ("purchase_invoices", "taxable_amount", "REAL DEFAULT 0"),
    ]:
        _add_col(conn, t, col, ddl)
    admin = conn.execute("SELECT id FROM users WHERE username='admin'").fetchone()
    if not admin:
        return
    aid = admin[0]
    groups = {r["group_type"]: r["id"] for r in conn.execute("SELECT id, group_type FROM account_groups").fetchall()}
    for code, name, gtype in [("1215", "WHT Receivable", "asset"), ("2115", "WHT Payable", "liability")]:
        if not conn.execute("SELECT 1 FROM chart_of_accounts WHERE code=?", (code,)).fetchone():
            conn.execute(
                "INSERT INTO chart_of_accounts(code,name,account_group_id,created_by) VALUES(?,?,?,?)",
                (code, name, groups.get(gtype, list(groups.values())[0]), aid),
            )


# Re-export unified tax engine (single source of truth)
from tax_engine import (  # noqa: E402
    calc_line,
    calc_line_tax_dict,
    compute_document_totals as compute_invoice_totals,
    apply_invoice_totals_to_data,
    enrich_lines,
    validate_pct,
)


def calc_line_tax(subtotal, tax_rate_row, tax_inclusive=False):
    """Legacy dict API used by UI helpers."""
    return calc_line_tax_dict(subtotal, tax_rate_row, tax_inclusive)


# ---------- Weighbridge ----------
_WS_SALES_INV_JOIN = """LEFT JOIN sales_invoices si ON (
    si.weight_slip_id = ws.id
    OR (ws.reference_type = 'sales_invoice' AND ws.reference_id = si.id)
)"""
_WS_PURCHASE_INV_JOIN = """LEFT JOIN purchase_invoices pi ON (
    pi.weight_slip_id = ws.id
    OR (ws.reference_type = 'purchase_invoice' AND ws.reference_id = pi.id)
)"""


def weight_slip_is_linked(row):
    """True if slip is tied to a sales or purchase invoice (either direction)."""
    if not row:
        return False
    if row.get("sales_invoice_no") or row.get("purchase_invoice_no"):
        return True
    if row.get("reference_type") in ("sales_invoice", "purchase_invoice") and row.get("reference_id"):
        return True
    return False


def weight_slip_is_imported(slip_or_remarks) -> bool:
    """True for slips loaded from Access / modern_weight_scale (not created in IFS weighbridge)."""
    if isinstance(slip_or_remarks, dict):
        remarks = str(slip_or_remarks.get("remarks") or "")
    else:
        remarks = str(slip_or_remarks or "")
    text = remarks.strip()
    if not text:
        return False
    if "imported from" in text.lower():
        return True
    # modern_weight_scale import stamps: "Dept: … | Type: SALE/PURCHASE"
    if text.startswith("Dept:") and "Type:" in text:
        return True
    return False


# SQL fragment: exclude historical imports from invoice slip pickers
_WS_EXCLUDE_IMPORTED_SQL = """
              AND LOWER(COALESCE(ws.remarks, '')) NOT LIKE '%imported from%'
              AND NOT (
                    COALESCE(ws.remarks, '') LIKE 'Dept:%'
                AND COALESCE(ws.remarks, '') LIKE '%Type:%'
              )
"""


def get_unlinked_slips_for_party(party_type, party_id, product_id=None, include_slip_id=None):
    """
    Completed slips for one customer/supplier, newest first, not yet primary-linked.
    Imported slips (Access / modern_weight_scale) are hidden — only IFS weighbridge slips.
    include_slip_id: always include this slip (e.g. already on invoice being edited).
    """
    from database import get_connection, rows_to_list

    if party_type not in ("customer", "supplier") or not party_id:
        return []
    col = "customer_id" if party_type == "customer" else "supplier_id"
    # Primary = slip.reference_* set OR any invoice already owns weight_slip_id as sole link.
    # Free for new primary: no reference and no invoice.weight_slip_id.
    q = f"""SELECT ws.*, c.name AS customer_name, c.code AS customer_code,
                   s.name AS supplier_name, s.code AS supplier_code, p.name AS product_name,
                   si.document_no AS sales_invoice_no, pi.document_no AS purchase_invoice_no
            FROM weight_slips ws
            LEFT JOIN customers c ON ws.customer_id=c.id
            LEFT JOIN suppliers s ON ws.supplier_id=s.id
            LEFT JOIN products p ON ws.product_id=p.id
            {_WS_SALES_INV_JOIN}
            {_WS_PURCHASE_INV_JOIN}
            WHERE ws.status='completed'
              AND COALESCE(ws.net_weight, 0) > 0
              AND ws.{col}=?
              AND NOT EXISTS (SELECT 1 FROM sales_invoices x WHERE x.weight_slip_id=ws.id)
              AND NOT EXISTS (SELECT 1 FROM purchase_invoices x WHERE x.weight_slip_id=ws.id)
              AND (ws.reference_type IS NULL OR ws.reference_id IS NULL)
              {_WS_EXCLUDE_IMPORTED_SQL}"""
    p = [party_id]
    if product_id:
        q += " AND ws.product_id=?"
        p.append(product_id)
    q += " ORDER BY ws.slip_date DESC, COALESCE(ws.second_weight_time, ws.first_weight_time) DESC, ws.id DESC"
    with get_connection() as conn:
        rows = rows_to_list(conn.execute(q, p).fetchall())
    if include_slip_id and not any(r["id"] == include_slip_id for r in rows):
        extra = get_weight_slip_pro(include_slip_id)
        if extra:
            rows = [extra] + rows
    return rows


def get_referenceable_slips(party_type=None, party_id=None, include_slip_id=None):
    """Completed slips that already have a primary invoice — for reference-only attach.

    Any party may reference the same vehicle slip (multi-customer trip).
    """
    from database import get_connection, rows_to_list

    q = f"""SELECT ws.*, c.name AS customer_name, s.name AS supplier_name, p.name AS product_name,
                   si.document_no AS sales_invoice_no, pi.document_no AS purchase_invoice_no
            FROM weight_slips ws
            LEFT JOIN customers c ON ws.customer_id=c.id
            LEFT JOIN suppliers s ON ws.supplier_id=s.id
            LEFT JOIN products p ON ws.product_id=p.id
            {_WS_SALES_INV_JOIN}
            {_WS_PURCHASE_INV_JOIN}
            WHERE ws.status='completed'
              AND COALESCE(ws.net_weight, 0) > 0
              AND (
                    (ws.reference_type IN ('sales_invoice','purchase_invoice') AND ws.reference_id IS NOT NULL)
                 OR EXISTS (SELECT 1 FROM sales_invoices x WHERE x.weight_slip_id=ws.id)
                 OR EXISTS (SELECT 1 FROM purchase_invoices x WHERE x.weight_slip_id=ws.id)
              )
              {_WS_EXCLUDE_IMPORTED_SQL}"""
    p = []
    q += " ORDER BY ws.slip_date DESC, ws.id DESC LIMIT 200"
    with get_connection() as conn:
        rows = rows_to_list(conn.execute(q, p).fetchall())
    if include_slip_id and not any(r["id"] == include_slip_id for r in rows):
        extra = get_weight_slip_pro(include_slip_id)
        if extra:
            rows = [extra] + rows
    return rows


def get_latest_unlinked_slip_for_party(party_type, party_id, product_id=None):
    slips = get_unlinked_slips_for_party(party_type, party_id, product_id=product_id)
    return slips[0] if slips else None


def get_linkable_sales_invoices(customer_id=None, slip_id=None):
    """Draft/rejected sales invoices open for weighbridge linking."""
    from database import get_connection, rows_to_list
    q = """SELECT s.id, s.document_no AS invoice_no, s.invoice_date AS sale_date,
                  s.customer_id, c.name AS customer_name, s.weight_slip_id, s.status
           FROM sales_invoices s JOIN customers c ON s.customer_id=c.id
           WHERE COALESCE(s.status,'draft') IN ('draft','rejected')
             AND (s.weight_slip_id IS NULL OR s.weight_slip_id=?)"""
    p = [slip_id or 0]
    if customer_id:
        q += " AND s.customer_id=?"
        p.append(customer_id)
    q += " ORDER BY s.invoice_date DESC, s.id DESC LIMIT 100"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


def get_linkable_purchase_invoices(supplier_id=None, slip_id=None):
    """Draft/rejected purchase invoices open for weighbridge linking."""
    from database import get_connection, rows_to_list
    q = """SELECT p.id, p.document_no AS invoice_no, p.invoice_date AS purchase_date,
                  p.supplier_id, s.name AS supplier_name, p.weight_slip_id, p.status
           FROM purchase_invoices p JOIN suppliers s ON p.supplier_id=s.id
           WHERE COALESCE(p.status,'draft') IN ('draft','rejected')
             AND (p.weight_slip_id IS NULL OR p.weight_slip_id=?)"""
    p = [slip_id or 0]
    if supplier_id:
        q += " AND p.supplier_id=?"
        p.append(supplier_id)
    q += " ORDER BY p.invoice_date DESC, p.id DESC LIMIT 100"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


def create_draft_invoice_from_weight_slip(slip_id, user_id=None, product_id=None):
    """
    Weigh-first workflow: create a draft sales/purchase invoice from a completed slip
    and link the slip in one step (fixes invoice↔slip deadlock).
    """
    from datetime import date
    from database import get_tax_rates, peek_invoice, save_purchase, save_sale

    slip = get_weight_slip_pro(slip_id)
    if not slip:
        raise ValueError("Weight slip not found.")
    if slip.get("status") != "completed":
        raise ValueError("Complete second weight before creating an invoice.")
    if weight_slip_is_linked(slip):
        raise ValueError("This slip is already linked to an invoice.")
    net = float(slip.get("net_weight") or 0)
    if net <= 0:
        raise ValueError("Slip has no net weight.")

    pid = product_id or slip.get("product_id")
    if not pid:
        raise ValueError("No item on slip — set item on the weight slip or pick one when creating the invoice.")

    is_sale = bool(slip.get("customer_id")) or slip.get("party_type") == "customer"
    from db_v3 import default_tax_rate_id
    default_tax = default_tax_rate_id()
    inv_date = str(slip.get("slip_date") or date.today())
    notes = f"From weight slip {slip.get('document_no', '')}"

    from database import get_connection, row_to_dict
    with get_connection() as conn:
        prod = row_to_dict(conn.execute(
            "SELECT id, code, name, sale_price, purchase_price, standard_weight FROM products WHERE id=?",
            (int(pid),),
        ).fetchone())
    if not prod:
        raise ValueError("Product on slip not found.")

    from product_rates_legacy import resolve_product_rate

    if is_sale:
        if not slip.get("customer_id"):
            raise ValueError("Slip has no customer — edit the slip and set customer/party.")
        rate, _ = resolve_product_rate(prod, kind="sale", party_id=int(slip["customer_id"]))
        qty = 1.0
        header = {
            "invoice_no": peek_invoice("SAL", "sales_invoices"),
            "customer_id": slip["customer_id"],
            "sale_date": inv_date,
            "payment_mode": "credit",
            "paid_amount": 0,
            "notes": notes,
            "tax_rate_id": default_tax,
            "discount_pct": 0,
            "weighbridge_required": 1,
            "weight_slip_id": slip_id,
        }
        lines = [{
            "item_id": int(pid), "quantity": qty, "rate": float(rate),
            "amount": round(qty * float(rate), 2), "net_weight": net,
        }]
        return save_sale(header, lines, user_id=user_id)

    if not slip.get("supplier_id"):
        raise ValueError("Slip has no supplier — edit the slip and set supplier/party.")
    rate, _ = resolve_product_rate(prod, kind="purchase", party_id=int(slip["supplier_id"]))
    qty = 1.0
    header = {
        "invoice_no": peek_invoice("PUR", "purchase_invoices"),
        "supplier_id": slip["supplier_id"],
        "purchase_date": inv_date,
        "payment_mode": "credit",
        "paid_amount": 0,
        "notes": notes,
        "tax_rate_id": default_tax,
        "discount_pct": 0,
        "weighbridge_required": 1,
        "weight_slip_id": slip_id,
    }
    lines = [{
        "item_id": int(pid), "quantity": qty, "rate": float(rate),
        "amount": round(qty * float(rate), 2), "net_weight": net,
    }]
    return save_purchase(header, lines, user_id=user_id)


def create_multi_dispatch_sales(
    *,
    customer_id,
    weight_slip_id,
    invoice_date,
    dispatches,
    user_id=None,
    payment_mode="credit",
    paid_amount=0,
    tax_rate_id=None,
    discount_pct=0,
    allow_weight_short=False,
    allow_weight_over=False,
    weight_tolerance_kg=1.0,
):
    """
    One party + one completed weight slip → many draft sales invoices + gate passes.

    Each dispatch: {town, notes?, order_id?, lines: [{item_id, quantity, rate, net_weight, ...}]}
    Optional order_id links that invoice to a sales order (delivery qty updates on save).
    First invoice claims the slip as primary; others attach as reference.
    Allocated kg across dispatches should equal slip net (within tolerance).
    """
    from datetime import date as _date
    from database import peek_invoice, save_sale, get_connection, row_to_dict
    from db_v3 import default_tax_rate_id
    from db_invoice_workflow import generate_gate_pass_from_sale

    if not customer_id:
        raise ValueError("Customer is required.")
    if not weight_slip_id:
        raise ValueError("Weight slip is required.")
    if not dispatches or len(dispatches) < 1:
        raise ValueError("Add at least one dispatch town / invoice.")

    slip = get_weight_slip_pro(weight_slip_id)
    if not slip:
        raise ValueError("Weight slip not found.")
    if slip.get("status") != "completed":
        raise ValueError("Complete second weight before creating invoices.")
    slip_net = float(slip.get("net_weight") or 0)
    if slip_net <= 0:
        raise ValueError("Slip has no net weight.")

    # Party check — allow UNKNOWN? Prefer matching customer or slip customer
    slip_cid = slip.get("customer_id")
    if slip_cid and int(slip_cid) != int(customer_id):
        raise ValueError(
            "Selected customer does not match the weight slip party. "
            "Use the same customer as on the slip, or edit the slip first."
        )

    cleaned = []
    allocated = 0.0
    for i, d in enumerate(dispatches):
        town = (d.get("town") or "").strip()
        if not town:
            raise ValueError(f"Dispatch #{i + 1}: enter a dispatch town / destination.")
        lines = [ln for ln in (d.get("lines") or []) if ln.get("item_id") or ln.get("product_id")]
        if not lines:
            raise ValueError(f"Dispatch **{town}**: add at least one line item.")
        norm_lines = []
        inv_wt = 0.0
        for ln in lines:
            pid = int(ln.get("item_id") or ln.get("product_id"))
            qty = float(ln.get("quantity") or 0)
            rate = float(ln.get("rate") or 0)
            nw = float(ln.get("net_weight") or 0)
            if qty <= 0:
                raise ValueError(f"Dispatch **{town}**: quantity must be greater than zero.")
            if nw <= 0:
                raise ValueError(f"Dispatch **{town}**: enter net weight (kg) on each line.")
            inv_wt += nw
            norm_lines.append({
                "item_id": pid,
                "quantity": qty,
                "rate": rate,
                "amount": round(qty * rate, 2),
                "line_amount": round(qty * rate, 2),
                "net_weight": nw,
                "tax_amount": float(ln.get("tax_amount") or 0),
                "line_discount": float(ln.get("line_discount") or 0),
            })
        allocated += inv_wt
        cleaned.append({
            "town": town,
            "notes": (d.get("notes") or "").strip(),
            "lines": norm_lines,
            "inv_wt": inv_wt,
            "order_id": int(d["order_id"]) if d.get("order_id") else None,
        })

    # One SO may only attach to one invoice in this batch
    so_seen = {}
    for d in cleaned:
        oid = d.get("order_id")
        if not oid:
            continue
        if oid in so_seen:
            raise ValueError(
                f"Sales order is linked to both **{so_seen[oid]}** and **{d['town']}**. "
                "Use a different SO per town, or leave SO blank on one invoice."
            )
        so_seen[oid] = d["town"]
        order = None
        try:
            from db_v3 import get_sales_order
            order = get_sales_order(oid)
        except Exception:
            order = None
        if not order:
            raise ValueError(f"Sales order not found for dispatch **{d['town']}**.")
        if int(order.get("customer_id") or 0) != int(customer_id):
            raise ValueError(
                f"Sales order **{order.get('document_no')}** belongs to another customer."
            )
        st_ok = (order.get("status") or "open").lower()
        if st_ok in ("closed", "cancelled", "canceled"):
            raise ValueError(
                f"Sales order **{order.get('document_no')}** is **{st_ok}** — cannot attach."
            )
        d["order_no"] = order.get("document_no")

    tol = float(weight_tolerance_kg or 0)
    short = slip_net - allocated
    over = allocated - slip_net
    if over > tol + 1e-9 and not allow_weight_over:
        raise ValueError(
            f"Allocated weight **{allocated:,.3f} kg** exceeds slip net **{slip_net:,.3f} kg** "
            f"by **{over:,.3f} kg**. Reduce town weights, or tick allow over."
        )
    if short > tol + 1e-9 and not allow_weight_short:
        raise ValueError(
            f"Allocated **{allocated:,.3f} kg** is short of slip net **{slip_net:,.3f} kg** "
            f"by **{short:,.3f} kg**. Tick allow short, or adjust town weights."
        )

    if tax_rate_id is None:
        tax_rate_id = default_tax_rate_id()
    inv_date = str(invoice_date or slip.get("slip_date") or _date.today())
    claim_primary_first = not weight_slip_is_linked(slip)

    created = []
    for i, d in enumerate(cleaned):
        town = d["town"]
        note_parts = [f"Dispatch To: {town}"]
        if d.get("order_no"):
            note_parts.append(f"From sales order {d['order_no']}")
        if d["notes"]:
            note_parts.append(d["notes"])
        note_parts.append(f"Multi-dispatch from slip {slip.get('document_no') or weight_slip_id}")
        header = {
            "invoice_no": peek_invoice("SAL", "sales_invoices"),
            "customer_id": int(customer_id),
            "sale_date": inv_date,
            "payment_mode": payment_mode or "credit",
            "paid_amount": float(paid_amount or 0) if i == 0 else 0,
            "notes": "\n".join(note_parts),
            "tax_rate_id": tax_rate_id,
            "discount_pct": float(discount_pct or 0),
            "weighbridge_required": 1,
            "weight_slip_id": int(weight_slip_id),
            "weight_slip_as_primary": (i == 0 and claim_primary_first),
            "dispatch_remarks": f"Dispatch To: {town}",
            "order_id": d.get("order_id"),
        }
        sid = save_sale(header, d["lines"], user_id=user_id)
        created.append({
            "invoice_id": sid,
            "town": town,
            "net_weight": d["inv_wt"],
            "is_primary": bool(i == 0 and claim_primary_first),
            "order_no": d.get("order_no"),
            "order_id": d.get("order_id"),
        })

    # Align physical kg to each invoice's allocated share (variance 0 on split load)
    with get_connection() as conn:
        for row in created:
            inv_wt = float(row["net_weight"] or 0)
            conn.execute(
                """UPDATE sales_invoices
                   SET total_net_weight=?, physical_weight_kg=?, weight_variance_kg=0,
                       weight_variance_pct=0, weight_match_status=?
                   WHERE id=?""",
                (
                    inv_wt,
                    inv_wt,
                    "matched" if row.get("is_primary") else "reference",
                    row["invoice_id"],
                ),
            )
            inv = row_to_dict(conn.execute(
                "SELECT document_no FROM sales_invoices WHERE id=?", (row["invoice_id"],),
            ).fetchone())
            row["invoice_no"] = inv.get("document_no") if inv else None

    # Regenerate GPs so weight/remarks pick up allocated kg + town
    for row in created:
        try:
            generate_gate_pass_from_sale(row["invoice_id"], user_id, require_approved=False)
            with get_connection() as conn:
                gp = row_to_dict(conn.execute(
                    "SELECT document_no FROM gate_passes WHERE sales_invoice_id=? ORDER BY id DESC LIMIT 1",
                    (row["invoice_id"],),
                ).fetchone())
            row["gate_pass_no"] = gp.get("document_no") if gp else None
        except Exception:
            row["gate_pass_no"] = None

    return {
        "weight_slip_id": int(weight_slip_id),
        "slip_no": slip.get("document_no"),
        "slip_net": slip_net,
        "allocated": allocated,
        "invoices": created,
    }


def save_weight_slip_pro(data, slip_id=None, user_id=None):
    from database import get_connection, ensure_document_no
    ts = now()
    gross = float(data.get("gross_weight") or data.get("first_weight") or 0)
    tare = float(data.get("tare_weight") or data.get("second_weight") or 0)
    first_w = float(data.get("first_weight") if data.get("first_weight") is not None else gross)
    second_w = float(data.get("second_weight") if data.get("second_weight") is not None else tare)
    if data.get("net_weight") is not None:
        net = round(float(data["net_weight"]), 3)
    else:
        net = round(gross - tare, 3)
    ref_type = data.get("reference_type")
    ref_id = data.get("reference_id")
    if data.get("sales_invoice_id"):
        ref_type, ref_id = "sales_invoice", data["sales_invoice_id"]
    elif data.get("purchase_invoice_id"):
        ref_type, ref_id = "purchase_invoice", data["purchase_invoice_id"]
    diff = float(data.get("weight_difference") or 0)
    with get_connection() as conn:
        if ref_type and ref_id:
            kind = "sales" if ref_type == "sales_invoice" else "purchase"
            inv_wt = invoice_lines_net_weight(conn, ref_id, kind)
            diff = round(net - inv_wt, 3)
        fields = (
            data.get("slip_date", ts[:10]), data.get("slip_time", ts[11:19]),
            data.get("vehicle_id"), data.get("vehicle_no"), data.get("driver_name"),
            data.get("customer_id"), data.get("supplier_id"), data.get("product_id"),
            data.get("party_type"), first_w, second_w, tare, gross, net, diff,
            data.get("first_weight_time"), data.get("second_weight_time"),
            data.get("print_time"), data.get("save_time", ts),
            data.get("remarks"), ref_type, ref_id,
            data.get("status") or ("completed" if second_w > 0 else "first_weigh"),
        )
        if slip_id:
            conn.execute(
                """UPDATE weight_slips SET slip_date=?,slip_time=?,vehicle_id=?,vehicle_no=?,driver_name=?,
                   customer_id=?,supplier_id=?,product_id=?,party_type=?,first_weight=?,second_weight=?,
                   tare_weight=?,gross_weight=?,net_weight=?,weight_difference=?,
                   first_weight_time=?,second_weight_time=?,print_time=?,save_time=?,remarks=?,
                   reference_type=?,reference_id=?,status=?,modified_by=?,modified_at=? WHERE id=?""",
                (*fields, user_id, ts, slip_id),
            )
        else:
            cur = conn.execute(
                """INSERT INTO weight_slips(document_no,slip_date,slip_time,vehicle_id,vehicle_no,driver_name,
                   customer_id,supplier_id,product_id,party_type,first_weight,second_weight,tare_weight,
                   gross_weight,net_weight,weight_difference,first_weight_time,second_weight_time,
                   print_time,save_time,remarks,reference_type,reference_id,status,created_by)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (ensure_document_no("WS", data.get("document_no"), conn), *fields, user_id),
            )
            slip_id = cur.lastrowid
        return slip_id


def get_weight_slip_pro(sid):
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        return row_to_dict(conn.execute(
            f"""SELECT ws.*, v.registration_no,
                       c.name AS customer_name, c.code AS customer_code,
                       s.name AS supplier_name, s.code AS supplier_code, p.name AS product_name,
                       si.document_no AS sales_invoice_no, pi.document_no AS purchase_invoice_no
               FROM weight_slips ws
               LEFT JOIN vehicles v ON ws.vehicle_id=v.id
               LEFT JOIN customers c ON ws.customer_id=c.id
               LEFT JOIN suppliers s ON ws.supplier_id=s.id
               LEFT JOIN products p ON ws.product_id=p.id
               {_WS_SALES_INV_JOIN}
               {_WS_PURCHASE_INV_JOIN}
               WHERE ws.id=?""", (sid,)).fetchone())


def get_weight_slips_pro(from_date=None, to_date=None, customer_id=None, supplier_id=None, product_id=None):
    from database import get_connection, rows_to_list
    q = f"""SELECT ws.*, v.registration_no,
                  c.name AS customer_name, c.code AS customer_code,
                  s.name AS supplier_name, s.code AS supplier_code, p.name AS product_name,
                  si.document_no AS sales_invoice_no, pi.document_no AS purchase_invoice_no
           FROM weight_slips ws
           LEFT JOIN vehicles v ON ws.vehicle_id=v.id
           LEFT JOIN customers c ON ws.customer_id=c.id
           LEFT JOIN suppliers s ON ws.supplier_id=s.id
           LEFT JOIN products p ON ws.product_id=p.id
           {_WS_SALES_INV_JOIN}
           {_WS_PURCHASE_INV_JOIN}
           WHERE 1=1"""
    p = []
    if from_date:
        q += " AND ws.slip_date>=?"; p.append(from_date)
    if to_date:
        q += " AND ws.slip_date<=?"; p.append(to_date)
    if customer_id:
        q += " AND ws.customer_id=?"; p.append(customer_id)
    if supplier_id:
        q += " AND ws.supplier_id=?"; p.append(supplier_id)
    if product_id:
        q += " AND ws.product_id=?"; p.append(product_id)
    q += " ORDER BY ws.slip_date DESC, ws.id DESC"
    with get_connection() as conn:
        return rows_to_list(conn.execute(q, p).fetchall())


def weight_slip_print_html(slip_id, operator_name=None):
    from erp_ui.report_print import get_company_info, PRINT_CSS_PORTRAIT_HALF, _now_str
    from db_commercial import slip_transaction_type
    s = get_weight_slip_pro(slip_id)
    if not s:
        return ""
    co = get_company_info()
    party = s.get("customer_name") or s.get("supplier_name") or "—"
    party_code = (s.get("customer_code") or s.get("supplier_code") or "").strip()
    if party_code and party != "—":
        party = f"{party_code} - {party}"
    inv_ref = s.get("sales_invoice_no") or s.get("purchase_invoice_no") or ""
    tx_type = slip_transaction_type(s)
    status = "COMPLETED" if s.get("status") == "completed" else (
        "PENDING" if s.get("status") == "first_weigh" else (s.get("status") or "").upper()
    )
    if inv_ref:
        status = f"COMPLETED — Linked {inv_ref}"
    elif status == "COMPLETED":
        status = "COMPLETED — Waiting for Invoice"

    first_w = float(s.get("first_weight") or 0)
    second_w = float(s.get("second_weight") or 0)
    first_t = s.get("first_weight_time") or s.get("slip_time") or ""
    second_t = s.get("second_weight_time") or ""
    is_first_only = s.get("status") == "first_weigh"
    print_time = s.get("print_time") or _now_str()

    def fmt_kg(v):
        if v is None or (isinstance(v, str) and v in ("—", "")):
            return "—"
        return f"{v:,.0f}" if float(v) == int(float(v)) else f"{v:,.2f}"

    if is_first_only:
        gross_w, tare_w, gross_t, tare_t = first_w, None, first_t, "—"
        net_w = "—"
        title = "FIRST WEIGHT SLIP"
        status = "1ST WEIGH — AWAITING 2ND WEIGHT"
        if inv_ref:
            status = f"1ST WEIGH — Bill {inv_ref}"
    else:
        if first_w >= second_w:
            gross_w, tare_w, gross_t, tare_t = first_w, second_w, first_t, second_t
        else:
            gross_w, tare_w, gross_t, tare_t = second_w, first_w, second_t, first_t
        net_w = round(abs(float(gross_w) - float(tare_w)), 3)
        title = "WEIGHT SLIP"
        if inv_ref:
            status = f"COMPLETED — Linked {inv_ref}"
        elif status == "COMPLETED":
            status = "COMPLETED — Waiting for Invoice"

    addr = co.get("address") or ""
    website = co.get("website") or "www.ifschemicals.com"
    operator = operator_name or "—"
    item_lbl = s.get("product_name") or "—"
    if inv_ref:
        item_lbl = f"{item_lbl} (from invoice)" if item_lbl != "—" else f"See invoice {inv_ref}"
    from erp_ui.helpers import fmt_datetime
    from erp_ui.report_print import print_company_header_enabled
    from html import escape as _esc_hdr
    letterhead = ""
    if print_company_header_enabled():
        letterhead = f"""
    <div class="header company-letterhead">
        <h1>{_esc_hdr(co['name'])}</h1>
        <div class="sub">{_esc_hdr(addr)} | {_esc_hdr(website)}</div>
    </div>
    """
    body = f"""
    {letterhead}
    <h2 style="text-align:center;">{title}</h2>
    <table class="data">
    <tr><td><b>Slip No</b></td><td>{s['document_no']}</td><td><b>Date / Time</b></td><td>{fmt_datetime(s.get('slip_date'), s.get('slip_time') or s.get('created_at'))}</td></tr>
    <tr><td><b>Print Time</b></td><td>{print_time}</td><td><b>Status</b></td><td>{status}</td></tr>
    <tr><td><b>Vehicle</b></td><td>{s.get('vehicle_no') or '—'}</td><td><b>Type</b></td><td>{tx_type}</td></tr>
    <tr><td><b>Item</b></td><td colspan="3">{item_lbl}</td></tr>
    </table>
    <div class="party-block">
        <div class="party-label">Party</div>
        <div class="party-name"><b>{party}</b></div>
    </div>
    <table class="data">
    <tr><td><b>Driver</b></td><td>{s.get('driver_name') or '—'}</td><td><b>Driver Mobile</b></td><td>—</td></tr>
    <tr><td><b>Gross Weight</b></td><td>{fmt_kg(gross_w)} KG</td><td><b>Gross Time</b></td><td>{gross_t or '—'}</td></tr>
    <tr><td><b>Tare Weight</b></td><td>{fmt_kg(tare_w)} KG</td><td><b>Tare Time</b></td><td>{tare_t or '—'}</td></tr>
    </table>
    <div class="voucher-amt-box">
        <div class="voucher-amt-label">{"First Weight" if is_first_only else "Net Weight"}</div>
        <div class="voucher-amt-value">{fmt_kg(first_w if is_first_only else net_w)} KG</div>
    </div>
    {"<p style='text-align:center;color:#666;font-size:0.9em'>Return for second weight — net weight will be printed on final slip.</p>" if is_first_only else ""}
    """
    from html import escape as _esc
    from erp_ui.document_print import document_footer_html, document_preparer_user_id, signature_block_html
    if operator and operator != "—":
        body += f'<p class="sig-note">Weighbridge operator: {_esc(str(operator))}</p>'
    body += signature_block_html(doc_label="weight slip")
    footer = document_footer_html(document_preparer_user_id(s))
    return f"""<!DOCTYPE html><html><head><meta charset='utf-8'><title>Weight Slip {s['document_no']}</title>
    {PRINT_CSS_PORTRAIT_HALF}<script>function doPrint(){{window.print();}}</script></head><body>
    <div class="half-page-sheet">{body}
    {footer}</div>
    <div class="half-page-cut no-print">— cut line — bottom half blank —</div>
    <p class="no-print"><button class="print-btn" onclick="doPrint()">Print</button></p>
    </body></html>"""


# ---------- Gate Pass ----------
GATE_PASS_TYPES = [
    ("material_in", "Material In"),
    ("material_out", "Material Out"),
    ("fg_dispatch", "Finished Goods Dispatch"),
]

INVOICE_LINE_ALL = "__all__"


def get_invoice_line_items(invoice_kind, invoice_id):
    """Normalized line items from a sales or purchase invoice."""
    from database import get_sale, get_purchase, get_items
    inv = get_sale(invoice_id) if invoice_kind == "sales" else get_purchase(invoice_id)
    if not inv:
        return []
    code_map = {p["id"]: p.get("code", "") for p in get_items(active_only=False)}
    rows = []
    for i in inv.get("items") or []:
        pid = i.get("item_id") or i.get("product_id")
        rows.append({
            "line_id": i.get("id"),
            "product_id": pid,
            "item_code": code_map.get(pid, ""),
            "item_name": i.get("item_name") or "",
            "quantity": float(i.get("quantity") or 0),
            "net_weight": float(i.get("net_weight") or 0),
            "rate": float(i.get("rate") or 0),
            "amount": float(i.get("amount") or 0),
        })
    return rows


def summarize_invoice_lines(items):
    """Combined bill summary for multi-line invoices."""
    if not items:
        return {"product_id": None, "quantity": 0.0, "material_desc": "", "net_weight": 0.0}
    desc_parts = [f"{i['item_name']} x {i['quantity']:g}" for i in items]
    material = ", ".join(desc_parts)
    if len(desc_parts) > 5:
        material = ", ".join(desc_parts[:5]) + f" … (+{len(items) - 5} more)"
    return {
        "product_id": items[0]["product_id"],
        "quantity": round(sum(i["quantity"] for i in items), 3),
        "material_desc": material,
        "net_weight": round(sum(i["net_weight"] for i in items), 3),
    }


def invoice_line_material_pick(items, pick=INVOICE_LINE_ALL):
    """Resolve product/qty/description from bill line pick token or line index."""
    if not items:
        return {"product_id": None, "quantity": 0.0, "material_desc": "", "net_weight": 0.0}
    if pick == INVOICE_LINE_ALL or pick is None:
        return summarize_invoice_lines(items)
    idx = int(pick)
    ln = items[idx]
    return {
        "product_id": ln["product_id"],
        "quantity": ln["quantity"],
        "material_desc": f"{ln['item_name']} x {ln['quantity']:g}",
        "net_weight": ln["net_weight"],
    }


def get_gate_pass_material_lines(g):
    """Material rows for gate pass print/UI — from linked invoice lines or header fallback."""
    if g.get("sales_invoice_id"):
        items = get_invoice_line_items("sales", g["sales_invoice_id"])
    elif g.get("purchase_invoice_id"):
        items = get_invoice_line_items("purchase", g["purchase_invoice_id"])
    else:
        items = []
    if items:
        return items
    name = g.get("product_name") or g.get("material_desc") or "—"
    if name == "—" and not g.get("quantity"):
        return []
    return [{
        "item_code": "",
        "item_name": name,
        "quantity": float(g.get("quantity") or 0),
        "net_weight": float(g.get("weight") or 0),
    }]


def sale_weighbridge_active(sale) -> bool:
    """True when invoice uses weighbridge / weight slip (not direct / retail without scale)."""
    wb = sale.get("weighbridge_required")
    if wb in (0, False, "0"):
        return bool(sale.get("weight_slip_id"))
    if wb in (1, True, "1"):
        return True
    return bool(sale.get("weight_slip_id"))


def build_gate_pass_sale_remarks(sale, ws=None):
    """Remarks for outbound gate pass — payment/weight lines only when applicable."""
    ws = ws or {}
    parts = [f"Invoice {sale['invoice_no']}"]
    mode = (sale.get("payment_mode") or "credit").lower()
    paid = float(sale.get("paid_amount") or 0)
    if mode == "cash" and paid > 0:
        parts.append(f"Cash paid Rs. {paid:,.2f}")
    if sale_weighbridge_active(sale):
        slip_no = ws.get("document_no") if ws else None
        if slip_no:
            parts.append(f"Slip {slip_no}")
        inv_wt = float(sale.get("total_net_weight") or sale.get("invoice_weight_kg") or 0)
        if (sale.get("weight_match_status") or "") == "reference":
            parts.append(f"Inv wt {inv_wt:,.3f} kg | Slip ref only (no variance)")
        else:
            phys_wt = float(sale.get("physical_weight_kg") or ws.get("net_weight") or 0)
            var_kg = float(sale.get("weight_variance_kg") or round(phys_wt - inv_wt, 3))
            parts.append(
                f"Inv wt {inv_wt:,.3f} kg | Phys {phys_wt:,.3f} kg | Var {var_kg:+,.3f} kg"
            )
    else:
        contact = (sale.get("driver_contact") or "").strip()
        if contact:
            parts.append(f"Driver contact {contact}")
    # Dispatch town / remarks (multi-dispatch or non-WB)
    extra = (sale.get("dispatch_remarks") or "").strip()
    if extra:
        parts.append(extra)
    notes = (sale.get("notes") or "").strip()
    if notes and notes not in parts:
        # Prefer short "Dispatch To: …" fragment if present
        for line in notes.splitlines():
            t = line.strip()
            if t.lower().startswith("dispatch to"):
                if t not in parts:
                    parts.append(t)
                break
    return " | ".join(parts)


def gate_pass_defaults_from_sales_invoice(sales_invoice_id):
    from database import get_connection, get_sale, row_to_dict
    sale = get_sale(sales_invoice_id)
    if not sale:
        return {}
    items = get_invoice_line_items("sales", sales_invoice_id)
    summary = summarize_invoice_lines(items)
    out = {
        "customer_id": sale["customer_id"],
        "party_name": sale["customer_name"],
        "product_id": summary.get("product_id"),
        "quantity": summary.get("quantity"),
        "material_desc": summary.get("material_desc"),
        "sales_invoice_id": sales_invoice_id,
        "weight_slip_id": sale.get("weight_slip_id"),
        "weight": float(sale.get("physical_weight_kg") or summary.get("net_weight") or 0),
        "invoice_line_pick": "__all__",
    }
    from database import get_customer
    cust = get_customer(sale["customer_id"]) if sale.get("customer_id") else None
    if cust and cust.get("phone"):
        out["party_phone"] = cust["phone"]
    # Non-weighbridge invoices store dispatch details on the sale itself
    if sale.get("vehicle_no"):
        out["vehicle_no"] = sale.get("vehicle_no")
    if sale.get("driver_name"):
        out["driver_name"] = sale.get("driver_name")
    if sale.get("driver_contact"):
        out["driver_contact"] = sale.get("driver_contact")
    if sale.get("dispatch_remarks"):
        out["remarks"] = sale.get("dispatch_remarks")
    with get_connection() as conn:
        if sale.get("weight_slip_id"):
            ws = row_to_dict(conn.execute(
                "SELECT vehicle_no, driver_name, net_weight, document_no FROM weight_slips WHERE id=?",
                (sale["weight_slip_id"],),
            ).fetchone())
            if ws:
                out["vehicle_no"] = ws.get("vehicle_no") or out.get("vehicle_no")
                out["driver_name"] = ws.get("driver_name") or out.get("driver_name")
                out["weight"] = float(ws.get("net_weight") or out["weight"])
        inv = row_to_dict(conn.execute(
            "SELECT dn_id FROM sales_invoices WHERE id=?", (sales_invoice_id,)
        ).fetchone())
        if inv and inv.get("dn_id"):
            out["delivery_note_id"] = inv["dn_id"]
            dn = row_to_dict(conn.execute(
                "SELECT driver_name, vehicle_id FROM delivery_notes WHERE id=?", (inv["dn_id"],)
            ).fetchone())
            if dn:
                out["driver_name"] = dn.get("driver_name") or out.get("driver_name")
                if dn.get("vehicle_id"):
                    v = row_to_dict(conn.execute(
                        "SELECT registration_no FROM vehicles WHERE id=?", (dn["vehicle_id"],)
                    ).fetchone())
                    if v:
                        out["vehicle_no"] = v.get("registration_no") or out.get("vehicle_no")
    return out


def gate_pass_defaults_from_purchase_invoice(purchase_invoice_id):
    from database import get_connection, get_purchase, row_to_dict
    purchase = get_purchase(purchase_invoice_id)
    if not purchase:
        return {}
    items = get_invoice_line_items("purchase", purchase_invoice_id)
    summary = summarize_invoice_lines(items)
    out = {
        "supplier_id": purchase["supplier_id"],
        "party_name": purchase["supplier_name"],
        "product_id": summary.get("product_id"),
        "quantity": summary.get("quantity"),
        "material_desc": summary.get("material_desc"),
        "purchase_invoice_id": purchase_invoice_id,
        "invoice_line_pick": "__all__",
    }
    from database import get_supplier
    sup = get_supplier(purchase["supplier_id"]) if purchase.get("supplier_id") else None
    if sup and sup.get("phone"):
        out["party_phone"] = sup["phone"]
    with get_connection() as conn:
        inv = row_to_dict(conn.execute(
            "SELECT grn_id FROM purchase_invoices WHERE id=?", (purchase_invoice_id,)
        ).fetchone())
        if inv and inv.get("grn_id"):
            out["grn_id"] = inv["grn_id"]
            grn = row_to_dict(conn.execute(
                "SELECT weight_slip_id FROM goods_receipt_notes WHERE id=?", (inv["grn_id"],)
            ).fetchone())
            if grn and grn.get("weight_slip_id"):
                ws = row_to_dict(conn.execute(
                    "SELECT vehicle_no, driver_name, net_weight FROM weight_slips WHERE id=?",
                    (grn["weight_slip_id"],),
                ).fetchone())
                if ws:
                    out["vehicle_no"] = ws.get("vehicle_no")
                    out["driver_name"] = ws.get("driver_name")
                    out["weight"] = ws.get("net_weight")
                    out["weight_slip_id"] = grn["weight_slip_id"]
    return out


def save_gate_pass(data, pass_id=None, user_id=None, skip_approval_check=False):
    from database import get_connection, ensure_document_no
    ensure_gate_pass_schema()
    ptype = data["pass_type"]
    if ptype in GATE_PASS_OUTWARD and not data.get("sales_invoice_id"):
        raise ValueError("Outward gate pass must be linked to a Sales Invoice.")
    if ptype in GATE_PASS_INWARD and not data.get("purchase_invoice_id"):
        raise ValueError("Inward gate pass must be linked to a Purchase Invoice.")
    from database import get_connection
    with get_connection() as conn:
        if not skip_approval_check:
            if data.get("sales_invoice_id"):
                inv = conn.execute(
                    "SELECT status FROM sales_invoices WHERE id=?", (data["sales_invoice_id"],)
                ).fetchone()
                if not inv or inv[0] != "approved":
                    raise ValueError("Gate pass requires an approved sales invoice.")
            if data.get("purchase_invoice_id"):
                inv = conn.execute(
                    "SELECT status FROM purchase_invoices WHERE id=?", (data["purchase_invoice_id"],)
                ).fetchone()
                if not inv or inv[0] != "approved":
                    raise ValueError("Gate pass requires an approved purchase invoice.")
        # Same weight slip may appear on multiple gate passes (primary + reference invoices).
    if data.get("sales_invoice_id") and not data.get("customer_id"):
        defaults = gate_pass_defaults_from_sales_invoice(data["sales_invoice_id"])
        data.setdefault("customer_id", defaults.get("customer_id"))
        data.setdefault("party_name", defaults.get("party_name"))
        data.setdefault("delivery_note_id", defaults.get("delivery_note_id"))
        data["supplier_id"] = None
    if data.get("purchase_invoice_id") and not data.get("supplier_id"):
        defaults = gate_pass_defaults_from_purchase_invoice(data["purchase_invoice_id"])
        data.setdefault("supplier_id", defaults.get("supplier_id"))
        data.setdefault("party_name", defaults.get("party_name"))
        data.setdefault("grn_id", defaults.get("grn_id"))
        data["customer_id"] = None
    ts = now()
    created_new = False
    with get_connection() as conn:
        if pass_id:
            conn.execute(
                """UPDATE gate_passes SET pass_type=?,pass_date=?,pass_time=?,vehicle_no=?,driver_name=?,
                   driver_contact=?,
                   party_name=?,customer_id=?,supplier_id=?,product_id=?,material_desc=?,quantity=?,weight=?,
                   sales_invoice_id=?,purchase_invoice_id=?,delivery_note_id=?,grn_id=?,weight_slip_id=?,
                   remarks=?,modified_by=?,modified_at=? WHERE id=?""",
                (data["pass_type"], data["pass_date"], data.get("pass_time", ts[11:19]),
                 data.get("vehicle_no"), data.get("driver_name"), data.get("driver_contact"),
                 data.get("party_name"),
                 data.get("customer_id"), data.get("supplier_id"), data.get("product_id"),
                 data.get("material_desc"), data.get("quantity", 0), data.get("weight", 0),
                 data.get("sales_invoice_id"), data.get("purchase_invoice_id"),
                 data.get("delivery_note_id"), data.get("grn_id"), data.get("weight_slip_id"),
                 data.get("remarks"), user_id, ts, pass_id),
            )
        else:
            cur = conn.execute(
                """INSERT INTO gate_passes(document_no,pass_type,pass_date,pass_time,vehicle_no,driver_name,
                   driver_contact,
                   party_name,customer_id,supplier_id,product_id,material_desc,quantity,weight,
                   sales_invoice_id,purchase_invoice_id,delivery_note_id,grn_id,weight_slip_id,remarks,created_by)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (ensure_document_no("GP", data.get("document_no"), conn), data["pass_type"], data["pass_date"],
                 data.get("pass_time", ts[11:19]), data.get("vehicle_no"), data.get("driver_name"),
                 data.get("driver_contact"),
                 data.get("party_name"), data.get("customer_id"), data.get("supplier_id"),
                 data.get("product_id"), data.get("material_desc"), data.get("quantity", 0),
                 data.get("weight", 0), data.get("sales_invoice_id"), data.get("purchase_invoice_id"),
                 data.get("delivery_note_id"), data.get("grn_id"), data.get("weight_slip_id"),
                 data.get("remarks"), user_id),
            )
            pass_id = cur.lastrowid
            created_new = True
        # Outward gate pass → notify portal customer (with or without sales/portal order)
        if ptype in GATE_PASS_OUTWARD and (
            created_new or data.get("notify_dispatch")
        ):
            try:
                from erp_core.notifications import notify_gate_pass_dispatched
                notify_gate_pass_dispatched(int(pass_id))
            except Exception:
                pass
        return pass_id


def approve_gate_pass(pass_id, user_id):
    from database import get_connection
    with get_connection() as conn:
        conn.execute(
            "UPDATE gate_passes SET status='approved',approved_by=?,approved_at=? WHERE id=?",
            (user_id, now(), pass_id),
        )


def get_gate_passes(pass_type=None, from_date=None, to_date=None, sales_invoice_id=None, purchase_invoice_id=None):
    from database import get_connection, rows_to_list
    q = """SELECT gp.*, c.name AS customer_name, c.phone AS customer_phone, c.contact_person AS customer_contact,
                  s.name AS supplier_name, s.phone AS supplier_phone, s.contact_person AS supplier_contact,
                  p.name AS product_name,
                  COALESCE(c.phone, s.phone) AS party_phone,
                  COALESCE(c.contact_person, s.contact_person) AS party_contact_person,
                  si.document_no AS sales_invoice_no, pi.document_no AS purchase_invoice_no,
                  dn.document_no AS delivery_note_no, grn.document_no AS grn_no,
                  ws.document_no AS weight_slip_no,
                  COALESCE(si.total_net_weight, pi.total_net_weight) AS invoice_weight_kg,
                  COALESCE(si.physical_weight_kg, pi.physical_weight_kg) AS physical_weight_kg,
                  COALESCE(si.weight_variance_kg, pi.weight_variance_kg) AS weight_variance_kg,
                  COALESCE(si.weight_variance_pct, pi.weight_variance_pct) AS weight_variance_pct,
                  si.payment_mode AS invoice_payment_mode, si.paid_amount AS invoice_paid_amount,
                  si.total AS invoice_total, si.notes AS sales_notes,
                  pi.payment_mode AS purchase_payment_mode,
                  pi.paid_amount AS purchase_paid_amount, pi.total AS purchase_invoice_total,
                  pi.notes AS purchase_notes
           FROM gate_passes gp
           LEFT JOIN customers c ON gp.customer_id=c.id
           LEFT JOIN suppliers s ON gp.supplier_id=s.id
           LEFT JOIN products p ON gp.product_id=p.id
           LEFT JOIN sales_invoices si ON gp.sales_invoice_id=si.id
           LEFT JOIN purchase_invoices pi ON gp.purchase_invoice_id=pi.id
           LEFT JOIN delivery_notes dn ON gp.delivery_note_id=dn.id
           LEFT JOIN goods_receipt_notes grn ON gp.grn_id=grn.id
           LEFT JOIN weight_slips ws ON gp.weight_slip_id=ws.id WHERE 1=1"""
    params = []
    if pass_type:
        q += " AND gp.pass_type=?"; params.append(pass_type)
    if from_date:
        q += " AND gp.pass_date>=?"; params.append(from_date)
    if to_date:
        q += " AND gp.pass_date<=?"; params.append(to_date)
    if sales_invoice_id:
        q += " AND gp.sales_invoice_id=?"; params.append(sales_invoice_id)
    if purchase_invoice_id:
        q += " AND gp.purchase_invoice_id=?"; params.append(purchase_invoice_id)
    q += " ORDER BY gp.pass_date DESC, gp.id DESC"
    with get_connection() as conn:
        ensure_gate_pass_schema(conn)
        return rows_to_list(conn.execute(q, params).fetchall())


def search_weight_slips(q=None, from_date=None, to_date=None, customer_id=None, supplier_id=None,
                        status=None, statuses=None, page=1, page_size=50, export_all=False):
    from database import run_paginated_list
    from_clause = f"""
        (
            SELECT ws.id, ws.document_no, ws.slip_date, ws.slip_time, ws.created_at, ws.status, ws.vehicle_no, ws.driver_name,
                   ws.first_weight, ws.second_weight, ws.net_weight,
                   ws.customer_id, ws.supplier_id,
                   c.name AS customer_name, c.code AS customer_code,
                   s.name AS supplier_name, s.code AS supplier_code,
                   COALESCE(
                       p.name,
                       (SELECT pr.name FROM sales_invoice_items sii
                        JOIN products pr ON pr.id = sii.product_id
                        WHERE sii.invoice_id = si.id
                        ORDER BY COALESCE(sii.net_weight, 0) DESC, sii.id LIMIT 1),
                       (SELECT pr.name FROM purchase_invoice_items pii
                        JOIN products pr ON pr.id = pii.product_id
                        WHERE pii.invoice_id = pi.id
                        ORDER BY COALESCE(pii.net_weight, 0) DESC, pii.id LIMIT 1)
                   ) AS product_name,
                   si.document_no AS sales_invoice_no, pi.document_no AS purchase_invoice_no
            FROM weight_slips ws
            LEFT JOIN customers c ON ws.customer_id=c.id
            LEFT JOIN suppliers s ON ws.supplier_id=s.id
            LEFT JOIN products p ON ws.product_id=p.id
            {_WS_SALES_INV_JOIN}
            {_WS_PURCHASE_INV_JOIN}
        ) t
    """
    where, params = [], []
    if from_date:
        where.append("slip_date>=?"); params.append(from_date)
    if to_date:
        where.append("slip_date<=?"); params.append(to_date)
    if customer_id:
        where.append("customer_id=?"); params.append(customer_id)
    if supplier_id:
        where.append("supplier_id=?"); params.append(supplier_id)
    status_list = [s for s in (statuses or []) if s]
    if status_list:
        where.append(f"status IN ({','.join('?' for _ in status_list)})")
        params.extend(status_list)
    elif status and status != "All":
        where.append("status=?"); params.append(status)
    if q:
        like = f"%{q.strip()}%"
        where.append(
            "(document_no LIKE ? OR vehicle_no LIKE ? OR customer_name LIKE ? OR supplier_name LIKE ? "
            "OR product_name LIKE ? OR sales_invoice_no LIKE ? OR purchase_invoice_no LIKE ?)"
        )
        params.extend([like] * 7)
    order_by = "slip_date DESC, id DESC"
    if status_list and "first_weigh" in status_list:
        # Pending first for Edit / Delete pickers
        order_by = (
            "CASE status WHEN 'first_weigh' THEN 0 WHEN 'completed' THEN 1 "
            "WHEN 'cancelled' THEN 2 ELSE 9 END, slip_date DESC, id DESC"
        )
    return run_paginated_list(
        from_clause,
        "id, document_no, slip_date, slip_time, created_at, status, vehicle_no, driver_name, first_weight, second_weight, net_weight, "
        "customer_name, customer_code, supplier_name, supplier_code, product_name, sales_invoice_no, purchase_invoice_no",
        where or None,
        params,
        order_by,
        page,
        page_size,
        export_all=export_all,
    )


def search_gate_passes(q=None, pass_type=None, from_date=None, to_date=None, status=None,
                       page=1, page_size=50, export_all=False):
    from database import run_paginated_list
    ensure_gate_pass_schema()
    from_clause = """
        (
            SELECT gp.id, gp.document_no, gp.pass_date, gp.pass_time, gp.created_at, gp.pass_type, gp.party_name, gp.vehicle_no,
                   gp.quantity, gp.weight, gp.status,
                   si.document_no AS sales_invoice_no, pi.document_no AS purchase_invoice_no,
                   si.payment_mode AS invoice_payment_mode, si.paid_amount AS invoice_paid_amount,
                   si.total AS invoice_total,
                   c.name AS customer_name, s.name AS supplier_name
            FROM gate_passes gp
            LEFT JOIN customers c ON gp.customer_id=c.id
            LEFT JOIN suppliers s ON gp.supplier_id=s.id
            LEFT JOIN sales_invoices si ON gp.sales_invoice_id=si.id
            LEFT JOIN purchase_invoices pi ON gp.purchase_invoice_id=pi.id
        ) t
    """
    where, params = [], []
    if pass_type:
        where.append("pass_type=?"); params.append(pass_type)
    if from_date:
        where.append("pass_date>=?"); params.append(from_date)
    if to_date:
        where.append("pass_date<=?"); params.append(to_date)
    if status and status != "All":
        where.append("status=?"); params.append(status)
    if q:
        like = f"%{q.strip()}%"
        where.append(
            "(document_no LIKE ? OR party_name LIKE ? OR vehicle_no LIKE ? OR customer_name LIKE ? "
            "OR supplier_name LIKE ? OR sales_invoice_no LIKE ? OR purchase_invoice_no LIKE ?)"
        )
        params.extend([like] * 7)
    return run_paginated_list(
        from_clause,
        "id, document_no, pass_date, pass_time, created_at, pass_type, party_name, vehicle_no, quantity, weight, status, "
        "sales_invoice_no, purchase_invoice_no, invoice_payment_mode, invoice_paid_amount, invoice_total, "
        "customer_name, supplier_name",
        where or None,
        params,
        "pass_date DESC, id DESC",
        page,
        page_size,
        export_all=export_all,
    )


# ---------- Dashboard v2 ----------
def _cash_balance_as_of(conn, as_of_date):
    """Cash book balance including COA opening (code 1000) through as_of_date."""
    coa = conn.execute(
        "SELECT COALESCE(opening_balance,0) FROM chart_of_accounts WHERE code='1000'"
    ).fetchone()
    base = float(coa[0] if coa else 0)
    rec = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM cash_receipts WHERE receipt_date<=?", (as_of_date,)
    ).fetchone()[0]
    pay = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM cash_payments WHERE payment_date<=?", (as_of_date,)
    ).fetchone()[0]
    return base + float(rec) - float(pay)


def _bank_balance_as_of(conn, as_of_date):
    """Combined bank balance (11xx COA opening + bank receipts/payments) through as_of_date."""
    coa = conn.execute(
        "SELECT COALESCE(SUM(opening_balance),0) FROM chart_of_accounts WHERE code LIKE '11%'"
    ).fetchone()
    base = float(coa[0] if coa else 0)
    rec = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM bank_receipts WHERE receipt_date<=?", (as_of_date,)
    ).fetchone()[0]
    pay = conn.execute(
        "SELECT COALESCE(SUM(amount),0) FROM bank_payments WHERE payment_date<=?", (as_of_date,)
    ).fetchone()[0]
    return base + float(rec) - float(pay)


def _table_exists(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _safe_count(conn, sql, params=()):
    try:
        return int(conn.execute(sql, params).fetchone()[0])
    except Exception:
        return 0


def get_dashboard_stats_v2():
    from database import get_connection, rows_to_list, _product_stock_join, _product_stock_sql
    from datetime import date, timedelta

    today_dt = date.today()
    today = today_dt.strftime("%Y-%m-%d")
    month_start = today_dt.replace(day=1).strftime("%Y-%m-%d")

    with get_connection() as conn:
        stats = {"as_of": today, "generated_at": now()}

        # Executive KPIs: posted (approved) invoices only — drafts inflate MTD.
        stats["today_sales"] = float(conn.execute(
            "SELECT COALESCE(SUM(total),0) FROM sales_invoices WHERE invoice_date=? AND status='approved'",
            (today,),
        ).fetchone()[0])
        stats["today_purchases"] = float(conn.execute(
            "SELECT COALESCE(SUM(total),0) FROM purchase_invoices WHERE invoice_date=? AND status='approved'",
            (today,),
        ).fetchone()[0])
        stats["mtd_sales"] = float(conn.execute(
            "SELECT COALESCE(SUM(total),0) FROM sales_invoices WHERE invoice_date>=? AND status='approved'",
            (month_start,),
        ).fetchone()[0])
        stats["mtd_purchases"] = float(conn.execute(
            "SELECT COALESCE(SUM(total),0) FROM purchase_invoices WHERE invoice_date>=? AND status='approved'",
            (month_start,),
        ).fetchone()[0])
        stats["mtd_sales_draft"] = float(conn.execute(
            "SELECT COALESCE(SUM(total),0) FROM sales_invoices WHERE invoice_date>=? AND status IN ('draft','pending_approval')",
            (month_start,),
        ).fetchone()[0])
        stats["mtd_purchases_draft"] = float(conn.execute(
            "SELECT COALESCE(SUM(total),0) FROM purchase_invoices WHERE invoice_date>=? AND status IN ('draft','pending_approval')",
            (month_start,),
        ).fetchone()[0])

        stats["cash_balance"] = _cash_balance_as_of(conn, today)
        stats["bank_balance"] = _bank_balance_as_of(conn, today)
        stats["liquid_balance"] = stats["cash_balance"] + stats["bank_balance"]

        # Dual-role parties (same code as customer + supplier) are netted (+Dr/−Cr),
        # matching combined party ledger — avoids inflated Top Receivables/Payables.
        from database import net_dual_role_party_balances
        _net_exp = net_dual_role_party_balances(conn)
        stats["receivables"] = float(_net_exp["total_receivables"])
        stats["payables"] = float(_net_exp["total_payables"])
        stats["party_exposure_netted"] = True
        stk = _product_stock_join("p")
        sc = _product_stock_sql("p")
        stats["stock_value"] = float(conn.execute(
            f"SELECT COALESCE(SUM({sc} * p.purchase_price),0) FROM products p {stk} WHERE p.is_active=1"
        ).fetchone()[0])
        stats["production_value"] = float(conn.execute(
            """SELECT COALESCE(SUM(pl.quantity * po.cost_per_unit),0)
               FROM production_finished_receipts pl
               JOIN production_orders po ON pl.production_order_id=po.id
               WHERE po.status='completed'"""
        ).fetchone()[0] or 0)

        pending = {
            "sales_approval": _safe_count(conn, "SELECT COUNT(*) FROM sales_invoices WHERE status='pending_approval'"),
            "purchase_approval": _safe_count(conn, "SELECT COUNT(*) FROM purchase_invoices WHERE status='pending_approval'"),
            "leave": _safe_count(conn, "SELECT COUNT(*) FROM leave_requests WHERE status='pending'"),
            "advances": _safe_count(conn, "SELECT COUNT(*) FROM employee_advances WHERE status='pending'"),
            "loans": _safe_count(conn, "SELECT COUNT(*) FROM employee_loans WHERE status='pending'"),
            "payroll_draft": _safe_count(conn, "SELECT COUNT(*) FROM payroll_runs WHERE status='draft'"),
            "gate_pass_open": _safe_count(conn, gate_pass_pending_count_sql()) if _table_exists(conn, "gate_passes") else 0,
            "delivery_draft": _safe_count(conn, "SELECT COUNT(*) FROM delivery_notes WHERE status='draft'") if _table_exists(conn, "delivery_notes") else 0,
            "sales_orders_open": _safe_count(
                conn, "SELECT COUNT(*) FROM sales_orders WHERE status NOT IN ('completed','cancelled')"
            ) if _table_exists(conn, "sales_orders") else 0,
            "production_active": _safe_count(
                conn, "SELECT COUNT(*) FROM production_orders WHERE status IN ('draft','issued','in_progress')"
            ) if _table_exists(conn, "production_orders") else 0,
            "journal_draft": _safe_count(conn, "SELECT COUNT(*) FROM journal_vouchers WHERE status='draft'") if _table_exists(conn, "journal_vouchers") else 0,
        }
        stats["pending_breakdown"] = pending
        stats["pending_approvals"] = sum(pending.values())
        stats["pending_deliveries"] = pending["delivery_draft"] + pending["sales_orders_open"]

        low = conn.execute(
            f"""SELECT p.code, p.name, {sc} AS stock_qty, p.reorder_level,
                       COALESCE(u.code, '') AS unit
                FROM products p {stk}
                LEFT JOIN units_of_measure u ON p.unit_id=u.id
                WHERE p.is_active=1 AND p.reorder_level>0
                AND {sc} <= p.reorder_level ORDER BY stock_qty ASC LIMIT 20"""
        ).fetchall()
        stats["low_stock"] = rows_to_list(low)
        stats["low_stock_count"] = len(stats["low_stock"])

        stats["recent_sales"] = rows_to_list(conn.execute(
            """SELECT s.document_no AS invoice_no, s.invoice_date AS sale_date, s.total, s.status,
                      c.name AS customer_name
               FROM sales_invoices s JOIN customers c ON s.customer_id=c.id
               ORDER BY s.id DESC LIMIT 8"""
        ).fetchall())
        stats["recent_purchases"] = rows_to_list(conn.execute(
            """SELECT p.document_no AS invoice_no, p.invoice_date AS purchase_date, p.total, p.status,
                      s.name AS supplier_name
               FROM purchase_invoices p JOIN suppliers s ON p.supplier_id=s.id
               ORDER BY p.id DESC LIMIT 8"""
        ).fetchall())

        stats["top_receivables"] = [
            {
                "code": r["code"],
                "name": r["name"],
                "balance": r["balance"],
                "credit_limit": r.get("credit_limit"),
            }
            for r in _net_exp["receivables"][:8]
        ]
        stats["top_payables"] = [
            {"code": r["code"], "name": r["name"], "balance": r["balance"]}
            for r in _net_exp["payables"][:8]
        ]

        def _month_bounds(ref_date, months_back):
            y, m = ref_date.year, ref_date.month - months_back
            while m <= 0:
                m += 12
                y -= 1
            m_start = date(y, m, 1)
            if m == 12:
                m_end = date(y + 1, 1, 1) - timedelta(days=1)
            else:
                m_end = date(y, m + 1, 1) - timedelta(days=1)
            return m_start, m_end

        trend = []
        for months_back in range(5, -1, -1):
            m_start, m_end = _month_bounds(today_dt, months_back)
            ms, me = m_start.strftime("%Y-%m-%d"), m_end.strftime("%Y-%m-%d")
            sales = float(conn.execute(
                "SELECT COALESCE(SUM(total),0) FROM sales_invoices WHERE invoice_date BETWEEN ? AND ? AND status='approved'",
                (ms, me),
            ).fetchone()[0])
            purchases = float(conn.execute(
                "SELECT COALESCE(SUM(total),0) FROM purchase_invoices WHERE invoice_date BETWEEN ? AND ? AND status='approved'",
                (ms, me),
            ).fetchone()[0])
            trend.append({"month": m_start.strftime("%b %Y"), "sales": sales, "purchases": purchases})
        stats["monthly_trend"] = trend

        stats["customers"] = conn.execute("SELECT COUNT(*) FROM customers WHERE is_active=1").fetchone()[0]
        stats["suppliers"] = conn.execute("SELECT COUNT(*) FROM suppliers WHERE is_active=1").fetchone()[0]
        stats["items"] = conn.execute("SELECT COUNT(*) FROM products WHERE is_active=1").fetchone()[0]
        stats["employees"] = _safe_count(conn, "SELECT COUNT(*) FROM employees WHERE is_active=1")
        stats["sales_total"] = float(conn.execute(
            "SELECT COALESCE(SUM(total),0) FROM sales_invoices WHERE status='approved'"
        ).fetchone()[0])
        stats["purchases_total"] = float(conn.execute(
            "SELECT COALESCE(SUM(total),0) FROM purchase_invoices WHERE status='approved'"
        ).fetchone()[0])

        if _table_exists(conn, "attendance"):
            att = conn.execute(
                """SELECT status, COUNT(*) AS cnt FROM attendance WHERE att_date=? GROUP BY status""",
                (today,),
            ).fetchall()
            att_map = {r["status"]: r["cnt"] for r in att}
            stats["attendance_today"] = {
                "present": att_map.get("present", 0),
                "absent": att_map.get("absent", 0),
                "leave": att_map.get("leave", 0) + att_map.get("half_day", 0),
                "late": att_map.get("late", 0),
            }
        else:
            stats["attendance_today"] = {"present": 0, "absent": 0, "leave": 0, "late": 0}

        stats["today_weight_slips"] = _safe_count(
            conn, "SELECT COUNT(*) FROM weight_slips WHERE slip_date=?", (today,)
        ) if _table_exists(conn, "weight_slips") else 0
        stats["today_gate_passes"] = _safe_count(
            conn, "SELECT COUNT(*) FROM gate_passes WHERE pass_date=?", (today,)
        ) if _table_exists(conn, "gate_passes") else 0

        try:
            from db_v3 import get_control_account_reconciliation
            recon = get_control_account_reconciliation(as_of=today)
            stats["ar_gl_diff"] = recon["ar_difference"]
            stats["ap_gl_diff"] = recon["ap_difference"]
        except Exception:
            stats["ar_gl_diff"] = 0
            stats["ap_gl_diff"] = 0

        fy = conn.execute("SELECT fy_code, start_date, end_date FROM fiscal_years WHERE is_active=1 LIMIT 1").fetchone()
        stats["fiscal_year"] = dict(fy) if fy else None

        alerts = []
        if pending["sales_approval"]:
            alerts.append({"severity": "high", "module": "Sales", "message": f"{pending['sales_approval']} sales invoice(s) awaiting approval"})
        if pending["purchase_approval"]:
            alerts.append({"severity": "high", "module": "Purchase", "message": f"{pending['purchase_approval']} purchase invoice(s) awaiting approval"})
        if stats["low_stock_count"]:
            alerts.append({"severity": "medium", "module": "Inventory", "message": f"{stats['low_stock_count']} product(s) at or below reorder level"})
        if abs(stats["ar_gl_diff"]) >= 0.01:
            alerts.append({"severity": "high", "module": "Finance", "message": f"AR control mismatch: Rs. {stats['ar_gl_diff']:,.2f}"})
        if abs(stats["ap_gl_diff"]) >= 0.01:
            alerts.append({"severity": "high", "module": "Finance", "message": f"AP control mismatch: Rs. {stats['ap_gl_diff']:,.2f}"})
        if pending["payroll_draft"]:
            alerts.append({"severity": "medium", "module": "HR", "message": f"{pending['payroll_draft']} payroll run(s) in draft"})
        if pending["leave"]:
            alerts.append({"severity": "low", "module": "HR", "message": f"{pending['leave']} leave request(s) pending"})
        stats["alerts"] = alerts

        return stats


# ---------- Backup / Restore ----------
def backup_database(dest_path=None):
    from database import DB_PATH
    dest = Path(dest_path) if dest_path else DB_PATH.parent / f"ifs_erp_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    shutil.copy2(DB_PATH, dest)
    return str(dest)


def restore_database(source_path):
    from database import DB_PATH, init_db, reset_runtime_state
    src = Path(source_path)
    if not src.exists():
        raise FileNotFoundError(f"Backup not found: {source_path}")
    shutil.copy2(src, DB_PATH)
    reset_runtime_state()
    init_db(force=True)
