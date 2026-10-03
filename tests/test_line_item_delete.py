"""Purchase/sale line ✕ must remove only the clicked row."""

from erp_ui.line_row_state import blank_line_item, drop_lines_by_uid, pad_line_rows


def _old_buggy_delete(rows, delete_index):
    """Reproduce the previous editor: skip deleted row, then filter by original index."""
    updated, to_remove = [], []
    for i, line in enumerate(rows):
        if i == delete_index:
            to_remove.append(i)
        else:
            updated.append(line)
    return [l for j, l in enumerate(updated) if j not in to_remove]


def test_old_index_delete_also_drops_the_next_row():
    rows = [
        {"_row_uid": "a", "item": "RM319"},
        {"_row_uid": "b", "item": "RM251"},
        {"_row_uid": "c", "item": "RM253"},  # Rexona
        {"_row_uid": "d", "item": "RM321"},
        {"_row_uid": "e", "item": "RM0080"},
    ]
    leftover = _old_buggy_delete(rows, 2)
    codes = [r["item"] for r in leftover]
    assert "RM253" not in codes
    assert "RM321" not in codes  # neighbor wrongly removed


def test_uid_delete_drops_only_clicked_row():
    rows = [
        {"_row_uid": "a", "item": "RM319"},
        {"_row_uid": "b", "item": "RM251"},
        {"_row_uid": "c", "item": "RM253"},
        {"_row_uid": "d", "item": "RM321"},
        {"_row_uid": "e", "item": "RM0080"},
    ]
    leftover = drop_lines_by_uid(rows, ["c"])
    assert [r["item"] for r in leftover] == ["RM319", "RM251", "RM321", "RM0080"]


def test_remove_line_does_not_delete_duplicate_product_ids():
    rows = [
        {"_row_uid": "a", "item_id": 192},
        {"_row_uid": "b", "item_id": 192},
        {"_row_uid": "c", "item_id": 276},
    ]
    leftover = drop_lines_by_uid(rows, ["a"])
    assert [r["_row_uid"] for r in leftover] == ["b", "c"]


def test_pad_assigns_unique_row_uids():
    rows = pad_line_rows([{"item_id": 1}, {"item_id": 2}], min_rows=5)
    uids = [r["_row_uid"] for r in rows]
    assert len(uids) == 5
    assert len(set(uids)) == 5
    assert blank_line_item()["_row_uid"] != blank_line_item()["_row_uid"]
