"""Smoke tests: account/item groups, weighbridge ↔ invoice linking."""

import os
import sys
import tempfile
from datetime import date

from pathlib import Path

_test_db = Path(tempfile.gettempdir()) / "erp_flow_test.db"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import database as db  # noqa: E402

db.DB_PATH = _test_db
from db_groups import (  # noqa: E402
    assign_entities_to_group,
    get_group_members,
    add_master_group,
    resolve_entity_ids_by_codes,
    remove_entities_from_group,
)
from db_commercial import (  # noqa: E402
    get_unlinked_slips_for_party,
    get_referenceable_slips,
    list_weight_slip_invoice_attachments,
    link_weight_slip_to_invoice,
    weight_slip_is_linked,
    save_weight_slip_pro,
)
from db_invoice_workflow import (  # noqa: E402
    complete_weight_slip,
    save_weight_slip_first,
    refresh_invoice_weight_match,
)


def setup():
    if _test_db.exists():
        _test_db.unlink()
    db.reset_runtime_state()
    db.init_db(force=True)
    uid = 1
    db.add_customer({"code": "T001", "name": "Test Customer A"}, uid)
    db.add_customer({"code": "T002", "name": "Test Customer B"}, uid)
    u = db.get_units_of_measure()
    unit_id = u[0]["id"] if u else None
    db.add_item(
        {
            "code": "T-PROD",
            "name": "Test Product",
            "unit_id": unit_id,
            "sale_price": 100.0,
            "purchase_price": 80.0,
            "item_type": "finished",
        },
        uid,
    )


def test_groups_bulk_add():
    setup()
    gid = add_master_group(
        {"entity_type": "customer", "code": "TGRP", "name": "Test Group", "sort_order": 0},
        user_id=1,
    )
    customers = db.get_customers(active_only=True)
    assert len(customers) >= 2, "need sample customers"
    ids = [customers[0]["id"], customers[1]["id"]]
    n = assign_entities_to_group("customer", ids, gid, user_id=1)
    assert n == 2
    members = get_group_members(gid)
    assert len(members) == 2
    codes = [customers[0]["code"], customers[1]["code"]]
    found, missing = resolve_entity_ids_by_codes("customer", codes)
    assert len(found) == 2
    assert not missing
    remove_entities_from_group("customer", ids, user_id=1)
    assert len(get_group_members(gid)) == 0
    print("OK test_groups_bulk_add")


def test_weigh_then_sale_link():
    setup()
    customers = db.get_customers(active_only=True)
    products = db.get_items(active_only=True)
    assert customers and products
    cid, pid = customers[0]["id"], products[0]["id"]
    slip_id = db.save_weight_slip_first(
        {
            "document_no": "WS-TEST-1",
            "slip_date": str(date.today()),
            "customer_id": cid,
            "party_type": "customer",
            "product_id": pid,
            "vehicle_no": "TEST-123",
            "first_weight": 5000.0,
            "second_weight": 0,
            "gross_weight": 5000.0,
            "tare_weight": 0,
            "net_weight": 0,
            "first_weight_time": "2026-06-03 10:00:00",
        },
        user_id=1,
    )
    complete_weight_slip(slip_id, 3000.0, "2026-06-03 11:00:00", user_id=1)
    slips = get_unlinked_slips_for_party("customer", cid)
    assert any(s["id"] == slip_id for s in slips)
    header = {
        "invoice_no": "SI-TEST-1",
        "customer_id": cid,
        "sale_date": str(date.today()),
        "payment_mode": "credit",
        "paid_amount": 0,
        "notes": "test",
        "tax_rate_id": db.get_tax_rates()[0]["id"] if db.get_tax_rates() else None,
        "discount_pct": 0,
        "weighbridge_required": 1,
        "weight_slip_id": slip_id,
    }
    lines = [{"item_id": pid, "quantity": 1.0, "rate": 100.0, "amount": 100.0, "net_weight": 2000.0}]
    sale_id = db.save_sale(header, lines, user_id=1)
    sale = db.get_sale(sale_id)
    assert sale["weight_slip_id"] == slip_id
    slip = db.get_weight_slip_pro(slip_id)
    assert weight_slip_is_linked(slip)
    # save without slip should fail
    header2 = dict(header)
    header2.pop("weight_slip_id")
    header2["invoice_no"] = "SI-TEST-2"
    try:
        db.save_sale(header2, lines, user_id=1)
        raise AssertionError("expected ValueError without weight slip")
    except ValueError as e:
        assert "Weight slip required" in str(e)
    print("OK test_weigh_then_sale_link")


def test_update_sale_with_weight_slip():
    """Regression: sales_invoices has no supplier_id — update must not query it."""
    setup()
    customers = db.get_customers(active_only=True)
    products = db.get_items(active_only=True)
    cid, pid = customers[0]["id"], products[0]["id"]
    slip_id = save_weight_slip_first(
        {"vehicle_no": "UPD-TEST", "customer_id": cid, "party_type": "customer", "first_weight": 5000},
        user_id=1,
    )
    complete_weight_slip(slip_id, 3000.0, "2026-06-03 11:00:00", user_id=1)
    header = {
        "invoice_no": "SI-UPD-1",
        "customer_id": cid,
        "sale_date": str(date.today()),
        "payment_mode": "credit",
        "paid_amount": 0,
        "weighbridge_required": 1,
        "weight_slip_id": slip_id,
        "discount_pct": 0,
    }
    lines = [{"item_id": pid, "quantity": 2.0, "rate": 100.0, "amount": 200.0, "net_weight": 2000.0}]
    sale_id = db.save_sale(header, lines, user_id=1)
    header["notes"] = "updated"
    db.save_sale(header, lines, sale_id=sale_id, user_id=1)
    sale = db.get_sale(sale_id)
    assert sale["notes"] == "updated"
    print("OK test_update_sale_with_weight_slip")


def test_save_sale_without_slip_rejected():
    setup()
    customers = db.get_customers(active_only=True)
    products = db.get_items(active_only=True)
    header = {
        "invoice_no": "SI-NOSLIP",
        "customer_id": customers[0]["id"],
        "sale_date": str(date.today()),
        "payment_mode": "credit",
        "paid_amount": 0,
        "weighbridge_required": 1,
        "discount_pct": 0,
    }
    lines = [{"item_id": products[0]["id"], "quantity": 1.0, "rate": 1.0, "amount": 1.0, "net_weight": 1.0}]
    try:
        db.save_sale(header, lines, user_id=1)
        raise AssertionError("expected reject")
    except ValueError:
        pass
    print("OK test_save_sale_without_slip_rejected")


def test_weight_slip_reference_only_second_invoice():
    """Primary keeps full slip weight/variance; second invoice is reference-only."""
    setup()
    customers = db.get_customers(active_only=True)
    products = db.get_items(active_only=True)
    assert len(customers) >= 2
    c1, c2 = customers[0]["id"], customers[1]["id"]
    pid = products[0]["id"]
    slip_id = save_weight_slip_first(
        {
            "vehicle_no": "REF-TEST",
            "customer_id": c1,
            "party_type": "customer",
            "product_id": pid,
            "first_weight": 5000,
        },
        user_id=1,
    )
    complete_weight_slip(slip_id, 3000.0, "2026-06-03 11:00:00", user_id=1)
    tax_id = db.get_tax_rates()[0]["id"] if db.get_tax_rates() else None
    lines_pri = [{"item_id": pid, "quantity": 1.0, "rate": 100.0, "amount": 100.0, "net_weight": 2000.0}]
    primary_id = db.save_sale(
        {
            "invoice_no": "SI-PRI-1",
            "customer_id": c1,
            "sale_date": str(date.today()),
            "payment_mode": "credit",
            "paid_amount": 0,
            "weighbridge_required": 1,
            "weight_slip_id": slip_id,
            "weight_slip_as_primary": True,
            "tax_rate_id": tax_id,
            "discount_pct": 0,
        },
        lines_pri,
        user_id=1,
    )
    lines_ref = [{"item_id": pid, "quantity": 1.0, "rate": 50.0, "amount": 50.0, "net_weight": 500.0}]
    ref_id = db.save_sale(
        {
            "invoice_no": "SI-REF-1",
            "customer_id": c2,
            "sale_date": str(date.today()),
            "payment_mode": "credit",
            "paid_amount": 0,
            "weighbridge_required": 1,
            "weight_slip_id": slip_id,
            "weight_slip_as_primary": False,
            "tax_rate_id": tax_id,
            "discount_pct": 0,
        },
        lines_ref,
        user_id=1,
    )
    atts = list_weight_slip_invoice_attachments(slip_id)
    assert len(atts) == 2
    assert atts[0]["link_role"] == "primary" and atts[0]["id"] == primary_id
    assert any(a["id"] == ref_id and a["link_role"] == "reference" for a in atts)

    slip = db.get_weight_slip_pro(slip_id)
    assert slip["reference_type"] == "sales_invoice"
    assert int(slip["reference_id"]) == primary_id

    pri = db.get_sale(primary_id)
    ref = db.get_sale(ref_id)
    assert pri["weight_match_status"] != "reference"
    assert float(pri["physical_weight_kg"] or 0) > 0
    assert ref["weight_match_status"] == "reference"
    assert float(ref["physical_weight_kg"] or 0) == 0
    assert float(ref["weight_variance_kg"] or 0) == 0

    try:
        link_weight_slip_to_invoice(
            slip_id, "sales_invoice", ref_id, user_id=1, as_primary=True,
        )
        raise AssertionError("expected second primary to fail")
    except ValueError as e:
        assert "already has a primary" in str(e)

    assert any(s["id"] == slip_id for s in get_referenceable_slips())
    print("OK test_weight_slip_reference_only_second_invoice")


if __name__ == "__main__":
    test_groups_bulk_add()
    test_save_sale_without_slip_rejected()
    test_weigh_then_sale_link()
    test_update_sale_with_weight_slip()
    test_weight_slip_reference_only_second_invoice()
    print("\nAll flow tests passed.")
