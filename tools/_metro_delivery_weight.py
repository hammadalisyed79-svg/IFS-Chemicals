"""Metro pending invoices — delivered vs pending weight."""
from __future__ import annotations

import json
from datetime import datetime

import database as db


def main():
    report = {"when": datetime.now().isoformat(timespec="seconds"), "customers": [], "invoices": [], "orders": [], "summary": {}}
    with db.get_connection() as c:
        # Detect weight columns on sales invoice items
        sii_cols = {r[1] for r in c.execute("PRAGMA table_info(sales_invoice_items)").fetchall()}
        si_cols = {r[1] for r in c.execute("PRAGMA table_info(sales_invoices)").fetchall()}
        soi_cols = {r[1] for r in c.execute("PRAGMA table_info(sales_order_items)").fetchall()}
        so_cols = {r[1] for r in c.execute("PRAGMA table_info(sales_orders)").fetchall()}
        report["schema"] = {
            "sales_invoice_items": sorted(sii_cols),
            "sales_invoices": sorted(si_cols),
            "sales_order_items": sorted(soi_cols),
        }

        custs = c.execute(
            """SELECT id, code, name, city, is_active
               FROM customers
               WHERE UPPER(name) LIKE '%METRO%' OR UPPER(code) LIKE '%METRO%'
               ORDER BY code"""
        ).fetchall()
        report["customers"] = [dict(r) for r in custs]
        if not custs:
            print("No Metro customers found")
            return
        ids = [int(r["id"]) for r in custs]
        placeholders = ",".join("?" * len(ids))

        # Pending / open invoices for Metro
        # Statuses that mean not fully closed
        inv_sql = f"""
            SELECT si.id, si.document_no, si.invoice_date, si.customer_id, c.code AS customer_code,
                   c.name AS customer_name, si.status, si.total, si.paid_amount,
                   COALESCE(si.warehouse_id, '') AS warehouse_id
            FROM sales_invoices si
            JOIN customers c ON c.id = si.customer_id
            WHERE si.customer_id IN ({placeholders})
            ORDER BY si.invoice_date DESC, si.id DESC
        """
        invoices = [dict(r) for r in c.execute(inv_sql, ids).fetchall()]

        # Weight from invoice lines
        wt_expr = "0"
        if "net_weight" in sii_cols:
            wt_expr = "COALESCE(SUM(sii.net_weight),0)"
        elif "weight" in sii_cols:
            wt_expr = "COALESCE(SUM(sii.weight),0)"

        qty_expr = "COALESCE(SUM(sii.quantity),0)" if "quantity" in sii_cols else "0"

        for inv in invoices:
            line = c.execute(
                f"""SELECT {qty_expr} AS qty, {wt_expr} AS net_kg,
                           COUNT(*) AS line_count
                    FROM sales_invoice_items sii
                    WHERE sii.invoice_id=?""",
                (inv["id"],),
            ).fetchone()
            inv["qty"] = float(line["qty"] or 0)
            inv["net_kg"] = float(line["net_kg"] or 0)
            inv["line_count"] = int(line["line_count"] or 0)

            # Weight slips linked?
            if "weight_slip_id" in si_cols and inv.get("weight_slip_id"):
                pass
            # Check weight_slips table linkage
            try:
                ws_cols = {r[1] for r in c.execute("PRAGMA table_info(weight_slips)").fetchall()}
            except Exception:
                ws_cols = set()
            if ws_cols:
                # common link patterns
                ws = None
                if "invoice_id" in ws_cols:
                    ws = c.execute(
                        "SELECT COALESCE(SUM(net_weight),0) FROM weight_slips WHERE invoice_id=?",
                        (inv["id"],),
                    ).fetchone()
                elif "sales_invoice_id" in ws_cols:
                    ws = c.execute(
                        "SELECT COALESCE(SUM(net_weight),0) FROM weight_slips WHERE sales_invoice_id=?",
                        (inv["id"],),
                    ).fetchone()
                if ws:
                    inv["weight_slip_kg"] = float(ws[0] or 0)

        report["invoices"] = invoices

        # Pending by status
        pending_statuses = {"draft", "pending", "submitted", "awaiting_approval", "approved", "unpaid", "partial", "posted"}
        # User said "metro invoices are pending" — likely approval pending or unpaid.
        # Show all, but highlight non-cancelled.

        active = [i for i in invoices if str(i.get("status") or "").lower() not in ("cancelled", "rejected", "void")]
        pending_approval = [
            i for i in active
            if str(i.get("status") or "").lower() in ("draft", "pending", "submitted", "awaiting_approval")
        ]
        # Also check approval workflow fields
        if "approval_status" in si_cols:
            for i in active:
                # reload approval
                pass

        # Sales orders for Metro with pending delivery
        orders = []
        if so_cols:
            so_rows = c.execute(
                f"""SELECT so.id, so.document_no, so.order_date, so.status, so.customer_id,
                           c.code AS customer_code, c.name AS customer_name, so.total
                    FROM sales_orders so
                    JOIN customers c ON c.id=so.customer_id
                    WHERE so.customer_id IN ({placeholders})
                    ORDER BY so.id DESC""",
                ids,
            ).fetchall()
            for so in so_rows:
                so = dict(so)
                # pending qty/weight from order items + product standard_weight
                if "delivered_qty" in soi_cols:
                    row = c.execute(
                        """SELECT
                              COALESCE(SUM(soi.quantity),0) AS ordered_qty,
                              COALESCE(SUM(COALESCE(soi.delivered_qty,0)),0) AS delivered_qty,
                              COALESCE(SUM(soi.quantity - COALESCE(soi.delivered_qty,0)),0) AS pending_qty,
                              COALESCE(SUM(
                                (soi.quantity - COALESCE(soi.delivered_qty,0)) * COALESCE(p.standard_weight,0)
                              ),0) AS pending_kg,
                              COALESCE(SUM(
                                COALESCE(soi.delivered_qty,0) * COALESCE(p.standard_weight,0)
                              ),0) AS delivered_kg,
                              COALESCE(SUM(soi.quantity * COALESCE(p.standard_weight,0)),0) AS ordered_kg
                           FROM sales_order_items soi
                           LEFT JOIN products p ON p.id = soi.product_id
                           WHERE soi.order_id=?""",
                        (so["id"],),
                    ).fetchone()
                    so.update({k: float(row[k] or 0) for k in row.keys()})
                orders.append(so)
        report["orders"] = orders

        # Gate passes / dispatches to Metro?
        gp_tables = [
            r[0]
            for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%gate%'"
            ).fetchall()
        ]
        report["gate_pass_tables"] = gp_tables

        # Summary
        def sumf(rows, key):
            return round(sum(float(r.get(key) or 0) for r in rows), 3)

        active_inv = [i for i in invoices if str(i.get("status") or "").lower() not in ("cancelled", "rejected", "void")]
        pending_inv = [
            i
            for i in active_inv
            if str(i.get("status") or "").lower()
            in ("draft", "pending", "submitted", "awaiting_approval", "pending_approval")
        ]
        # unpaid-ish
        unpaid_inv = []
        for i in active_inv:
            total = float(i.get("total") or 0)
            paid = float(i.get("paid_amount") or 0)
            st = str(i.get("status") or "").lower()
            if st in ("approved", "posted") and paid + 0.01 < total:
                unpaid_inv.append(i)

        open_orders = [
            o
            for o in orders
            if str(o.get("status") or "").lower() in ("open", "partial") and float(o.get("pending_qty") or 0) > 0
        ]

        report["summary"] = {
            "metro_customers": len(custs),
            "all_invoices": len(invoices),
            "active_invoices": len(active_inv),
            "pending_approval_invoices": len(pending_inv),
            "unpaid_approved_invoices": len(unpaid_inv),
            "active_invoice_net_kg": sumf(active_inv, "net_kg"),
            "pending_approval_net_kg": sumf(pending_inv, "net_kg"),
            "unpaid_approved_net_kg": sumf(unpaid_inv, "net_kg"),
            "open_partial_orders": len(open_orders),
            "order_ordered_kg": sumf(orders, "ordered_kg"),
            "order_delivered_kg": sumf(orders, "delivered_kg"),
            "order_pending_kg": sumf(open_orders, "pending_kg"),
            "order_delivered_qty": sumf(orders, "delivered_qty"),
            "order_pending_qty": sumf(open_orders, "pending_qty"),
        }

        # Status breakdown of invoices
        by_status = {}
        for i in invoices:
            st = str(i.get("status") or "(blank)")
            by_status.setdefault(st, {"count": 0, "net_kg": 0.0, "total": 0.0})
            by_status[st]["count"] += 1
            by_status[st]["net_kg"] += float(i.get("net_kg") or 0)
            by_status[st]["total"] += float(i.get("total") or 0)
        for st, v in by_status.items():
            v["net_kg"] = round(v["net_kg"], 3)
            v["total"] = round(v["total"], 2)
        report["invoice_status_breakdown"] = by_status

    out = "reports/metro_delivery_weight_2026-08-22.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print("CUSTOMERS")
    for c in report["customers"]:
        print(f"  {c['code']} — {c['name']} (id={c['id']})")
    print("\nSUMMARY")
    print(json.dumps(report["summary"], indent=2))
    print("\nINVOICE STATUS BREAKDOWN")
    print(json.dumps(report["invoice_status_breakdown"], indent=2))
    print("\nPENDING APPROVAL INVOICES")
    for i in report["invoices"]:
        st = str(i.get("status") or "").lower()
        if st in ("draft", "pending", "submitted", "awaiting_approval", "pending_approval"):
            print(
                f"  {i['document_no']} | {i['invoice_date']} | {i['status']} | "
                f"qty={i['qty']:,.3f} | kg={i['net_kg']:,.3f} | total={float(i['total'] or 0):,.2f} | {i['customer_name']}"
            )
    print("\nOPEN/PARTIAL SALES ORDERS")
    for o in report["orders"]:
        if str(o.get("status") or "").lower() in ("open", "partial") and float(o.get("pending_qty") or 0) > 0:
            print(
                f"  {o['document_no']} | {o['status']} | ordered_kg={o.get('ordered_kg',0):,.3f} | "
                f"delivered_kg={o.get('delivered_kg',0):,.3f} | pending_kg={o.get('pending_kg',0):,.3f} | "
                f"delivered_qty={o.get('delivered_qty',0):,.3f} | pending_qty={o.get('pending_qty',0):,.3f}"
            )
    print("\nALL ACTIVE INVOICES (recent 30)")
    active = [
        i
        for i in report["invoices"]
        if str(i.get("status") or "").lower() not in ("cancelled", "rejected", "void")
    ][:30]
    for i in active:
        print(
            f"  {i['document_no']} | {i['invoice_date']} | {i['status']} | "
            f"kg={i['net_kg']:,.3f} | qty={i['qty']:,.3f} | total={float(i['total'] or 0):,.2f}"
        )
    print("WROTE", out)


if __name__ == "__main__":
    main()
