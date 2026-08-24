"""V13.14 — unified line entry engine (wraps smart_line_item_editor)."""

from __future__ import annotations

import streamlit as st

from erp_ui import helpers as hlp


def line_entry_engine(
    items_dict,
    key_prefix: str,
    *,
    show_weight: bool = False,
    party_id=None,
    require_rate: bool = True,
    validate_stock: bool = False,
    warehouse_id=None,
):
    """
    Reusable grid: insert, delete, edit, copy, paste, move, duplicate row.
    Returns (valid_lines, total_amount).
    """
    sk = f"{key_prefix}_lines"
    clip_key = f"{key_prefix}_line_clip"
    hlp._init_line_items_session(sk)

    tb1, tb2, tb3, tb4, tb5 = st.columns(5)
    if tb1.button("+ Insert row", key=f"{key_prefix}_ins", use_container_width=True):
        st.session_state[sk].append(hlp._blank_line_item())
        st.rerun()
    if tb2.button("Copy row", key=f"{key_prefix}_cpy", use_container_width=True):
        sel = st.session_state.get(f"{key_prefix}_edit_pick", "—")
        lines = [l for l in st.session_state[sk] if l.get("item_id") or l.get("product_id")]
        if sel != "—" and lines:
            idx = int(sel.split()[1]) - 1 if "Line" in sel else 0
            if 0 <= idx < len(lines):
                st.session_state[clip_key] = dict(lines[idx])
                st.toast("Line copied.")
    if tb3.button("Paste row", key=f"{key_prefix}_pst", use_container_width=True):
        clip = st.session_state.get(clip_key)
        if clip:
            st.session_state[sk].append(dict(clip))
            st.rerun()
    if tb4.button("↑ Move up", key=f"{key_prefix}_mvu", use_container_width=True):
        _move_line(sk, -1, key_prefix)
    if tb5.button("↓ Move down", key=f"{key_prefix}_mvd", use_container_width=True):
        _move_line(sk, 1, key_prefix)

    if st.button("Ctrl+D duplicate last valid row", key=f"{key_prefix}_dup", use_container_width=False):
        valid = [l for l in st.session_state[sk] if l.get("item_id") or l.get("product_id")]
        if valid:
            st.session_state[sk].append(dict(valid[-1]))
            st.rerun()

    valid, total = hlp.smart_line_item_editor(
        items_dict, key_prefix, show_weight=show_weight, party_id=party_id,
    )

    if validate_stock and warehouse_id and valid:
        from application import data_gateway as db
        from erp_core.inventory_service import stock_position

        for i, ln in enumerate(valid, 1):
            pid = ln.get("item_id") or ln.get("product_id")
            qty = float(ln.get("quantity") or 0)
            pos = stock_position(pid, warehouse_id)
            if qty > pos["available"] and db.get_setting("allow_negative_stock", "0") != "1":
                st.warning(f"Line {i}: qty {qty:,.2f} exceeds available stock {pos['available']:,.2f}")

    st.caption(
        f"**{len(valid)}** line(s) · **Total {total:,.2f}** · "
        "Double-click row via Select line to edit · Totals/tax refresh on change"
    )
    return valid, total


def _move_line(sk: str, direction: int, key_prefix: str) -> None:
    lines = st.session_state.get(sk) or []
    sel = st.session_state.get(f"{key_prefix}_edit_pick", "—")
    if sel == "—" or not lines:
        return
    try:
        idx = int(sel.replace("Line ", "").split(":")[0]) - 1
    except Exception:
        return
    j = idx + direction
    if 0 <= idx < len(lines) and 0 <= j < len(lines):
        lines[idx], lines[j] = lines[j], lines[idx]
        st.session_state[sk] = lines
        st.rerun()
