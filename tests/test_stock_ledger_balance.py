from db_reports import apply_stock_ledger_balances


def test_running_balance_in_then_out():
    rows = [
        {"product_id": 1, "movement_type": "in", "quantity": 100},
        {"product_id": 1, "movement_type": "out", "quantity": 30},
        {"product_id": 1, "movement_type": "out", "quantity": 10},
    ]
    out, summary = apply_stock_ledger_balances(rows, {1: 50})
    assert [r["balance"] for r in out] == [150, 120, 110]
    assert summary["opening"] == 50
    assert summary["period_in"] == 100
    assert summary["period_out"] == 40
    assert summary["closing"] == 110


def test_running_balance_resets_per_product():
    rows = [
        {"product_id": 1, "movement_type": "in", "quantity": 5},
        {"product_id": 2, "movement_type": "out", "quantity": 2},
        {"product_id": 1, "movement_type": "out", "quantity": 1},
    ]
    out, summary = apply_stock_ledger_balances(rows, {1: 10, 2: 8})
    assert [r["balance"] for r in out] == [15, 6, 14]
    assert summary["opening"] == 18
    assert summary["closing"] == 20
