"""V15 in-app notifications."""

from __future__ import annotations

from datetime import datetime


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def create_notification(
    *,
    user_id=None,
    customer_id=None,
    category: str,
    title: str,
    message: str = "",
    ref_type: str | None = None,
    ref_id=None,
) -> int | None:
    from database import get_connection
    with get_connection() as conn:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='erp_notifications'"
        ).fetchone():
            return None
        cur = conn.execute(
            """INSERT INTO erp_notifications(user_id,customer_id,category,title,message,ref_type,ref_id)
               VALUES(?,?,?,?,?,?,?)""",
            (user_id, customer_id, category, title, message, ref_type, ref_id),
        )
        return cur.lastrowid


def get_notifications_for_user(user_id: int, *, unread_only: bool = False, limit: int = 50):
    from database import get_connection, rows_to_list
    where = "user_id=?"
    params: list = [user_id]
    if unread_only:
        where += " AND is_read=0"
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            f"""SELECT * FROM erp_notifications WHERE {where}
                ORDER BY created_at DESC LIMIT ?""",
            params + [limit],
        ).fetchall())


def get_notifications_for_customer(customer_id: int, *, unread_only: bool = False, limit: int = 50):
    from database import get_connection, rows_to_list
    where = "customer_id=?"
    params: list = [customer_id]
    if unread_only:
        where += " AND is_read=0"
    with get_connection() as conn:
        return rows_to_list(conn.execute(
            f"""SELECT * FROM erp_notifications WHERE {where}
                ORDER BY created_at DESC LIMIT ?""",
            params + [limit],
        ).fetchall())


def mark_notification_read(notification_id: int, user_id: int | None = None) -> None:
    from database import get_connection
    with get_connection() as conn:
        if user_id:
            conn.execute(
                "UPDATE erp_notifications SET is_read=1 WHERE id=? AND user_id=?",
                (notification_id, user_id),
            )
        else:
            conn.execute("UPDATE erp_notifications SET is_read=1 WHERE id=?", (notification_id,))


def mark_all_read(user_id: int) -> None:
    from database import get_connection
    with get_connection() as conn:
        conn.execute("UPDATE erp_notifications SET is_read=1 WHERE user_id=?", (user_id,))


def notify_internal_sales_order(portal_order: dict) -> None:
    """Alert internal sales/admin staff when a distributor submits a portal order."""
    from database import get_connection, rows_to_list
    users = _internal_sales_notify_users()
    with get_connection() as conn:
        cust_name = portal_order.get("customer_name")
        if not cust_name and portal_order.get("customer_id"):
            row = conn.execute(
                "SELECT name, code FROM customers WHERE id=?",
                (portal_order["customer_id"],),
            ).fetchone()
            if row:
                cust_name = f"{row['code']} — {row['name']}"
    ono = portal_order.get("order_no") or "#"
    title = f"New distributor order {ono}"
    bits = [
        f"From {cust_name or 'distributor'}",
        f"total Rs. {float(portal_order.get('total') or 0):,.2f}",
    ]
    if portal_order.get("order_date"):
        bits.append(f"order date {portal_order['order_date']}")
    if portal_order.get("delivery_date"):
        bits.append(f"delivery {portal_order['delivery_date']}")
    if portal_order.get("dispatch_town"):
        bits.append(f"dispatch to {portal_order['dispatch_town']}")
    msg = " — ".join(bits)
    for u in users:
        create_notification(
            user_id=u["id"],
            customer_id=portal_order.get("customer_id"),
            category="portal_order",
            title=title,
            message=msg,
            ref_type="portal_order",
            ref_id=portal_order.get("id"),
        )


def _internal_sales_notify_users() -> list[dict]:
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        users = rows_to_list(conn.execute(
            """SELECT DISTINCT u.id FROM users u
               LEFT JOIN roles r ON r.id=u.role_id
               WHERE u.is_active=1
                 AND LOWER(COALESCE(u.user_type,'internal')) NOT LIKE 'distributor%'
                 AND (
                   LOWER(COALESCE(u.role,''))='admin'
                   OR UPPER(COALESCE(r.code,'')) IN (
                     'SALES_MGR','SALES_OFF','GM','SUPER_ADMIN','ADMIN','DIRECTOR'
                   )
                 )"""
        ).fetchall())
        if not users:
            users = rows_to_list(conn.execute(
                """SELECT id FROM users WHERE is_active=1
                   AND LOWER(COALESCE(user_type,'internal')) NOT LIKE 'distributor%'
                   AND LOWER(COALESCE(role,''))='admin'"""
            ).fetchall())
    return users


def notify_internal_order_deleted(info: dict) -> None:
    """Alert IFS sales staff when a distributor deletes a portal order."""
    users = _internal_sales_notify_users()
    ono = (info.get("order_no") or "#").strip()
    so_no = (info.get("sales_order_no") or "").strip()
    cust = (info.get("customer_name") or "distributor").strip()
    title = f"Order {ono} deleted by distributor"
    bits = [f"Distributor: {cust}"]
    if so_no:
        bits.append(f"Sales order {so_no} also removed")
    total = info.get("total")
    if total is not None:
        try:
            bits.append(f"total was Rs. {float(total):,.2f}")
        except (TypeError, ValueError):
            pass
    if info.get("dispatch_town"):
        bits.append(f"dispatch {info['dispatch_town']}")
    msg = " — ".join(bits)
    for u in users:
        create_notification(
            user_id=u["id"],
            customer_id=info.get("customer_id"),
            category="order_deleted",
            title=title,
            message=msg,
            ref_type="portal_order",
            ref_id=info.get("id"),
        )


def notify_distributor(customer_id: int, category: str, title: str, message: str = "",
                     ref_type: str | None = None, ref_id=None) -> None:
    from database import get_connection, rows_to_list
    with get_connection() as conn:
        users = rows_to_list(conn.execute(
            """SELECT id FROM users WHERE is_active=1 AND linked_customer_id=?
               AND user_type IN ('distributor','distributor_staff')""",
            (customer_id,),
        ).fetchall())
    for u in users:
        create_notification(
            user_id=u["id"],
            customer_id=customer_id,
            category=category,
            title=title,
            message=message,
            ref_type=ref_type,
            ref_id=ref_id,
        )


def notify_customer_dispatch(
    customer_id: int,
    *,
    title: str,
    message: str = "",
    ref_type: str = "dispatch",
    ref_id=None,
) -> None:
    """Notify portal distributor when their order/invoice is dispatched."""
    if not customer_id:
        return
    notify_distributor(
        int(customer_id),
        "dispatch",
        title,
        message,
        ref_type=ref_type,
        ref_id=ref_id,
    )


def notify_sale_invoice_dispatched(invoice_id: int, *, gate_pass_no: str | None = None) -> None:
    """When a sales invoice is dispatched (gate pass / outward), notify the customer."""
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        inv = row_to_dict(conn.execute(
            """SELECT s.id, s.document_no, s.customer_id, s.total, s.order_id,
                      c.name AS customer_name, c.code AS customer_code,
                      COALESCE(c.is_distributor,0) AS is_distributor,
                      COALESCE(c.portal_enabled,0) AS portal_enabled
               FROM sales_invoices s
               LEFT JOIN customers c ON c.id=s.customer_id
               WHERE s.id=?""",
            (invoice_id,),
        ).fetchone())
        if not inv or not inv.get("customer_id"):
            return
        if not _customer_has_portal(conn, inv["customer_id"], inv):
            return

        portal_order = _find_portal_order_for_invoice(conn, invoice_id, inv.get("order_id"))
        if portal_order:
            conn.execute(
                """UPDATE portal_orders SET status='In Dispatch', modified_at=?
                   WHERE id=? AND status NOT IN ('Delivered','Cancelled','Rejected')""",
                (_now(), portal_order["id"]),
            )

    inv_no = inv.get("document_no") or invoice_id
    gp = f" Gate pass {gate_pass_no}." if gate_pass_no else ""
    title = f"Dispatched — invoice {inv_no}"
    msg = (
        f"Your goods have been dispatched (invoice {inv_no})."
        + gp
        + (f" Portal order {portal_order['order_no']}." if portal_order else "")
    )
    notify_customer_dispatch(
        inv["customer_id"],
        title=title,
        message=msg,
        ref_type="sales_invoice",
        ref_id=invoice_id,
    )
    if portal_order:
        notify_distributor(
            inv["customer_id"],
            "order_in_dispatch",
            f"Order {portal_order['order_no']} in dispatch",
            msg,
            ref_type="portal_order",
            ref_id=portal_order["id"],
        )


def _customer_has_portal(conn, customer_id: int, row: dict | None = None) -> bool:
    if not customer_id:
        return False
    portal_users = conn.execute(
        """SELECT COUNT(*) FROM users
           WHERE is_active=1 AND linked_customer_id=?
             AND user_type IN ('distributor','distributor_staff')""",
        (customer_id,),
    ).fetchone()[0]
    if portal_users:
        return True
    if row and (row.get("is_distributor") or row.get("portal_enabled")):
        return True
    cust = conn.execute(
        """SELECT COALESCE(is_distributor,0), COALESCE(portal_enabled,0)
           FROM customers WHERE id=?""",
        (customer_id,),
    ).fetchone()
    return bool(cust and (cust[0] or cust[1]))


def _find_portal_order_for_invoice(conn, invoice_id: int, order_id=None) -> dict | None:
    """Resolve portal order from sales invoice → sales order (SO link optional paths)."""
    from database import row_to_dict

    if order_id:
        po = row_to_dict(conn.execute(
            """SELECT id, order_no, status FROM portal_orders
               WHERE sales_order_id=? OR id=(
                 SELECT portal_order_id FROM sales_orders WHERE id=?
               )
               LIMIT 1""",
            (order_id, order_id),
        ).fetchone())
        if po:
            return po
    return row_to_dict(conn.execute(
        """SELECT po.id, po.order_no, po.status
           FROM portal_orders po
           JOIN sales_orders so ON so.portal_order_id=po.id OR po.sales_order_id=so.id
           JOIN sales_invoices si ON si.order_id=so.id
           WHERE si.id=?
           LIMIT 1""",
        (invoice_id,),
    ).fetchone())


def notify_gate_pass_dispatched(gate_pass_id: int) -> None:
    """
    Notify portal customer that an outward gate pass was issued.
    Works with or without a linked sales / portal order — only needs a customer.
    """
    from database import get_connection, row_to_dict

    with get_connection() as conn:
        gp = row_to_dict(conn.execute(
            """SELECT gp.*,
                      si.document_no AS sales_invoice_no,
                      si.order_id AS sales_order_id,
                      si.customer_id AS inv_customer_id,
                      c.name AS customer_name, c.code AS customer_code,
                      COALESCE(c.is_distributor,0) AS is_distributor,
                      COALESCE(c.portal_enabled,0) AS portal_enabled
               FROM gate_passes gp
               LEFT JOIN sales_invoices si ON si.id=gp.sales_invoice_id
               LEFT JOIN customers c ON c.id=COALESCE(gp.customer_id, si.customer_id)
               WHERE gp.id=?""",
            (gate_pass_id,),
        ).fetchone())
        if not gp:
            return
        ptype = (gp.get("pass_type") or "").strip().lower()
        if ptype not in ("material_out", "fg_dispatch"):
            return

        customer_id = gp.get("customer_id") or gp.get("inv_customer_id")
        if not customer_id:
            return
        if not _customer_has_portal(conn, int(customer_id), gp):
            return

        inv_id = gp.get("sales_invoice_id")
        portal_order = None
        if inv_id:
            portal_order = _find_portal_order_for_invoice(
                conn, int(inv_id), gp.get("sales_order_id"),
            )
        if not portal_order and gp.get("sales_order_id"):
            portal_order = row_to_dict(conn.execute(
                """SELECT id, order_no, status FROM portal_orders
                   WHERE sales_order_id=? OR id=(
                     SELECT portal_order_id FROM sales_orders WHERE id=?
                   )
                   LIMIT 1""",
                (gp["sales_order_id"], gp["sales_order_id"]),
            ).fetchone())

        if portal_order:
            conn.execute(
                """UPDATE portal_orders SET status='In Dispatch', modified_at=?
                   WHERE id=? AND status NOT IN ('Delivered','Cancelled','Rejected')""",
                (_now(), portal_order["id"]),
            )

        gp_no = gp.get("document_no") or f"#{gate_pass_id}"
        inv_no = gp.get("sales_invoice_no")
        vehicle = (gp.get("vehicle_no") or "").strip()
        bits = [f"Gate pass {gp_no} issued — your goods are dispatched."]
        if inv_no:
            bits.append(f"Invoice {inv_no}.")
        if portal_order:
            bits.append(f"Order {portal_order['order_no']}.")
        if vehicle:
            bits.append(f"Vehicle {vehicle}.")
        msg = " ".join(bits)
        title = f"Dispatched — gate pass {gp_no}"

    notify_customer_dispatch(
        int(customer_id),
        title=title,
        message=msg,
        ref_type="gate_pass",
        ref_id=gate_pass_id,
    )
