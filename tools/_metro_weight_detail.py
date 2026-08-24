"""Metro — reconcile draft invoice weights with weight slips / gate passes."""
from __future__ import annotations

import json
import database as db

METRO_ID = 826


def main():
    with db.get_connection() as c:
        # Invoice lines detail
        print("=== PENDING DRAFT INVOICE LINES ===")
        rows = c.execute(
            """SELECT si.document_no, si.invoice_date, si.status,
                      p.code AS product_code, p.name AS product_name,
                      sii.quantity, sii.net_weight, sii.gross_weight, sii.tare_weight,
                      sii.rate, sii.amount
               FROM sales_invoices si
               JOIN sales_invoice_items sii ON sii.invoice_id=si.id
               LEFT JOIN products p ON p.id=sii.product_id
               WHERE si.customer_id=? AND LOWER(COALESCE(si.status,''))='draft'
               ORDER BY si.invoice_date, si.document_no, sii.id""",
            (METRO_ID,),
        ).fetchall()
        total_kg = 0.0
        total_qty = 0.0
        for r in rows:
            r = dict(r)
            total_kg += float(r["net_weight"] or 0)
            total_qty += float(r["quantity"] or 0)
            print(
                f"{r['document_no']} | {r['invoice_date']} | {r['product_code']} | "
                f"qty={float(r['quantity'] or 0):,.3f} | net_kg={float(r['net_weight'] or 0):,.3f} | "
                f"gross={float(r['gross_weight'] or 0):,.3f} tare={float(r['tare_weight'] or 0):,.3f}"
            )
        print(f"TOTAL draft qty={total_qty:,.3f} net_kg={total_kg:,.3f}")

        # Weight slips for metro
        ws_cols = [r[1] for r in c.execute("PRAGMA table_info(weight_slips)").fetchall()]
        print("\nweight_slips cols", ws_cols)
        if ws_cols:
            # find customer link
            q = None
            if "customer_id" in ws_cols:
                q = """SELECT document_no, slip_date, status, net_weight, gross_weight, tare_weight,
                              invoice_id, vehicle_no
                       FROM weight_slips WHERE customer_id=? ORDER BY slip_date DESC"""
                params = (METRO_ID,)
            else:
                q = None
            if q:
                # adapt column names if needed
                try:
                    slips = [dict(r) for r in c.execute(q, params).fetchall()]
                except Exception as e:
                    print("WS query err", e)
                    # try softer
                    slips = [
                        dict(r)
                        for r in c.execute(
                            "SELECT * FROM weight_slips WHERE customer_id=? ORDER BY id DESC LIMIT 50",
                            (METRO_ID,),
                        ).fetchall()
                    ]
                print(f"\n=== WEIGHT SLIPS for Metro ({len(slips)}) ===")
                ws_kg = 0.0
                for s in slips[:40]:
                    nw = float(s.get("net_weight") or s.get("net_wt") or 0)
                    ws_kg += nw
                    print(
                        f"{s.get('document_no') or s.get('id')} | {s.get('slip_date') or s.get('entry_date')} | "
                        f"status={s.get('status')} | net={nw:,.3f} | inv={s.get('invoice_id')} | veh={s.get('vehicle_no')}"
                    )
                print(f"WEIGHT SLIPS net_kg sum (shown)={ws_kg:,.3f}")

        # Link: invoices with weight_slip_id
        si_cols = [r[1] for r in c.execute("PRAGMA table_info(sales_invoices)").fetchall()]
        print("\nsales_invoices has weight_slip_id?", "weight_slip_id" in si_cols)
        if "weight_slip_id" in si_cols:
            for r in c.execute(
                """SELECT document_no, invoice_date, status, weight_slip_id, total
                   FROM sales_invoices WHERE customer_id=? AND status='draft'""",
                (METRO_ID,),
            ).fetchall():
                print(dict(r))

        # Approved/historical metro deliveries for context
        print("\n=== APPROVED / NON-DRAFT METRO INVOICES ===")
        for r in c.execute(
            """SELECT si.document_no, si.invoice_date, si.status,
                      COALESCE(SUM(sii.net_weight),0) AS net_kg,
                      COALESCE(SUM(sii.quantity),0) AS qty
               FROM sales_invoices si
               LEFT JOIN sales_invoice_items sii ON sii.invoice_id=si.id
               WHERE si.customer_id=? AND LOWER(COALESCE(si.status,'')) NOT IN ('draft','cancelled','rejected','void')
               GROUP BY si.id
               ORDER BY si.invoice_date DESC""",
            (METRO_ID,),
        ).fetchall():
            print(dict(r))

        # Gate passes
        gp_cols = []
        try:
            gp_cols = [r[1] for r in c.execute("PRAGMA table_info(gate_passes)").fetchall()]
        except Exception:
            pass
        print("\ngate_passes cols", gp_cols[:30])
        if "party_id" in gp_cols or "customer_id" in gp_cols:
            col = "customer_id" if "customer_id" in gp_cols else "party_id"
            try:
                gps = c.execute(
                    f"""SELECT document_no, pass_date, status, pass_type, net_weight, vehicle_no
                        FROM gate_passes WHERE {col}=? ORDER BY id DESC LIMIT 30""",
                    (METRO_ID,),
                ).fetchall()
                print("gate passes", len(gps))
                for g in gps:
                    print(dict(g))
            except Exception as e:
                print("gp err", e)
                for g in c.execute(
                    f"SELECT * FROM gate_passes WHERE {col}=? ORDER BY id DESC LIMIT 10",
                    (METRO_ID,),
                ).fetchall():
                    print(dict(g))


if __name__ == "__main__":
    main()
