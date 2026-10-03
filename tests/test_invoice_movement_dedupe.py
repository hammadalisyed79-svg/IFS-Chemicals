"""Keep oldest invoice movements until line qty is filled."""

from erp_core.inventory_movement_dedupe import plan_movement_keeps


def test_plan_keeps_first_batch_of_duplicate_sale():
    lines = {764: 300.0}
    mvs = [
        {"id": 24992, "product_id": 764, "quantity": 300},
        {"id": 25002, "product_id": 764, "quantity": 300},
    ]
    assert plan_movement_keeps(lines, mvs) == [24992]


def test_plan_keeps_multi_line_same_product():
    lines = {10: 100.0 + 50.0}
    mvs = [
        {"id": 1, "product_id": 10, "quantity": 100},
        {"id": 2, "product_id": 10, "quantity": 50},
        {"id": 3, "product_id": 10, "quantity": 100},
        {"id": 4, "product_id": 10, "quantity": 50},
    ]
    assert plan_movement_keeps(lines, mvs) == [1, 2]


def test_plan_prefers_exact_qty_on_reapprove():
    lines = {1: 38940.0}
    mvs = [
        {"id": 1667, "product_id": 1, "quantity": 38835.0},
        {"id": 17682, "product_id": 1, "quantity": 38940.0},
    ]
    assert plan_movement_keeps(lines, mvs) == [17682]


def test_plan_drops_product_not_on_invoice():
    lines = {1: 10.0}
    mvs = [
        {"id": 1, "product_id": 1, "quantity": 10},
        {"id": 2, "product_id": 2, "quantity": 4145},
    ]
    assert plan_movement_keeps(lines, mvs) == [1]
