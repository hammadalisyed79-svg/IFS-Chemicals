"""Distributor portal — orders, catalogue, isolation."""

from __future__ import annotations

from datetime import date, datetime

from db_v15 import PORTAL_ORDER_STATUSES
from erp_core import notifications as notify


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_distributor_customer_id(user: dict) -> int | None:
    cid = user.get("linked_customer_id")
    if cid:
        return int(cid)
    return None


def assert_distributor_access(user: dict, customer_id: int) -> None:
    uid_cid = get_distributor_customer_id(user)
    if uid_cid is None or int(customer_id) != int(uid_cid):
        raise PermissionError("Access denied — distributor data isolation.")


def get_distributor_profile(user: dict) -> dict | None:
    cid = get_distributor_customer_id(user)
    if not cid:
        return None
    from database import get_connection, row_to_dict
    from db_v15 import ensure_distributor_catalog_schema
    with get_connection() as conn:
        ensure_distributor_catalog_schema(conn)
        row = conn.execute(
            """SELECT c.id AS customer_id, c.name AS customer_name, c.code AS customer_code,
                      c.current_balance, c.phone, c.email, c.address, c.city, c.province,
                      c.ntn, c.strn, c.contact_person,
                      COALESCE(c.dispatch_phone, dp.dispatch_phone) AS dispatch_phone,
                      COALESCE(c.accounts_phone, dp.accounts_phone) AS accounts_phone,
                      COALESCE(c.owner_phone, dp.owner_phone) AS owner_phone,
                      COALESCE(dp.business_name, c.name) AS business_name,
                      COALESCE(dp.contact_name, c.contact_person) AS contact_name,
                      COALESCE(dp.assigned_price_list_id, c.assigned_price_list_id) AS assigned_price_list_id,
                      COALESCE(dp.credit_limit, c.credit_limit, 0) AS credit_limit,
                      COALESCE(dp.show_stock, 0) AS show_stock,
                      COALESCE(dp.portal_enabled, c.portal_enabled, 0) AS portal_enabled,
                      pl.name AS price_list_name
               FROM customers c
               LEFT JOIN distributor_profiles dp ON dp.customer_id=c.id
               LEFT JOIN price_lists pl ON pl.id=COALESCE(dp.assigned_price_list_id, c.assigned_price_list_id)
               WHERE c.id=?""",
            (cid,),
        ).fetchone()
        return row_to_dict(row) if row else None


def update_my_profile(user: dict, data: dict) -> dict:
    """
    Distributor self-service profile update.
    Writes to customers (master) and distributor_profiles so staff ERP sees the same contacts.
    """
    cid = get_distributor_customer_id(user)
    if not cid:
        raise PermissionError("Distributor account not linked to a customer.")
    assert_distributor_access(user, cid)

    def _clean(key, max_len=80):
        v = data.get(key)
        if v is None:
            return None
        s = str(v).strip()
        return s[:max_len] if s else None

    phone = _clean("phone", 40)
    email = _clean("email", 120)
    contact_name = _clean("contact_name", 120)
    city = _clean("city", 80)
    province = _clean("province", 80)
    address = _clean("address", 255)
    ntn = _clean("ntn", 40)
    strn = _clean("strn", 40)
    dispatch_phone = _clean("dispatch_phone", 40)
    accounts_phone = _clean("accounts_phone", 40)
    owner_phone = _clean("owner_phone", 40)

    if email and "@" not in email:
        raise ValueError("Enter a valid email address (or leave blank).")

    from database import get_connection
    from db_v15 import ensure_distributor_catalog_schema

    uid = user.get("id")
    with get_connection() as conn:
        ensure_distributor_catalog_schema(conn)
        conn.execute(
            """UPDATE customers SET
                 phone=?, email=?, contact_person=?, city=?, province=?, address=?,
                 ntn=?, strn=?,
                 dispatch_phone=?, accounts_phone=?, owner_phone=?,
                 modified_by=?, modified_at=?
               WHERE id=?""",
            (
                phone, email, contact_name, city, province, address,
                ntn, strn,
                dispatch_phone, accounts_phone, owner_phone,
                uid, _now(), cid,
            ),
        )
        cust_name = conn.execute(
            "SELECT name FROM customers WHERE id=?", (cid,)
        ).fetchone()
        biz = (cust_name[0] if cust_name else None) or None
        exists = conn.execute(
            "SELECT id FROM distributor_profiles WHERE customer_id=?", (cid,)
        ).fetchone()
        if exists:
            conn.execute(
                """UPDATE distributor_profiles SET
                     contact_name=?, phone=?, email=?, city=?, province=?, address=?,
                     ntn=?, strn=?,
                     dispatch_phone=?, accounts_phone=?, owner_phone=?,
                     modified_at=?
                   WHERE customer_id=?""",
                (
                    contact_name, phone, email, city, province, address,
                    ntn, strn,
                    dispatch_phone, accounts_phone, owner_phone,
                    _now(), cid,
                ),
            )
        else:
            conn.execute(
                """INSERT INTO distributor_profiles(
                     customer_id, business_name, contact_name, phone, email,
                     city, province, address, ntn, strn,
                     dispatch_phone, accounts_phone, owner_phone, portal_enabled)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,1)""",
                (
                    cid, biz,
                    contact_name, phone, email, city, province, address, ntn, strn,
                    dispatch_phone, accounts_phone, owner_phone,
                ),
            )
    return get_distributor_profile(user) or {}


def resolve_price_list_id(user: dict) -> int | None:
    prof = get_distributor_profile(user)
    if not prof:
        return None
    plid = prof.get("assigned_price_list_id")
    if plid:
        return int(plid)
    from database import get_connection
    cid = get_distributor_customer_id(user)
    with get_connection() as conn:
        row = conn.execute(
            """SELECT price_list_id FROM distributor_price_lists
               WHERE customer_id=? AND is_active=1
               ORDER BY priority DESC LIMIT 1""",
            (cid,),
        ).fetchone()
        return int(row[0]) if row else None


def get_product_price(product_id: int, price_list_id: int | None, fallback_rate: float = 0) -> dict:
    from database import get_connection, row_to_dict
    if not price_list_id:
        return {"rate": fallback_rate, "discount_pct": 0, "min_qty": 1}
    with get_connection() as conn:
        row = conn.execute(
            """SELECT rate, discount_pct, min_qty FROM price_list_items
               WHERE price_list_id=? AND product_id=? AND is_active=1""",
            (price_list_id, product_id),
        ).fetchone()
        if row:
            return {"rate": float(row[0]), "discount_pct": float(row[1] or 0), "min_qty": float(row[2] or 1)}
    return {"rate": fallback_rate, "discount_pct": 0, "min_qty": 1}


def get_catalog(user: dict, *, search: str | None = None, limit: int = 300):
    """Distributor catalogue — only products on this customer's catalog (effective today)."""
    from database import get_connection, rows_to_list
    from erp_core import distributor_catalog as dcat

    dcat.ensure_schema()
    cid = get_distributor_customer_id(user)
    if not cid:
        return []
    prof = get_distributor_profile(user) or {}
    show_stock = bool(prof.get("show_stock"))

    where = [
        "d.customer_id=?",
        "COALESCE(d.is_active,1)=1",
        "date(d.effective_from) <= date('now')",
        "COALESCE(p.is_active,1)=1",
    ]
    params: list = [cid]
    if search and search.strip():
        like = f"%{search.strip()}%"
        where.append("(p.code LIKE ? OR p.name LIKE ?)")
        params.extend([like, like])

    stock_expr = (
        "(SELECT COALESCE(SUM(ws.quantity), 0) FROM warehouse_stock ws WHERE ws.product_id=p.id)"
        if show_stock
        else "0"
    )
    if not (search and search.strip()):
        limit = min(int(limit or 300), 150)
    else:
        limit = min(int(limit or 300), 400)
    params.append(limit)

    sql = f"""
        SELECT p.id, p.code, p.name, p.unit_id, u.code AS unit,
               d.rate, d.discount_pct, d.min_qty, d.admin_changed, d.source,
               d.effective_from, d.admin_note,
               {stock_expr} AS stock_qty
        FROM distributor_catalog_items d
        JOIN products p ON p.id=d.product_id
        LEFT JOIN units_of_measure u ON u.id=p.unit_id
        WHERE {' AND '.join(where)}
        ORDER BY CASE WHEN COALESCE(d.admin_changed,0)=1 THEN 0 ELSE 1 END, p.name
        LIMIT ?
    """
    with get_connection() as conn:
        rows = rows_to_list(conn.execute(sql, params).fetchall())
    out = []
    for r in rows:
        rate = float(r.get("rate") or 0)
        disc = float(r.get("discount_pct") or 0)
        net = rate * (1 - disc / 100.0)
        item = {
            "product_id": r["id"],
            "code": r["code"],
            "name": r["name"],
            "unit": r.get("unit") or "",
            "rate": rate,
            "discount_pct": disc,
            "net_rate": net,
            "min_qty": float(r.get("min_qty") or 1),
            "admin_changed": bool(r.get("admin_changed")),
            "source": r.get("source") or "invoice",
            "effective_from": r.get("effective_from"),
            "admin_note": r.get("admin_note") or "",
        }
        if show_stock:
            item["stock_qty"] = float(r.get("stock_qty") or 0)
        out.append(item)
    return out


def get_customer_outstanding(customer_id: int) -> float:
    from database import get_connection
    with get_connection() as conn:
        row = conn.execute(
            "SELECT current_balance FROM customers WHERE id=?", (customer_id,)
        ).fetchone()
        return float(row[0] or 0) if row else 0.0


def check_credit_limit(user: dict, order_total: float) -> tuple[bool, str]:
    prof = get_distributor_profile(user) or {}
    limit = float(prof.get("credit_limit") or 0)
    if limit <= 0:
        return True, ""
    cid = get_distributor_customer_id(user)
    outstanding = get_customer_outstanding(cid)
    if outstanding + order_total > limit:
        return False, (
            f"Credit limit exceeded. Limit Rs. {limit:,.2f}, "
            f"outstanding Rs. {outstanding:,.2f}, order Rs. {order_total:,.2f}."
        )
    return True, ""


def list_portal_orders(user: dict, *, status: str | None = None):
    cid = get_distributor_customer_id(user)
    if cid:
        try:
            _backfill_portal_mirrors_for_customer(int(cid))
        except Exception:
            pass
    from database import get_connection, rows_to_list
    where = ["po.customer_id=?"]
    params: list = [cid]
    if status and status != "All":
        where.append("po.status=?")
        params.append(status)
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            f"""SELECT po.*, so.document_no AS sales_order_no
                FROM portal_orders po
                LEFT JOIN sales_orders so ON so.id=po.sales_order_id
                WHERE {' AND '.join(where)}
                ORDER BY po.order_date DESC, po.id DESC""",
            params,
        ).fetchall())


def _backfill_portal_mirrors_for_customer(customer_id: int) -> int:
    """Create portal mirrors for open ERP sales orders that are not yet in My Orders."""
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        rows = rows_to_list(conn.execute(
            """SELECT so.id
               FROM sales_orders so
               WHERE so.customer_id=?
                 AND LOWER(COALESCE(so.status,'')) IN ('open','partial')
                 AND COALESCE(so.portal_order_id, 0)=0
                 AND NOT EXISTS (
                     SELECT 1 FROM portal_orders po WHERE po.sales_order_id=so.id
                 )
               ORDER BY so.id""",
            (customer_id,),
        ).fetchall())
    created = 0
    for r in rows:
        try:
            if sync_portal_order_from_sales_order(int(r["id"]), notify_user=False):
                created += 1
        except Exception:
            continue
    return created


def get_portal_order(user: dict, order_id: int) -> dict | None:
    from database import get_connection, row_to_dict, rows_to_list
    with get_connection() as conn:
        row = conn.execute(
            """SELECT po.*, so.document_no AS sales_order_no
               FROM portal_orders po
               LEFT JOIN sales_orders so ON so.id=po.sales_order_id
               WHERE po.id=?""",
            (order_id,),
        ).fetchone()
        if not row:
            return None
        order = row_to_dict(row)
        assert_distributor_access(user, order["customer_id"])
        order["items"] = rows_to_list(conn.execute(
            """SELECT poi.product_id, p.code AS product_code, p.name AS product_name,
                      poi.quantity, poi.rate, poi.discount_pct, poi.amount, poi.min_qty
               FROM portal_order_items poi
               JOIN products p ON p.id=poi.product_id
               WHERE portal_order_id=?""",
            (order_id,),
        ).fetchall())
        return order


def get_portal_order_internal(order_id: int) -> dict | None:
    from database import get_connection, row_to_dict, rows_to_list
    with get_connection() as conn:
        row = conn.execute(
            """SELECT po.*, c.name AS customer_name, c.code AS customer_code,
                      u.username AS distributor_username
               FROM portal_orders po
               JOIN customers c ON c.id=po.customer_id
               LEFT JOIN users u ON u.id=po.distributor_user_id
               WHERE po.id=?""",
            (order_id,),
        ).fetchone()
        if not row:
            return None
        order = row_to_dict(row)
        order["items"] = rows_to_list(conn.execute(
            """SELECT poi.*, p.code AS product_code, p.name AS product_name
               FROM portal_order_items poi JOIN products p ON p.id=poi.product_id
               WHERE portal_order_id=?""",
            (order_id,),
        ).fetchall())
        return order


def list_all_portal_orders(*, status: str | None = None, customer_id=None):
    from database import get_connection, rows_to_list
    where, params = ["1=1"], []
    if status and status != "All":
        where.append("po.status=?")
        params.append(status)
    if customer_id:
        where.append("po.customer_id=?")
        params.append(customer_id)
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            f"""SELECT po.*, c.name AS customer_name, c.code AS customer_code
                FROM portal_orders po
                JOIN customers c ON c.id=po.customer_id
                WHERE {' AND '.join(where)}
                ORDER BY po.order_date DESC, po.id DESC""",
            params,
        ).fetchall())


def _calc_lines(cart: list[dict], customer_id: int) -> tuple[list[dict], float, float]:
    """Price lines from per-customer distributor catalog (server-side)."""
    from erp_core import distributor_catalog as dcat

    lines = []
    subtotal = 0.0
    for row in cart:
        pid = int(row["product_id"])
        qty = float(row["quantity"])
        cat = dcat.get_catalog_price(customer_id, pid)
        if not cat:
            raise ValueError(f"Product {pid} is not on your allocated product list.")
        rate = float(cat["rate"] or 0)
        disc = float(cat.get("discount_pct") or 0)
        min_qty = float(cat.get("min_qty") or 1)
        if qty < min_qty:
            raise ValueError(f"Minimum quantity for product {pid} is {min_qty}")
        gross = qty * rate
        amt = gross * (1 - disc / 100.0)
        subtotal += amt
        lines.append({
            "product_id": pid,
            "quantity": qty,
            "rate": rate,
            "discount_pct": disc,
            "amount": amt,
            "min_qty": min_qty,
        })
    return lines, subtotal, subtotal


def create_portal_order(
    user: dict,
    cart: list[dict],
    notes: str = "",
    submit: bool = True,
    *,
    order_date=None,
    delivery_date=None,
    dispatch_town: str = "",
) -> int:
    if not cart:
        raise ValueError("Cart is empty.")
    cid = get_distributor_customer_id(user)
    if not cid:
        raise PermissionError("Distributor account not linked to a customer.")
    lines, subtotal, total = _calc_lines(cart, cid)
    ok, msg = check_credit_limit(user, total)
    if not ok:
        raise ValueError(msg)

    town = (dispatch_town or "").strip()
    if not town:
        raise ValueError("Dispatch town is required — where should this order be delivered?")

    od = str(order_date or date.today())[:10]
    dd = str(delivery_date)[:10] if delivery_date else None
    if dd and dd < od:
        raise ValueError("Delivery date cannot be before order date.")

    from database import get_connection, ensure_document_no
    from db_v15 import ensure_distributor_catalog_schema
    status = "Submitted" if submit else "Draft"
    with get_connection() as conn:
        ensure_distributor_catalog_schema(conn)  # ensures delivery_date / dispatch_town
        order_no = ensure_document_no("POR", None, conn)
        cur = conn.execute(
            """INSERT INTO portal_orders(
                order_no,customer_id,distributor_user_id,order_date,delivery_date,dispatch_town,status,
                subtotal,discount,tax,total,notes,submitted_at,source_channel)
               VALUES(?,?,?,?,?,?,?,?,0,0,?,?,?,'portal')""",
            (
                order_no, cid, user["id"], od, dd, town, status,
                subtotal, total, notes,
                _now() if submit else None,
            ),
        )
        poid = cur.lastrowid
        for ln in lines:
            conn.execute(
                """INSERT INTO portal_order_items(
                    portal_order_id,product_id,quantity,rate,discount_pct,amount,min_qty)
                   VALUES(?,?,?,?,?,?,?)""",
                (poid, ln["product_id"], ln["quantity"], ln["rate"],
                 ln["discount_pct"], ln["amount"], ln["min_qty"]),
            )

    order = get_portal_order(user, poid)
    if submit:
        # Enrich for staff notification text
        prof = get_distributor_profile(user) or {}
        order["customer_name"] = (
            f"{prof.get('customer_code') or ''} — {prof.get('customer_name') or prof.get('business_name') or ''}"
        ).strip(" —")
        so_id = _create_sales_order_draft(user, order, lines)
        _link_sales_order(poid, so_id)
        order = get_portal_order(user, poid)
        order["customer_name"] = (
            f"{prof.get('customer_code') or ''} — {prof.get('customer_name') or ''}"
        ).strip(" —")
        notify.notify_internal_sales_order(order)
        notify.notify_distributor(
            cid, "order_submitted", f"Order {order['order_no']} submitted",
            "Your order was received and is under review.", "portal_order", poid,
        )
    return poid


def _link_sales_order(portal_order_id: int, sales_order_id: int) -> None:
    from database import get_connection
    with get_connection() as conn:
        conn.execute(
            "UPDATE portal_orders SET sales_order_id=?, status='Under Review', modified_at=? WHERE id=?",
            (sales_order_id, _now(), portal_order_id),
        )
        conn.execute(
            "UPDATE sales_orders SET portal_order_id=?, source_channel='portal' WHERE id=?",
            (portal_order_id, sales_order_id),
        )


def _create_sales_order_draft(user: dict, order: dict, lines: list[dict]) -> int:
    from db_v3 import save_sales_order
    from database import get_connection
    from db_v15 import ensure_distributor_catalog_schema
    cid = order["customer_id"]
    wh_id = None
    town = (order.get("dispatch_town") or "").strip()
    with get_connection() as conn:
        wh = conn.execute("SELECT id FROM warehouses WHERE is_active=1 ORDER BY id LIMIT 1").fetchone()
        wh_id = wh[0] if wh else None
    note_bits = [f"Portal order {order['order_no']}"]
    if town:
        note_bits.append(f"Dispatch To: {town}")
    if order.get("delivery_date"):
        note_bits.append(f"Delivery: {order['delivery_date']}")
    if order.get("notes"):
        note_bits.append(str(order["notes"]))
    data = {
        "document_no": "",
        "customer_id": cid,
        "order_date": order["order_date"],
        "delivery_date": order.get("delivery_date"),
        "warehouse_id": wh_id,
        "status": "open",
        "notes": " | ".join(note_bits),
        "portal_order_id": order["id"],
        "source_channel": "portal",
        "dispatch_town": town or None,
    }
    so_lines = [
        {
            "product_id": ln["product_id"],
            "item_id": ln["product_id"],
            "quantity": ln["quantity"],
            "rate": ln["rate"],
            "discount_pct": float(ln.get("discount_pct") or 0),
            "line_amount": ln["amount"],
            "amount": ln["amount"],
        }
        for ln in lines
    ]
    so_id = save_sales_order(
        data, so_lines, user_id=user.get("id"), skip_portal_sync=True,
    )
    with get_connection() as conn:
        ensure_distributor_catalog_schema(conn)
        if order.get("delivery_date"):
            conn.execute(
                "UPDATE sales_orders SET delivery_date=? WHERE id=?",
                (str(order["delivery_date"])[:10], so_id),
            )
        if town:
            conn.execute(
                "UPDATE sales_orders SET dispatch_town=? WHERE id=?",
                (town, so_id),
            )
    return so_id


def update_portal_status(portal_order_id: int, status: str, *, user_id=None, reason: str = "") -> None:
    if status not in PORTAL_ORDER_STATUSES:
        raise ValueError(f"Invalid status: {status}")
    reason = (reason or "").strip()
    if status == "Rejected" and not reason:
        raise ValueError("Enter a rejection reason — the distributor will see this notification.")
    from database import get_connection
    with get_connection() as conn:
        row = conn.execute(
            """SELECT customer_id, order_no, status, sales_order_id
               FROM portal_orders WHERE id=?""",
            (portal_order_id,),
        ).fetchone()
        if not row:
            raise ValueError("Portal order not found.")
        cur_status = (row[2] or "").strip()
        if cur_status in ("Delivered", "Invoiced") and status == "Rejected":
            raise ValueError(f"Cannot reject an order that is already {cur_status}.")
        if cur_status == "Rejected" and status == "Rejected":
            raise ValueError("Order is already rejected.")
        if status == "Approved":
            conn.execute(
                """UPDATE portal_orders SET status=?, modified_at=?, approved_at=?, approved_by=?,
                       rejection_reason=NULL
                   WHERE id=?""",
                (status, _now(), _now(), user_id, portal_order_id),
            )
        elif status == "Rejected":
            conn.execute(
                """UPDATE portal_orders SET status=?, modified_at=?, rejection_reason=?
                   WHERE id=?""",
                (status, _now(), reason, portal_order_id),
            )
            # Close linked sales order so staff cannot keep processing it
            so_id = row[3]
            if so_id:
                conn.execute(
                    """UPDATE sales_orders SET status='cancelled', notes=COALESCE(notes,'') || ?,
                           modified_by=?, modified_at=?
                       WHERE id=? AND LOWER(COALESCE(status,'')) NOT IN ('cancelled','canceled','closed')""",
                    (
                        f"\n[Rejected] {reason}",
                        user_id,
                        _now(),
                        so_id,
                    ),
                )
        else:
            conn.execute(
                "UPDATE portal_orders SET status=?, modified_at=? WHERE id=?",
                (status, _now(), portal_order_id),
            )
        cid = row[0]
        ono = row[1]
    titles = {
        "Approved": (f"Order {ono} approved", "Your order has been approved and will be processed."),
        "Rejected": (
            f"Order {ono} rejected",
            f"Your order was rejected.\nReason: {reason}",
        ),
        "In Dispatch": (f"Order {ono} dispatched", "Your order is on the way / in dispatch."),
        "Invoiced": (f"Order {ono} invoiced", "Your order has been invoiced."),
        "Delivered": (f"Order {ono} delivered", "Your order has been marked delivered."),
        "Cancelled": (f"Order {ono} cancelled", reason or "Your order was cancelled."),
        "Under Review": (f"Order {ono} under review", "Sales is reviewing your order."),
    }
    if status in titles:
        title, default_msg = titles[status]
        notify.notify_distributor(
            cid, f"order_{status.lower().replace(' ', '_')}",
            title, default_msg if status == "Rejected" else (reason or default_msg),
            "portal_order", portal_order_id,
        )


def reject_portal_order(portal_order_id: int, reason: str, *, user_id=None) -> None:
    """Admin reject + notify distributor (requires reason)."""
    update_portal_status(portal_order_id, "Rejected", user_id=user_id, reason=reason)


# Distributor may change orders only before dispatch.
_DISTRIBUTOR_EDITABLE = frozenset({
    "Draft", "Submitted", "Under Review", "Approved", "Rejected",
})
_DISTRIBUTOR_DELETABLE = frozenset({
    "Draft", "Submitted", "Under Review", "Approved", "Rejected", "Cancelled",
})
_DISTRIBUTOR_LOCKED = frozenset({
    "In Dispatch", "Invoiced", "Delivered",
})


def distributor_may_edit_order(status: str | None) -> bool:
    st = (status or "").strip()
    if st in _DISTRIBUTOR_LOCKED:
        return False
    return st in _DISTRIBUTOR_EDITABLE


def distributor_may_delete_order(status: str | None) -> bool:
    st = (status or "").strip()
    if st in _DISTRIBUTOR_LOCKED:
        return False
    return st in _DISTRIBUTOR_DELETABLE


def update_portal_order(
    user: dict,
    order_id: int,
    cart: list[dict],
    notes: str = "",
    *,
    order_date=None,
    delivery_date=None,
    dispatch_town: str = "",
) -> int:
    """Distributor edits own portal order (and linked open sales order)."""
    if not cart:
        raise ValueError("Cart is empty — add at least one product.")
    order = get_portal_order(user, int(order_id))
    if not order:
        raise ValueError("Order not found.")
    assert_distributor_access(user, order["customer_id"])
    if not distributor_may_edit_order(order.get("status")):
        raise ValueError(
            f"Cannot edit order in status '{order.get('status')}'. "
            "Orders can only be edited before dispatch."
        )

    cid = order["customer_id"]
    lines, subtotal, total = _calc_lines(cart, cid)
    ok, msg = check_credit_limit(user, total)
    if not ok:
        raise ValueError(msg)

    town = (dispatch_town or "").strip()
    if not town:
        raise ValueError("Dispatch town is required — where should this order be delivered?")

    od = str(order_date or order.get("order_date") or date.today())[:10]
    dd = str(delivery_date)[:10] if delivery_date else None
    if dd and dd < od:
        raise ValueError("Delivery date cannot be before order date.")

    from database import get_connection
    from db_v15 import ensure_distributor_catalog_schema

    # After edit, send back for sales review (also clears prior rejection).
    new_status = "Under Review" if order.get("sales_order_id") else "Submitted"

    with get_connection() as conn:
        ensure_distributor_catalog_schema(conn)
        conn.execute(
            """UPDATE portal_orders SET
                   order_date=?, delivery_date=?, dispatch_town=?, notes=?,
                   subtotal=?, discount=0, tax=0, total=?,
                   status=?, rejection_reason=NULL, modified_at=?,
                   submitted_at=COALESCE(submitted_at, ?)
               WHERE id=? AND customer_id=?""",
            (
                od, dd, town, notes or "",
                subtotal, total,
                new_status, _now(), _now(),
                int(order_id), cid,
            ),
        )
        conn.execute("DELETE FROM portal_order_items WHERE portal_order_id=?", (int(order_id),))
        for ln in lines:
            conn.execute(
                """INSERT INTO portal_order_items(
                    portal_order_id,product_id,quantity,rate,discount_pct,amount,min_qty)
                   VALUES(?,?,?,?,?,?,?)""",
                (int(order_id), ln["product_id"], ln["quantity"], ln["rate"],
                 ln["discount_pct"], ln["amount"], ln["min_qty"]),
            )

    order = get_portal_order(user, int(order_id))
    so_id = order.get("sales_order_id")
    so_ok = False
    if so_id:
        from database import get_connection, row_to_dict
        with get_connection() as conn:
            so = row_to_dict(conn.execute(
                "SELECT id, status, document_no FROM sales_orders WHERE id=?", (so_id,),
            ).fetchone())
        st = (so or {}).get("status") or ""
        if so and st.lower() not in ("cancelled", "canceled", "closed"):
            _update_linked_sales_order(user, order, lines, int(so_id), so.get("document_no") or "")
            so_ok = True
    if not so_ok:
        new_so = _create_sales_order_draft(user, order, lines)
        _link_sales_order(int(order_id), new_so)
        order = get_portal_order(user, int(order_id))

    prof = get_distributor_profile(user) or {}
    order["customer_name"] = (
        f"{prof.get('customer_code') or ''} — {prof.get('customer_name') or ''}"
    ).strip(" —")
    notify.notify_internal_sales_order(order)
    notify.notify_distributor(
        cid, "order_updated", f"Order {order['order_no']} updated",
        "Your order changes were saved and sent for sales review.",
        "portal_order", int(order_id),
    )
    return int(order_id)


def _update_linked_sales_order(
    user: dict, order: dict, lines: list[dict], so_id: int, document_no: str,
) -> None:
    from db_v3 import save_sales_order
    from database import get_connection
    from db_v15 import ensure_distributor_catalog_schema

    town = (order.get("dispatch_town") or "").strip()
    note_bits = [f"Portal order {order['order_no']} (updated by distributor)"]
    if town:
        note_bits.append(f"Dispatch To: {town}")
    if order.get("delivery_date"):
        note_bits.append(f"Delivery: {order['delivery_date']}")
    if order.get("notes"):
        note_bits.append(str(order["notes"]))
    wh_id = None
    with get_connection() as conn:
        wh = conn.execute("SELECT id FROM warehouses WHERE is_active=1 ORDER BY id LIMIT 1").fetchone()
        wh_id = wh[0] if wh else None
    data = {
        "document_no": document_no,
        "customer_id": order["customer_id"],
        "order_date": order["order_date"],
        "delivery_date": order.get("delivery_date"),
        "warehouse_id": wh_id,
        "status": "open",
        "notes": " | ".join(note_bits),
        "portal_order_id": order["id"],
        "source_channel": "portal",
        "dispatch_town": town or None,
    }
    so_lines = [
        {
            "product_id": ln["product_id"],
            "item_id": ln["product_id"],
            "quantity": ln["quantity"],
            "rate": ln["rate"],
            "discount_pct": float(ln.get("discount_pct") or 0),
            "line_amount": ln["amount"],
            "amount": ln["amount"],
        }
        for ln in lines
    ]
    save_sales_order(
        data, so_lines, so_id=so_id, user_id=user.get("id"), skip_portal_sync=True,
    )
    with get_connection() as conn:
        ensure_distributor_catalog_schema(conn)
        if order.get("delivery_date"):
            conn.execute(
                "UPDATE sales_orders SET delivery_date=? WHERE id=?",
                (str(order["delivery_date"])[:10], so_id),
            )
        if town:
            conn.execute(
                "UPDATE sales_orders SET dispatch_town=? WHERE id=?",
                (town, so_id),
            )


def delete_portal_order(user: dict, order_id: int) -> None:
    """Distributor deletes own order (and linked SO when allowed)."""
    order = get_portal_order(user, int(order_id))
    if not order:
        raise ValueError("Order not found.")
    assert_distributor_access(user, order["customer_id"])
    if not distributor_may_delete_order(order.get("status")):
        raise ValueError(
            f"Cannot delete order in status '{order.get('status')}'. "
            "Orders can only be deleted before dispatch."
        )

    so_id = order.get("sales_order_id")
    ono = order.get("order_no") or f"#{order_id}"
    so_no = (order.get("sales_order_no") or "").strip()
    cid = order["customer_id"]
    order_id = int(order_id)
    total = order.get("total")
    town = (order.get("dispatch_town") or "").strip()

    cust_name = ""
    try:
        from database import get_connection as _gc
        with _gc() as _c:
            crow = _c.execute(
                "SELECT code, name FROM customers WHERE id=?", (cid,),
            ).fetchone()
            if crow:
                cust_name = f"{crow['code']} — {crow['name']}"
            if so_id and not so_no:
                so_row = _c.execute(
                    "SELECT document_no FROM sales_orders WHERE id=?", (int(so_id),),
                ).fetchone()
                if so_row:
                    so_no = (so_row[0] or "").strip()
    except Exception:
        pass
    if not cust_name:
        prof = get_distributor_profile(user) or {}
        cust_name = (
            f"{prof.get('customer_code') or ''} — "
            f"{prof.get('customer_name') or prof.get('business_name') or ''}"
        ).strip(" —") or "distributor"

    from database import get_connection

    with get_connection() as conn:
        if so_id:
            so_id = int(so_id)
            if not so_no:
                so_row = conn.execute(
                    "SELECT document_no FROM sales_orders WHERE id=?", (so_id,),
                ).fetchone()
                if so_row:
                    so_no = (so_row[0] or "").strip()
            linked = conn.execute(
                """SELECT COUNT(*) FROM sales_invoices
                   WHERE order_id=? AND COALESCE(status,'draft') NOT IN ('cancelled','rejected')""",
                (so_id,),
            ).fetchone()[0]
            if linked:
                raise ValueError(
                    "This order is already linked to an invoice or delivery — contact IFS sales."
                )
            delivered = conn.execute(
                """SELECT COALESCE(SUM(COALESCE(delivered_qty,0)),0)
                   FROM sales_order_items WHERE order_id=?""",
                (so_id,),
            ).fetchone()[0]
            if float(delivered or 0) > 0.0001:
                raise ValueError(
                    "This order is already linked to an invoice or delivery — contact IFS sales."
                )
            dn = conn.execute(
                """SELECT COUNT(*) FROM delivery_notes
                   WHERE sales_order_id=? AND LOWER(COALESCE(status,'')) NOT IN ('cancelled','canceled')""",
                (so_id,),
            ).fetchone()[0]
            if dn:
                raise ValueError(
                    "This order is already linked to an invoice or delivery — contact IFS sales."
                )

            # Other portal rows may also point at this SO (duplicate mirrors).
            twin_ids = [
                int(r[0]) for r in conn.execute(
                    "SELECT id FROM portal_orders WHERE sales_order_id=? AND id<>?",
                    (so_id, order_id),
                ).fetchall()
            ]

            # Clear ALL FKs to this SO before delete (portal + delivery notes).
            conn.execute(
                "UPDATE portal_orders SET sales_order_id=NULL, modified_at=? WHERE sales_order_id=?",
                (_now(), so_id),
            )
            conn.execute(
                "UPDATE sales_orders SET portal_order_id=NULL WHERE id=?",
                (so_id,),
            )
            conn.execute(
                "UPDATE delivery_notes SET sales_order_id=NULL WHERE sales_order_id=?",
                (so_id,),
            )
            conn.execute("DELETE FROM sales_order_items WHERE order_id=?", (so_id,))
            conn.execute("DELETE FROM sales_orders WHERE id=?", (so_id,))

            # Remove duplicate portal mirrors that shared the same SO
            for tid in twin_ids:
                conn.execute("DELETE FROM portal_order_items WHERE portal_order_id=?", (tid,))
                conn.execute(
                    "DELETE FROM portal_orders WHERE id=? AND customer_id=?",
                    (tid, cid),
                )

        conn.execute("DELETE FROM portal_order_items WHERE portal_order_id=?", (order_id,))
        conn.execute(
            "DELETE FROM portal_orders WHERE id=? AND customer_id=?",
            (order_id, cid),
        )

    # Distributor confirmation (Notifications page + sidebar)
    dist_msg = f"You deleted order {ono}."
    if so_no:
        dist_msg += f" Linked sales order {so_no} was also removed."
    notify.notify_distributor(
        cid,
        "order_deleted",
        f"Order {ono} deleted",
        dist_msg,
        "portal_order",
        order_id,
    )
    # IFS sales / admin notifications (ERP sidebar)
    try:
        notify.notify_internal_order_deleted({
            "id": order_id,
            "order_no": ono,
            "sales_order_no": so_no,
            "customer_id": cid,
            "customer_name": cust_name,
            "total": total,
            "dispatch_town": town,
        })
    except Exception:
        pass


def sync_portal_order_from_sales_order(
    sales_order_id: int,
    *,
    notify_user: bool = True,
    user_id=None,
) -> bool:
    """
    Keep distributor My Orders in sync with a Sales Order.

    - If a portal order is already linked → update lines/totals/status.
    - If the customer has portal access and no portal order yet → create one
      so ERP-created SOs also appear in the distributor portal.
    """
    from database import get_connection, row_to_dict, rows_to_list, ensure_document_no
    from product_rates_legacy import _implied_line_discount_pct
    from db_v15 import ensure_distributor_catalog_schema

    so_id = int(sales_order_id)
    created_new = False
    with get_connection() as conn:
        ensure_distributor_catalog_schema(conn)
        so = row_to_dict(conn.execute(
            """SELECT so.*,
                      (SELECT po.id FROM portal_orders po
                       WHERE po.sales_order_id=so.id
                          OR po.id=so.portal_order_id
                       LIMIT 1) AS linked_portal_id
               FROM sales_orders so WHERE so.id=?""",
            (so_id,),
        ).fetchone())
        if not so:
            return False

        so_status = (so.get("status") or "").strip().lower()
        if so_status in ("cancelled", "canceled") and not (
            so.get("linked_portal_id") or so.get("portal_order_id")
        ):
            # No need to create a portal mirror for a cancelled internal SO
            return False

        poid = so.get("linked_portal_id") or so.get("portal_order_id")
        portal = None
        if poid:
            portal = row_to_dict(conn.execute(
                "SELECT * FROM portal_orders WHERE id=?", (poid,)
            ).fetchone())
            if not portal:
                poid = None

        # Prefer an existing portal order referenced in SO notes (avoids duplicate mirrors)
        if not poid:
            import re
            m = re.search(
                r"Portal order\s+(POR-\d+)",
                str(so.get("notes") or ""),
                flags=re.IGNORECASE,
            )
            if m:
                portal = row_to_dict(conn.execute(
                    "SELECT * FROM portal_orders WHERE order_no=?",
                    (m.group(1).upper(),),
                ).fetchone())
                if portal:
                    poid = portal["id"]

        if not poid:
            # Create portal mirror only for portal-enabled distributor customers
            cid = so.get("customer_id")
            if not cid:
                return False
            portal_on = conn.execute(
                """SELECT COALESCE(dp.portal_enabled, c.portal_enabled, 0) AS pe
                   FROM customers c
                   LEFT JOIN distributor_profiles dp ON dp.customer_id=c.id
                   WHERE c.id=?""",
                (cid,),
            ).fetchone()
            if not portal_on or int(portal_on[0] or 0) != 1:
                return False
            dist_user = conn.execute(
                """SELECT id FROM users
                   WHERE linked_customer_id=? AND COALESCE(is_active,1)=1
                     AND LOWER(COALESCE(user_type,'')) LIKE 'distributor%'
                   ORDER BY id LIMIT 1""",
                (cid,),
            ).fetchone()
            if not dist_user:
                return False

            # Ensure column exists (older DBs)
            try:
                conn.execute("SELECT discount_pct FROM sales_order_items LIMIT 1")
            except Exception:
                conn.execute(
                    "ALTER TABLE sales_order_items ADD COLUMN discount_pct REAL DEFAULT 0"
                )
            items = rows_to_list(conn.execute(
                """SELECT product_id, quantity, rate, amount,
                          COALESCE(discount_pct, 0) AS discount_pct
                   FROM sales_order_items WHERE order_id=? ORDER BY id""",
                (so_id,),
            ).fetchall())
            if not items:
                return False

            so_no = so.get("document_no") or f"SO#{so_id}"
            order_no = ensure_document_no("POR", None, conn)
            order_date = str(so.get("order_date") or date.today())[:10]
            delivery_date = so.get("delivery_date")
            if delivery_date:
                delivery_date = str(delivery_date)[:10]
            town = (so.get("dispatch_town") or "").strip() or None
            header_disc = float(so.get("discount") or 0)
            tax = float(so.get("tax") or 0)
            total = float(so.get("total") or 0)
            subtotal = float(so.get("subtotal") or 0) or sum(
                float(it.get("amount") or 0) for it in items
            )
            notes_bits = [f"Created by IFS from {so_no}"]
            if (so.get("notes") or "").strip():
                notes_bits.append(str(so["notes"]).strip())
            portal_status = "Cancelled" if so_status in ("cancelled", "canceled") else "Approved"

            cur = conn.execute(
                """INSERT INTO portal_orders(
                    order_no,customer_id,distributor_user_id,order_date,delivery_date,
                    dispatch_town,status,subtotal,discount,tax,total,notes,
                    sales_order_id,submitted_at,approved_at,approved_by,modified_at,source_channel)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    order_no, cid, int(dist_user[0]), order_date, delivery_date,
                    town, portal_status, subtotal, header_disc, tax, total,
                    " | ".join(notes_bits),
                    so_id, _now(), _now(), user_id, _now(), "internal",
                ),
            )
            poid = cur.lastrowid
            for it in items:
                qty = float(it.get("quantity") or 0)
                rate = float(it.get("rate") or 0)
                amt = float(it.get("amount") or 0)
                disc = float(it.get("discount_pct") or 0)
                if disc <= 0.0001:
                    disc = _implied_line_discount_pct(qty, rate, 0, amt, 0)
                conn.execute(
                    """INSERT INTO portal_order_items(
                        portal_order_id,product_id,quantity,rate,discount_pct,amount,min_qty)
                       VALUES(?,?,?,?,?,?,?)""",
                    (poid, int(it["product_id"]), qty, rate, disc, amt, 1),
                )
            conn.execute(
                """UPDATE sales_orders SET
                       portal_order_id=?,
                       source_channel=COALESCE(NULLIF(source_channel,''),'internal')
                   WHERE id=?""",
                (poid, so_id),
            )
            created_new = True
            portal = row_to_dict(conn.execute(
                "SELECT * FROM portal_orders WHERE id=?", (poid,)
            ).fetchone())
            total = float(portal.get("total") or total)
            n_lines = len(items)
            ono = order_no
            so_no_display = so_no
            cid_notify = cid
        else:
            # Ensure column exists (older DBs)
            try:
                conn.execute("SELECT discount_pct FROM sales_order_items LIMIT 1")
            except Exception:
                conn.execute(
                    "ALTER TABLE sales_order_items ADD COLUMN discount_pct REAL DEFAULT 0"
                )
            items = rows_to_list(conn.execute(
                """SELECT product_id, quantity, rate, amount,
                          COALESCE(discount_pct, 0) AS discount_pct
                   FROM sales_order_items WHERE order_id=? ORDER BY id""",
                (so_id,),
            ).fetchall())
            if not items:
                return False

            new_lines = []
            subtotal = 0.0
            for it in items:
                qty = float(it.get("quantity") or 0)
                rate = float(it.get("rate") or 0)
                amt = float(it.get("amount") or 0)
                disc = float(it.get("discount_pct") or 0)
                if disc <= 0.0001:
                    disc = _implied_line_discount_pct(qty, rate, 0, amt, 0)
                subtotal += amt
                new_lines.append({
                    "product_id": int(it["product_id"]),
                    "quantity": qty,
                    "rate": rate,
                    "discount_pct": disc,
                    "amount": amt,
                    "min_qty": 1,
                })

            header_disc = float(so.get("discount") or 0)
            tax = float(so.get("tax") or 0)
            total = float(so.get("total") or subtotal)
            order_date = str(so.get("order_date") or portal.get("order_date") or "")[:10]
            delivery_date = so.get("delivery_date") or portal.get("delivery_date")
            if delivery_date:
                delivery_date = str(delivery_date)[:10]
            town = (so.get("dispatch_town") or portal.get("dispatch_town") or "").strip() or None

            portal_status = portal.get("status") or "Under Review"
            if so_status in ("cancelled", "canceled"):
                portal_status = "Cancelled"
            elif portal_status in ("Submitted", "Draft"):
                portal_status = "Under Review"

            # Ensure reverse link; keep existing channel (portal/internal)
            conn.execute(
                """UPDATE sales_orders SET
                       portal_order_id=?,
                       source_channel=COALESCE(NULLIF(source_channel,''),'internal')
                   WHERE id=?""",
                (poid, so_id),
            )

            has_delivery = conn.execute("PRAGMA table_info(portal_orders)").fetchall()
            delivery_cols = {r[1] for r in has_delivery}

            if "delivery_date" in delivery_cols:
                conn.execute(
                    """UPDATE portal_orders SET
                         sales_order_id=?, order_date=?, delivery_date=?,
                         dispatch_town=COALESCE(?, dispatch_town),
                         subtotal=?, discount=?, tax=?, total=?,
                         status=?, modified_at=?
                       WHERE id=?""",
                    (
                        so_id, order_date, delivery_date, town,
                        subtotal, header_disc, tax, total,
                        portal_status, _now(), poid,
                    ),
                )
            else:
                conn.execute(
                    """UPDATE portal_orders SET
                         sales_order_id=?, order_date=?,
                         subtotal=?, discount=?, tax=?, total=?,
                         status=?, modified_at=?
                       WHERE id=?""",
                    (
                        so_id, order_date,
                        subtotal, header_disc, tax, total,
                        portal_status, _now(), poid,
                    ),
                )

            conn.execute("DELETE FROM portal_order_items WHERE portal_order_id=?", (poid,))
            for ln in new_lines:
                conn.execute(
                    """INSERT INTO portal_order_items(
                        portal_order_id,product_id,quantity,rate,discount_pct,amount,min_qty)
                       VALUES(?,?,?,?,?,?,?)""",
                    (
                        poid, ln["product_id"], ln["quantity"], ln["rate"],
                        ln["discount_pct"], ln["amount"], ln["min_qty"],
                    ),
                )

            ono = portal.get("order_no") or ""
            so_no_display = so.get("document_no") or f"SO#{so_id}"
            cid_notify = portal.get("customer_id")
            n_lines = len(new_lines)

    if notify_user and cid_notify:
        if created_new:
            notify.notify_distributor(
                cid_notify,
                "order_created",
                f"New order {ono}",
                (
                    f"IFS created order {ono} for you (ref {so_no_display}). "
                    f"Total Rs. {total:,.2f} · {n_lines} line(s). "
                    f"Open My Orders to view."
                ),
                "portal_order",
                poid,
            )
        else:
            notify.notify_distributor(
                cid_notify,
                "order_updated",
                f"Order {ono} updated",
                (
                    f"Sales updated your order (ref {so_no_display}). "
                    f"New total Rs. {total:,.2f} · {n_lines} line(s). "
                    f"Open My Orders to view the latest."
                ),
                "portal_order",
                poid,
            )
    return True


def submit_payment_proof(
    user: dict,
    amount: float,
    proof_date: str,
    reference_no: str = "",
    bank_name: str = "",
    notes: str = "",
    portal_order_id=None,
    *,
    file_bytes: bytes | None = None,
    file_name: str | None = None,
) -> int:
    """Distributor submits a payment claim (+ optional bank slip image/PDF)."""
    from pathlib import Path
    import re
    import uuid

    cid = get_distributor_customer_id(user)
    if not cid:
        raise PermissionError("Not linked to a customer.")
    amount = float(amount or 0)
    if amount <= 0:
        raise ValueError("Enter amount paid greater than zero.")

    file_path = None
    if file_bytes:
        if len(file_bytes) > 8 * 1024 * 1024:
            raise ValueError("Slip file too large (max 8 MB).")
        safe = re.sub(r"[^\w.\-]+", "_", (file_name or "slip.bin").strip())[:120] or "slip.bin"
        ext = Path(safe).suffix.lower()
        if ext not in (".pdf", ".png", ".jpg", ".jpeg", ".webp", ".gif"):
            raise ValueError("Attach a PDF or image slip (png/jpg/pdf).")
        root = Path(__file__).resolve().parent.parent / "data" / "portal_payment_proofs" / str(cid)
        root.mkdir(parents=True, exist_ok=True)
        stored = f"{uuid.uuid4().hex}_{safe}"
        dest = root / stored
        dest.write_bytes(file_bytes)
        file_path = str(dest)

    from database import get_connection, rows_to_list
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO portal_payment_proofs(
                customer_id,portal_order_id,proof_date,amount,reference_no,bank_name,notes,
                file_path,status,created_by)
               VALUES(?,?,?,?,?,?,?,?, 'pending',?)""",
            (
                cid, portal_order_id, proof_date, amount, reference_no, bank_name, notes,
                file_path, user["id"],
            ),
        )
        pid = cur.lastrowid

    cust_label = f"Customer #{cid}"
    try:
        prof = get_distributor_profile(user) or {}
        cust_label = f"{prof.get('customer_code') or ''} — {prof.get('customer_name') or cust_label}".strip(" —")
    except Exception:
        pass

    notify.create_notification(
        user_id=None,
        customer_id=cid,
        category="payment_proof",
        title="Payment proof uploaded",
        message=f"Rs. {amount:,.2f} — ref {reference_no or '—'}",
        ref_type="payment_proof",
        ref_id=pid,
    )
    with get_connection() as conn:
        staff = rows_to_list(conn.execute(
            """SELECT id FROM users
               WHERE is_active=1
                 AND LOWER(COALESCE(role,'')) IN (
                     'admin','super_admin','accountant','fin_mgr','accounts'
                 )
               LIMIT 40"""
        ).fetchall())
    msg = (
        f"{cust_label} uploaded payment proof Rs. {amount:,.2f}"
        + (f" · {bank_name}" if bank_name else "")
        + (f" · ref {reference_no}" if reference_no else "")
        + (" · slip attached" if file_path else "")
        + ". Review under Sales → Distributor Orders → Payment Proofs."
    )
    for u in staff:
        notify.create_notification(
            user_id=u["id"],
            category="payment_proof",
            title="Distributor payment proof",
            message=msg,
            ref_type="payment_proof",
            ref_id=pid,
        )
    return pid


def list_payment_proofs(user: dict):
    cid = get_distributor_customer_id(user)
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            """SELECT id, proof_date, amount, reference_no, bank_name, notes, status,
                      CASE WHEN file_path IS NOT NULL AND TRIM(file_path)!='' THEN 1 ELSE 0 END AS has_slip,
                      created_at, reviewed_at
               FROM portal_payment_proofs WHERE customer_id=?
               ORDER BY proof_date DESC, id DESC""",
            (cid,),
        ).fetchall())


def list_all_payment_proofs(*, status: str | None = None, customer_id=None):
    from database import get_connection, rows_to_list
    where, params = ["1=1"], []
    if status and status != "All":
        where.append("pp.status=?")
        params.append(status)
    if customer_id:
        where.append("pp.customer_id=?")
        params.append(customer_id)
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            f"""SELECT pp.*, c.code AS customer_code, c.name AS customer_name,
                       u.username AS uploaded_by
                FROM portal_payment_proofs pp
                JOIN customers c ON c.id=pp.customer_id
                LEFT JOIN users u ON u.id=pp.created_by
                WHERE {' AND '.join(where)}
                ORDER BY
                  CASE pp.status WHEN 'pending' THEN 0 WHEN 'approved' THEN 1 ELSE 2 END,
                  pp.created_at DESC, pp.id DESC""",
            params,
        ).fetchall())


def get_payment_proof(proof_id: int) -> dict | None:
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        return row_to_dict(conn.execute(
            """SELECT pp.*, c.code AS customer_code, c.name AS customer_name
               FROM portal_payment_proofs pp
               JOIN customers c ON c.id=pp.customer_id
               WHERE pp.id=?""",
            (proof_id,),
        ).fetchone())


def review_payment_proof(
    proof_id: int,
    status: str,
    *,
    user_id=None,
    reason: str = "",
) -> None:
    """Approve or reject a distributor payment proof; notify the distributor."""
    status = (status or "").strip().lower()
    if status not in ("approved", "rejected", "pending"):
        raise ValueError("Status must be approved or rejected.")
    reason = (reason or "").strip()
    if status == "rejected" and not reason:
        raise ValueError("Enter a rejection reason for the distributor.")

    from database import get_connection
    with get_connection() as conn:
        row = conn.execute(
            "SELECT customer_id, amount, reference_no, status FROM portal_payment_proofs WHERE id=?",
            (proof_id,),
        ).fetchone()
        if not row:
            raise ValueError("Payment proof not found.")
        conn.execute(
            """UPDATE portal_payment_proofs
               SET status=?, reviewed_by=?, reviewed_at=?, notes=CASE
                     WHEN ?!='' THEN TRIM(COALESCE(notes,'') || char(10) || '[Review] ' || ?)
                     ELSE notes END
               WHERE id=?""",
            (status, user_id, _now(), reason, reason, proof_id),
        )
        cid = int(row[0])
        amount = float(row[1] or 0)
        ref = row[2] or "—"

    if status == "approved":
        title = "Payment proof approved"
        msg = (
            f"Your payment proof Rs. {amount:,.2f} (ref {ref}) was approved by accounts. "
            "Ledger posting is completed by IFS finance if not already reflected."
        )
    elif status == "rejected":
        title = "Payment proof rejected"
        msg = f"Your payment proof Rs. {amount:,.2f} (ref {ref}) was rejected. Reason: {reason}"
    else:
        return
    notify.notify_distributor(cid, f"payment_{status}", title, msg, "payment_proof", proof_id)


def list_customer_invoices(user: dict, *, approved_only: bool = True):
    """Invoices for the signed-in distributor. Default: approved only (portal-safe)."""
    cid = get_distributor_customer_id(user)
    if not cid:
        return []
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='sales_invoices'").fetchone():
            return []
        where = "customer_id=? AND LOWER(COALESCE(status,''))='approved'" if approved_only else "customer_id=?"
        return rows_to_list(conn.execute(
            f"""SELECT id,
                      document_no AS invoice_no,
                      invoice_date AS sale_date,
                      total, paid_amount, status, approval_status
               FROM sales_invoices
               WHERE {where}
               ORDER BY invoice_date DESC, id DESC
               LIMIT 200""",
            (cid,),
        ).fetchall())


def get_my_invoice(user: dict, invoice_id: int) -> dict | None:
    """Load full approved sales invoice belonging to this distributor (lines included)."""
    cid = get_distributor_customer_id(user)
    if not cid:
        raise PermissionError("Not linked to a customer.")
    invoice_id = int(invoice_id)
    from database import get_connection, get_sale
    with get_connection() as conn:
        row = conn.execute(
            """SELECT id, customer_id, status FROM sales_invoices WHERE id=?""",
            (invoice_id,),
        ).fetchone()
        if not row:
            return None
        if int(row["customer_id"]) != int(cid):
            raise PermissionError("This invoice does not belong to your account.")
        if str(row["status"] or "").lower() != "approved":
            raise PermissionError("Only approved invoices can be viewed on the portal.")
    inv = get_sale(invoice_id)
    if inv:
        assert_distributor_access(user, inv["customer_id"])
    return inv


def get_my_ledger(user: dict, from_date=None, to_date=None, *, detailed: bool = False):
    """Customer ledger for the signed-in distributor only (isolation by linked_customer_id)."""
    cid = get_distributor_customer_id(user)
    if not cid:
        raise PermissionError("Distributor account not linked to a customer.")
    assert_distributor_access(user, cid)
    import database as db
    if detailed:
        return db.get_customer_ledger_detailed(cid, from_date, to_date, include_linked=True)
    return db.get_customer_ledger(cid, from_date, to_date, include_linked=True)


def enable_distributor_portal(
    customer_id: int,
    *,
    username: str,
    password: str,
    full_name: str | None = None,
    price_list_id: int | None = None,
    credit_limit: float = 0,
    show_stock: bool = False,
    created_by: int | None = None,
) -> dict:
    """Mark customer as portal distributor and create a linked portal user.

    Returns credentials dict for one-time display to staff.
    """
    import database as db
    from database import get_connection, row_to_dict

    with get_connection() as conn:
        cust = row_to_dict(conn.execute(
            "SELECT * FROM customers WHERE id=?", (customer_id,)
        ).fetchone())
        if not cust:
            raise ValueError("Customer not found.")
        role_row = conn.execute(
            "SELECT id FROM roles WHERE UPPER(code)='DISTRIBUTOR' LIMIT 1"
        ).fetchone()
        role_id = int(role_row[0]) if role_row else None

        pl_id = price_list_id or cust.get("assigned_price_list_id")
        conn.execute(
            """UPDATE customers SET is_distributor=1, portal_enabled=1,
               assigned_price_list_id=COALESCE(?, assigned_price_list_id),
               credit_limit=COALESCE(?, credit_limit)
               WHERE id=?""",
            (pl_id, credit_limit if credit_limit is not None else cust.get("credit_limit"), customer_id),
        )
        conn.execute(
            """INSERT INTO distributor_profiles(
                   customer_id, business_name, contact_name, assigned_price_list_id,
                   credit_limit, show_stock, portal_enabled)
               VALUES(?,?,?,?,?,?,1)
               ON CONFLICT(customer_id) DO UPDATE SET
                   assigned_price_list_id=COALESCE(excluded.assigned_price_list_id, distributor_profiles.assigned_price_list_id),
                   credit_limit=excluded.credit_limit,
                   show_stock=excluded.show_stock,
                   portal_enabled=1,
                   business_name=COALESCE(excluded.business_name, distributor_profiles.business_name)""",
            (
                customer_id,
                cust.get("name"),
                full_name or cust.get("name"),
                pl_id,
                float(credit_limit or 0),
                int(bool(show_stock)),
            ),
        )
        if pl_id:
            try:
                exists_pl = conn.execute(
                    "SELECT 1 FROM distributor_price_lists WHERE customer_id=? AND price_list_id=?",
                    (customer_id, pl_id),
                ).fetchone()
                if not exists_pl:
                    conn.execute(
                        """INSERT INTO distributor_price_lists(customer_id,price_list_id,priority,is_active,created_by)
                           VALUES(?,?,1,1,?)""",
                        (customer_id, pl_id, created_by),
                    )
            except Exception:
                pass

        existing = conn.execute(
            "SELECT id, username FROM users WHERE linked_customer_id=? AND LOWER(COALESCE(user_type,'')) LIKE 'distributor%'",
            (customer_id,),
        ).fetchone()

    display_name = (full_name or cust.get("name") or username).strip()
    if existing:
        db.update_user(
            existing[0],
            display_name,
            "user",
            1,
            password=password,
            modified_by=created_by,
            user_type="distributor",
            linked_customer_id=customer_id,
            role_id=role_id,
        )
        with get_connection() as conn:
            if "must_change_password" in [r[1] for r in conn.execute("PRAGMA table_info(users)")]:
                conn.execute(
                    "UPDATE users SET must_change_password=1 WHERE id=?", (existing[0],)
                )
        user_id = existing[0]
        uname = existing[1]
    else:
        db.add_user(
            username,
            password,
            display_name,
            role="user",
            created_by=created_by,
            user_type="distributor",
            linked_customer_id=customer_id,
            role_id=role_id,
            must_change_password=1,
        )
        with get_connection() as conn:
            user_id = conn.execute(
                "SELECT id FROM users WHERE LOWER(username)=LOWER(?)", (username,)
            ).fetchone()[0]
        uname = username

    return {
        "user_id": user_id,
        "username": uname,
        "password": password,
        "customer_id": customer_id,
        "customer_code": cust.get("code"),
        "customer_name": cust.get("name"),
        "must_change_password": True,
    }


def update_distributor_portal_settings(
    customer_id: int,
    *,
    credit_limit: float | None = None,
    price_list_id: int | None = None,
    show_stock: bool | None = None,
    modified_by: int | None = None,
) -> dict:
    """Update credit / price list / show-stock without touching portal password."""
    from database import get_connection, row_to_dict

    with get_connection() as conn:
        cust = row_to_dict(conn.execute(
            "SELECT * FROM customers WHERE id=?", (customer_id,)
        ).fetchone())
        if not cust:
            raise ValueError("Customer not found.")

        sets = ["is_distributor=1", "portal_enabled=1"]
        params: list = []
        if credit_limit is not None:
            sets.append("credit_limit=?")
            params.append(float(credit_limit))
        if price_list_id is not None:
            sets.append("assigned_price_list_id=?")
            params.append(int(price_list_id))
        params.append(customer_id)
        conn.execute(f"UPDATE customers SET {', '.join(sets)} WHERE id=?", params)

        # Upsert distributor_profiles
        pl_id = price_list_id if price_list_id is not None else cust.get("assigned_price_list_id")
        cr = float(credit_limit) if credit_limit is not None else float(cust.get("credit_limit") or 0)
        stock = int(bool(show_stock)) if show_stock is not None else None
        existing = conn.execute(
            "SELECT id, show_stock FROM distributor_profiles WHERE customer_id=?",
            (customer_id,),
        ).fetchone()
        if existing:
            stock_val = stock if stock is not None else int(existing["show_stock"] or 0)
            conn.execute(
                """UPDATE distributor_profiles SET
                       assigned_price_list_id=COALESCE(?, assigned_price_list_id),
                       credit_limit=?,
                       show_stock=?,
                       portal_enabled=1
                   WHERE customer_id=?""",
                (pl_id, cr, stock_val, customer_id),
            )
        else:
            conn.execute(
                """INSERT INTO distributor_profiles(
                       customer_id, business_name, assigned_price_list_id,
                       credit_limit, show_stock, portal_enabled)
                   VALUES(?,?,?,?,?,1)""",
                (customer_id, cust.get("name"), pl_id, cr, int(bool(show_stock))),
            )
        if pl_id:
            try:
                exists_pl = conn.execute(
                    "SELECT 1 FROM distributor_price_lists WHERE customer_id=? AND price_list_id=?",
                    (customer_id, pl_id),
                ).fetchone()
                if not exists_pl:
                    conn.execute(
                        """INSERT INTO distributor_price_lists(customer_id,price_list_id,priority,is_active,created_by)
                           VALUES(?,?,1,1,?)""",
                        (customer_id, pl_id, modified_by),
                    )
            except Exception:
                pass

        refreshed = row_to_dict(conn.execute(
            """SELECT c.id AS customer_id, c.code, c.name, c.credit_limit,
                      c.assigned_price_list_id, COALESCE(dp.show_stock,0) AS show_stock
               FROM customers c
               LEFT JOIN distributor_profiles dp ON dp.customer_id=c.id
               WHERE c.id=?""",
            (customer_id,),
        ).fetchone())
    return refreshed or {}


def get_customer_portal_profile(customer_id: int) -> dict | None:
    """Staff view of contacts the distributor maintains on portal Profile."""
    if not customer_id:
        return None
    from database import get_connection, row_to_dict
    from db_v15 import ensure_distributor_catalog_schema
    with get_connection() as conn:
        ensure_distributor_catalog_schema(conn)
        row = conn.execute(
            """SELECT c.id AS customer_id, c.code AS customer_code, c.name AS customer_name,
                      c.phone, c.email, c.contact_person, c.city, c.province, c.address,
                      c.ntn, c.strn,
                      COALESCE(c.dispatch_phone, dp.dispatch_phone) AS dispatch_phone,
                      COALESCE(c.accounts_phone, dp.accounts_phone) AS accounts_phone,
                      COALESCE(c.owner_phone, dp.owner_phone) AS owner_phone,
                      c.modified_at AS customer_modified_at,
                      dp.modified_at AS profile_modified_at
               FROM customers c
               LEFT JOIN distributor_profiles dp ON dp.customer_id=c.id
               WHERE c.id=?""",
            (customer_id,),
        ).fetchone()
        return row_to_dict(row) if row else None


def list_existing_portals() -> list[dict]:
    """Distributor portal logins already set up (for staff overview)."""
    from database import get_connection, rows_to_list
    from db_v15 import ensure_distributor_catalog_schema
    with get_connection() as conn:
        ensure_distributor_catalog_schema(conn)
        return rows_to_list(conn.execute(
            """
            SELECT u.id AS user_id, u.username, u.full_name, u.is_active,
                   u.must_change_password, u.last_login_at, u.user_type,
                   c.id AS customer_id, c.code AS customer_code, c.name AS customer_name,
                   c.phone, c.email, c.contact_person, c.city,
                   COALESCE(c.dispatch_phone, dp.dispatch_phone) AS dispatch_phone,
                   COALESCE(c.accounts_phone, dp.accounts_phone) AS accounts_phone,
                   COALESCE(c.owner_phone, dp.owner_phone) AS owner_phone,
                   COALESCE(c.portal_enabled, 0) AS portal_enabled,
                   COALESCE(c.is_distributor, 0) AS is_distributor,
                   COALESCE(c.credit_limit, 0) AS credit_limit,
                   pl.code AS price_list_code, pl.name AS price_list_name,
                   (SELECT COUNT(*) FROM distributor_catalog_items d
                    WHERE d.customer_id=c.id AND COALESCE(d.is_active,1)=1) AS catalog_items
            FROM users u
            JOIN customers c ON c.id = u.linked_customer_id
            LEFT JOIN distributor_profiles dp ON dp.customer_id = c.id
            LEFT JOIN price_lists pl ON pl.id = COALESCE(
                dp.assigned_price_list_id,
                c.assigned_price_list_id
            )
            WHERE LOWER(COALESCE(u.user_type,'')) LIKE 'distributor%'
              AND u.linked_customer_id IS NOT NULL
            ORDER BY c.code, u.username
            """
        ).fetchall())


def set_portal_user_active(user_id: int, is_active: bool, *, modified_by: int | None = None) -> None:
    from database import get_connection
    with get_connection() as conn:
        row = conn.execute(
            """SELECT id FROM users
               WHERE id=? AND LOWER(COALESCE(user_type,'')) LIKE 'distributor%'""",
            (user_id,),
        ).fetchone()
        if not row:
            raise ValueError("Portal user not found.")
        conn.execute(
            "UPDATE users SET is_active=?, modified_by=?, modified_at=datetime('now') WHERE id=?",
            (int(bool(is_active)), modified_by, user_id),
        )


def save_portal_cart(
    user: dict,
    cart: list[dict],
    *,
    notes: str = "",
    order_date=None,
    delivery_date=None,
    dispatch_town: str = "",
) -> None:
    """Persist cart draft so distributor can return later (Save to cart)."""
    import json
    from database import get_connection
    from db_v15 import ensure_distributor_catalog_schema

    uid = user.get("id")
    if not uid:
        raise ValueError("Not signed in.")
    cid = get_distributor_customer_id(user)
    payload = json.dumps(cart or [], ensure_ascii=False)
    with get_connection() as conn:
        ensure_distributor_catalog_schema(conn)
        conn.execute(
            """INSERT INTO portal_cart_drafts(
                 user_id, customer_id, cart_json, notes, order_date, delivery_date, dispatch_town, saved_at)
               VALUES(?,?,?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                 customer_id=excluded.customer_id,
                 cart_json=excluded.cart_json,
                 notes=excluded.notes,
                 order_date=excluded.order_date,
                 delivery_date=excluded.delivery_date,
                 dispatch_town=excluded.dispatch_town,
                 saved_at=excluded.saved_at""",
            (
                uid, cid, payload, notes or "",
                str(order_date)[:10] if order_date else None,
                str(delivery_date)[:10] if delivery_date else None,
                (dispatch_town or "").strip() or None,
                _now(),
            ),
        )


def load_portal_cart(user: dict) -> dict:
    """Load saved cart draft. Returns cart + notes + dates + dispatch_town."""
    import json
    from database import get_connection, row_to_dict
    from db_v15 import ensure_distributor_catalog_schema

    uid = user.get("id")
    empty = {
        "cart": [], "notes": "", "order_date": None, "delivery_date": None,
        "dispatch_town": "", "saved_at": None,
    }
    if not uid:
        return empty
    with get_connection() as conn:
        ensure_distributor_catalog_schema(conn)
        row = row_to_dict(conn.execute(
            "SELECT * FROM portal_cart_drafts WHERE user_id=?", (uid,)
        ).fetchone())
    if not row:
        return empty
    try:
        cart = json.loads(row.get("cart_json") or "[]")
        if not isinstance(cart, list):
            cart = []
    except Exception:
        cart = []
    return {
        "cart": cart,
        "notes": row.get("notes") or "",
        "order_date": row.get("order_date"),
        "delivery_date": row.get("delivery_date"),
        "dispatch_town": row.get("dispatch_town") or "",
        "saved_at": row.get("saved_at"),
    }


def clear_portal_cart(user: dict) -> None:
    from database import get_connection
    uid = user.get("id")
    if not uid:
        return
    with get_connection() as conn:
        if conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='portal_cart_drafts'"
        ).fetchone():
            conn.execute("DELETE FROM portal_cart_drafts WHERE user_id=?", (uid,))

