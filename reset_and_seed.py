"""Delete all ERP data and load interconnected demo data for module testing.

Usage:
    python reset_and_seed.py

Login after reset: run reset_admin_password.bat and read ADMIN_BOOTSTRAP.txt
"""

from __future__ import annotations

import shutil
import traceback
from datetime import date
from pathlib import Path

import database as db

TODAY = str(date.today())
BACKUP_SUFFIX = ".before_reset.bak"


def reset_database(backup: bool = True) -> Path | None:
    """Remove live database and re-initialize empty schema + system defaults."""
    db_path = Path(db.DB_PATH)
    backup_path = None
    if db_path.exists():
        if backup:
            backup_path = db_path.with_suffix(db_path.suffix + BACKUP_SUFFIX)
            if backup_path.exists():
                backup_path.unlink()
            shutil.copy2(db_path, backup_path)
        db_path.unlink()
        print(f"Removed: {db_path}")
    db.init_db()
    print("Database re-initialized (schema + defaults).")
    return backup_path


def _complete_slip(uid, *, party_type, party_id, vehicle, gross, tare, product_id=None):
    slip_id = db.save_weight_slip_first({
        "document_no": db.next_weight_slip_no(),
        "slip_date": TODAY,
        "customer_id": party_id if party_type == "customer" else None,
        "supplier_id": party_id if party_type == "supplier" else None,
        "party_type": party_type,
        "product_id": product_id,
        "vehicle_no": vehicle,
        "first_weight": gross,
        "first_weight_time": "08:00:00",
    }, uid)
    db.complete_weight_slip(slip_id, tare, "09:00:00", uid)
    return slip_id


def seed_demo_data(uid: int) -> dict:
    """Create sample masters and transactions linked across all modules."""
    wh = db.get_warehouses()[0]["id"]
    u_kg = next(u["id"] for u in db.get_units_of_measure() if u["symbol"] == "KG")
    u_ctn = next(u["id"] for u in db.get_units_of_measure() if u["symbol"] == "CTN")
    cat_raw = next(c["id"] for c in db.get_product_categories() if "Raw" in c["name"])
    cat_fg = next(c["id"] for c in db.get_product_categories() if "Finished" in c["name"])
    cat_det = next(c["id"] for c in db.get_product_categories() if "Detergent" in c["name"])
    tax_std = next(t["id"] for t in db.get_tax_rates() if t["code"] == "STD18")
    tax_red = next(t["id"] for t in db.get_tax_rates() if t["code"] == "REDUCED")
    bank_acct = next(a["id"] for a in db.get_accounts() if a["code"] == "1100")

    ctx: dict = {"wh": wh, "tax_std": tax_std, "tax_red": tax_red}

    # --- Masters ---
    ctx["sup_id"] = db.add_supplier({
        "code": "SUP-001", "name": "National Chemicals Ltd", "phone": "042-1110001",
        "address": "Industrial Area, Lahore", "opening_balance": 0,
    }, uid)
    ctx["sup2_id"] = db.add_supplier({
        "code": "SUP-002", "name": "Packaging House", "phone": "042-2220002", "opening_balance": 0,
    }, uid)
    ctx["cust_id"] = db.add_customer({
        "code": "CUS-001", "name": "Metro Traders", "phone": "0300-1111111",
        "address": "Hall Road, Lahore", "opening_balance": 0,
    }, uid)
    ctx["cust2_id"] = db.add_customer({
        "code": "CUS-002", "name": "Cash Walk-in Customer", "phone": "0300-2222222", "opening_balance": 0,
    }, uid)

    ctx["raw_id"] = db.add_item({
        "code": "RAW-SODA", "name": "Soda Ash Raw Material", "category_id": cat_raw, "unit_id": u_kg,
        "item_type": "raw", "weight_unit": "kg", "standard_weight": 1.0, "packing_size": "Bulk",
        "purchase_price": 100, "sale_price": 0, "tax_rate_id": tax_std,
        "reorder_level": 200, "min_stock": 100, "stock_qty": 0,
    }, uid)
    ctx["fg_id"] = db.add_item({
        "code": "FG-DET", "name": "Detergent Powder FG", "category_id": cat_fg, "unit_id": u_kg,
        "item_type": "finished", "weight_unit": "kg", "standard_weight": 1.0, "packing_size": "25 kg bag",
        "purchase_price": 0, "sale_price": 250, "tax_rate_id": tax_std,
        "reorder_level": 50, "min_stock": 20, "stock_qty": 0,
    }, uid)
    ctx["ctn_id"] = db.add_item({
        "code": "ITM002", "name": "Train Dishwash 120/36", "category_id": cat_det, "unit_id": u_ctn,
        "item_type": "finished", "weight_unit": "kg", "standard_weight": 4.32, "packing_size": "36 pcs/carton",
        "purchase_price": 490, "sale_price": 500, "tax_rate_id": tax_red,
        "reorder_level": 10, "min_stock": 5, "stock_qty": 50,
    }, uid)

    # --- Finance opening balances ---
    db.add_cash_entry(TODAY, "Opening cash balance", "OB-CASH", "credit", 500_000, None, uid)
    db.add_bank_entry(TODAY, "Opening bank balance", "OB-BANK", "credit", 1_000_000, bank_acct, uid)

    # --- Purchase: GRN → weighbridge → invoice → approve ---
    grn_lines = [{
        "product_id": ctx["raw_id"], "quantity": 500, "unit_id": u_kg,
        "rate": 100, "amount": 50_000, "net_weight": 500,
    }]
    ctx["grn_id"] = db.save_grn({
        "grn_date": TODAY, "supplier_id": ctx["sup_id"], "warehouse_id": wh, "notes": "Demo raw material GRN",
    }, grn_lines, None, uid)
    db.post_grn(ctx["grn_id"], uid)

    ctx["pi_slip"] = _complete_slip(
        uid, party_type="supplier", party_id=ctx["sup_id"],
        vehicle="LHR-4521", gross=1500, tare=1000, product_id=ctx["raw_id"],
    )
    pi_lines = [{
        "item_id": ctx["raw_id"], "quantity": 500, "rate": 100, "amount": 50_000,
        "net_weight": 500, "tax_rate_id": tax_std,
    }]
    ctx["pi_id"] = db.save_purchase({
        "invoice_no": db.next_invoice("PI", "purchase_invoices"),
        "supplier_id": ctx["sup_id"], "purchase_date": TODAY,
        "discount_pct": 0, "tax_rate_id": tax_std, "paid_amount": 20_000,
        "payment_mode": "cash", "notes": "Demo purchase invoice", "grn_id": ctx["grn_id"],
        "weight_slip_id": ctx["pi_slip"],
    }, pi_lines, None, uid)
    db.submit_purchase_invoice(ctx["pi_id"], uid)
    db.approve_purchase_invoice(ctx["pi_id"], uid)

    # --- Production: BOM → order → issue → complete ---
    ctx["bom_id"] = db.save_bom({
        "finished_product_id": ctx["fg_id"], "version_no": "1.0", "standard_output_qty": 100,
    }, [{
        "raw_product_id": ctx["raw_id"], "quantity": 80, "standard_cost": 100,
        "line_cost": 8000, "wastage_pct": 2,
    }], None, uid)
    db.approve_bom(ctx["bom_id"], uid)

    ctx["po_id"] = db.save_production_order({
        "order_date": TODAY, "bom_id": ctx["bom_id"], "finished_product_id": ctx["fg_id"],
        "warehouse_id": wh, "planned_qty": 100,
        "labour_cost": 500, "utility_cost": 300, "packing_cost": 200, "overhead_cost": 100,
    }, uid)
    db.issue_production_materials(ctx["po_id"], uid)
    db.complete_production(ctx["po_id"], 98, 2, "Passed", uid)

    # --- Sales 1: bulk FG (weight slip matches invoice) ---
    ctx["si1_slip"] = _complete_slip(
        uid, party_type="customer", party_id=ctx["cust_id"],
        vehicle="KHI-8899", gross=100, tare=50, product_id=ctx["fg_id"],
    )
    si1_lines = [{
        "item_id": ctx["fg_id"], "quantity": 50, "rate": 250, "amount": 12_500,
        "net_weight": 50, "tax_rate_id": tax_std,
    }]
    ctx["si1_id"] = db.save_sale({
        "invoice_no": db.next_invoice("SI", "sales_invoices"),
        "customer_id": ctx["cust_id"], "sale_date": TODAY,
        "discount_pct": 0, "tax_rate_id": tax_std, "paid_amount": 10_000,
        "payment_mode": "cash", "weight_slip_id": ctx["si1_slip"],
    }, si1_lines, None, uid)
    db.submit_sale_invoice(ctx["si1_id"], uid)
    db.approve_sale_invoice(ctx["si1_id"], uid)

    # --- Sales 2: carton product (auto weight = qty × 4.32 kg) ---
    ctn_qty, ctn_net = 10, 43.2
    ctx["si2_slip"] = _complete_slip(
        uid, party_type="customer", party_id=ctx["cust2_id"],
        vehicle="ISB-3344", gross=500, tare=456.8, product_id=ctx["ctn_id"],
    )
    si2_lines = [{
        "item_id": ctx["ctn_id"], "quantity": ctn_qty, "rate": 500, "amount": ctn_qty * 500,
        "net_weight": ctn_net, "tax_rate_id": tax_red,
    }]
    ctx["si2_id"] = db.save_sale({
        "invoice_no": db.next_invoice("SI", "sales_invoices"),
        "customer_id": ctx["cust2_id"], "sale_date": TODAY,
        "discount_pct": 0, "tax_rate_id": tax_red, "paid_amount": 0,
        "payment_mode": "credit", "weight_slip_id": ctx["si2_slip"],
    }, si2_lines, None, uid)
    db.submit_sale_invoice(ctx["si2_id"], uid)
    db.approve_sale_invoice(ctx["si2_id"], uid)

    # --- Finance: customer receipt + supplier payment ---
    cust, _ = db.get_customer_ledger(ctx["cust_id"])
    if float(cust["balance"]) > 0:
        db.record_customer_receipt(
            ctx["cust_id"], TODAY, float(cust["balance"]), "RCP-DEMO-001",
            "Demo customer payment", uid,
        )
    db.record_supplier_payment(
        ctx["sup_id"], TODAY, 20_000, "PAY-DEMO-001", "Demo supplier payment", uid,
    )
    db.add_cash_entry(TODAY, "Petty office expense", "EXP-001", "debit", 2_500, None, uid)

    # --- HR: employee + attendance ---
    dept = db.get_departments()[0]["id"] if db.get_departments() else None
    ctx["emp_id"] = db.add_employee_hr({
        "code": "EMP-002", "full_name": "Ahmed Production", "mobile": "0321-5555555",
        "department_id": dept, "department_name": "Production",
        "designation_name": "Supervisor", "joining_date": TODAY, "basic_salary": 45_000,
    }, uid)
    db.save_attendance({
        "employee_id": ctx["emp_id"], "att_date": TODAY,
        "status": "present", "check_in": "08:30", "check_out": "17:30",
    }, uid)

    return ctx


def verify_seed(ctx: dict) -> list[str]:
    """Quick checks that modules are linked."""
    issues = []
    si1 = db.get_sale(ctx["si1_id"])
    if not si1.get("gate_pass_id") and not db.get_gate_passes(sales_invoice_id=ctx["si1_id"]):
        issues.append("Sales invoice 1 missing gate pass")
    raw = next(i for i in db.get_items() if i["id"] == ctx["raw_id"])
    fg = next(i for i in db.get_items() if i["id"] == ctx["fg_id"])
    ctn = next(i for i in db.get_items() if i["id"] == ctx["ctn_id"])
    if raw["stock_qty"] <= 0:
        issues.append("Raw stock should be positive after GRN/production")
    if fg["stock_qty"] <= 0:
        issues.append("FG stock should remain after production minus sale")
    if ctn["stock_qty"] != 40:
        issues.append(f"Carton stock expected 40 after sale (50 - 10), got {ctn['stock_qty']}")
    tb = db.get_trial_balance(f"{date.today().year}-01-01", f"{date.today().year}-12-31")
    dr = sum(r["period_debit"] for r in tb)
    cr = sum(r["period_credit"] for r in tb)
    if abs(dr - cr) > 0.02:
        issues.append(f"Trial balance not balanced: DR {dr} CR {cr}")
    if not db.get_cash_book(TODAY, TODAY):
        issues.append("Cash book has no entries for today")
    if not db.get_bank_book(TODAY, TODAY):
        issues.append("Bank book has no entries for today")
    return issues


def print_summary(ctx: dict):
    print("\n" + "=" * 60)
    print("DEMO DATA LOADED — test these linked flows:")
    print("=" * 60)
    print("  Masters     : 2 customers, 2 suppliers, 3 products (raw / FG / carton)")
    print("  Purchase    : GRN -> weight slip -> purchase invoice (approved)")
    print("  Production  : BOM -> production order -> material issue -> FG receipt")
    print("  Sales       : 2 sales with weight slips, gate passes, approval")
    print("  Finance     : opening cash/bank, customer receipt, supplier payment")
    print("  HR          : employee + today's attendance")
    print("-" * 60)
    for label, key in [
        ("Purchase invoice", "pi_id"), ("Production order", "po_id"),
        ("Sale (bulk FG)", "si1_id"), ("Sale (cartons)", "si2_id"),
    ]:
        print(f"  {label}: ID {ctx.get(key)}")
    print("-" * 60)
    print("  Login: run reset_admin_password.bat — see ADMIN_BOOTSTRAP.txt")
    print("  Stock snapshot:")
    for i in db.get_items():
        print(f"    {i['code']}: {i['stock_qty']} {i['unit']}")


def main():
    print("IFS Chemicals ERP — Reset & Seed Demo Data")
    print("=" * 60)
    try:
        backup = reset_database(backup=True)
        if backup:
            print(f"Backup saved: {backup}")
        from tools.reset_admin_password import reset_admin_password
        pw = reset_admin_password()
        user = db.authenticate("admin", pw)
        if not user:
            raise RuntimeError("Admin user missing after init_db()")
        uid = user["id"]
        ctx = seed_demo_data(uid)
        issues = verify_seed(ctx)
        if issues:
            print("\nWARNINGS:")
            for msg in issues:
                print(f"  - {msg}")
        else:
            print("\nAll linkage checks passed.")
        print_summary(ctx)
        return 0
    except Exception as e:
        print(f"\nFAILED: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
