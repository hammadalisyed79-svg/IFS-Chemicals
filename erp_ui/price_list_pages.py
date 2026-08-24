"""V15 — Price list master and distributor assignment."""

from __future__ import annotations

import streamlit as st
from erp_ui import form_flow as ff
import pandas as pd

from application import data_gateway as db
from application.data_gateway import user_can
from erp_ui.helpers import std_page_header, money_input, options_with_blank, require_selected, sticky_page_tabs, render_dataframe_html_table


def page_price_lists():
    user = st.session_state.get("user") or {}
    if not user_can(user, "PriceLists", "view") and user.get("role") != "admin":
        st.error("Access denied.")
        return

    std_page_header("Price Lists", status="register", status_kind="shell")
    tab = sticky_page_tabs(["Price Lists", "Line Rates", "Distributor Assignment"], "price_list_tab")

    if tab == "Price Lists":
        _tab_lists(user)
    elif tab == "Line Rates":
        _tab_items(user)
    elif tab == "Distributor Assignment":
        _tab_assign(user)


def _tab_lists(user):
    with db.get_connection() as conn:
        rows = conn.execute("SELECT * FROM price_lists ORDER BY code").fetchall()
    if rows:
        render_dataframe_html_table(pd.DataFrame([dict(r) for r in rows]))
    with st.form("new_pl"):
        code = st.text_input("Code")
        name = st.text_input("Name")
        lt = st.selectbox("Type", ["retail", "wholesale", "distributor", "special", "region", "product"])
        if st.form_submit_button("Create price list", type="primary"):
            with db.get_connection() as conn:
                conn.execute(
                    "INSERT INTO price_lists(code,name,list_type,is_active,created_by) VALUES(?,?,?,1,?)",
                    (code.upper(), name, lt, user.get("id")),
                )
            ff.action_done("Created")


def _tab_items(user):
    with db.get_connection() as conn:
        pls = [dict(r) for r in conn.execute("SELECT id, code, name FROM price_lists WHERE is_active=1").fetchall()]
    if not pls:
        st.info("Create a price list first.")
        return
    pl_map = {f"{p['code']} — {p['name']}": p["id"] for p in pls}
    pl_id = pl_map[st.selectbox("Price list", list(pl_map.keys()))]
    with db.get_connection() as conn:
        items = [dict(r) for r in conn.execute(
            """SELECT pli.*, p.code, p.name FROM price_list_items pli
               JOIN products p ON p.id=pli.product_id WHERE pli.price_list_id=?""",
            (pl_id,),
        ).fetchall()]
    if items:
        render_dataframe_html_table(pd.DataFrame(items))

    products = db.get_items(active_only=True)
    p_opts = {f"{p['code']} — {p['name']}": p["id"] for p in products}
    with st.form("add_pli"):
        prod = st.selectbox("Product", list(p_opts.keys()))
        rate = money_input("Rate", value=0.0, min_value=0.0, key="pli_rate")
        disc = st.number_input("Discount %", min_value=0.0, max_value=100.0, step=0.5)
        minq = st.number_input("Min order qty", min_value=0.0, step=1.0, value=1.0)
        if st.form_submit_button("Add / update rate", type="primary"):
            pid = p_opts[prod]
            with db.get_connection() as conn:
                conn.execute(
                    """INSERT INTO price_list_items(price_list_id,product_id,rate,discount_pct,min_qty,is_active)
                       VALUES(?,?,?,?,?,1)
                       ON CONFLICT(price_list_id,product_id) DO UPDATE SET
                       rate=excluded.rate, discount_pct=excluded.discount_pct, min_qty=excluded.min_qty""",
                    (pl_id, pid, rate, disc, minq),
                )
            ff.action_done("Saved")


def _tab_assign(user):
    customers = [c for c in db.get_customers(active_only=True) if c.get("is_distributor") or c.get("portal_enabled")]
    if not customers:
        st.info("Mark customers as distributors (Customers master) to assign price lists.")
        return
    cmap = {f"{c['code']} — {c['name']}": c for c in customers}
    cust_labels, blank = options_with_blank(cmap.keys())
    cust_lbl = st.selectbox("Distributor customer", cust_labels)
    if not require_selected("distributor customer", cust_lbl, blank, soft=True):
        return
    cust = cmap[cust_lbl]
    with db.get_connection() as conn:
        pls = [dict(r) for r in conn.execute("SELECT id, code, name FROM price_lists WHERE is_active=1").fetchall()]
    pl_map = {f"{p['code']} — {p['name']}": p["id"] for p in pls}
    cur_pl = cust.get("assigned_price_list_id")
    default = next((k for k, v in pl_map.items() if v == cur_pl), list(pl_map.keys())[0] if pl_map else None)
    pl_sel = st.selectbox("Assigned price list", list(pl_map.keys()), index=list(pl_map.keys()).index(default) if default in pl_map else 0)
    credit = st.number_input("Credit limit", value=float(cust.get("credit_limit") or 0))
    show_stock = st.checkbox("Show stock in portal", value=bool(cust.get("show_stock")))
    if st.button("Save assignment", type="primary"):
        pl_id = pl_map[pl_sel]
        with db.get_connection() as conn:
            conn.execute(
                "UPDATE customers SET is_distributor=1, portal_enabled=1, assigned_price_list_id=?, credit_limit=? WHERE id=?",
                (pl_id, credit, cust["id"]),
            )
            conn.execute(
                """INSERT INTO distributor_profiles(customer_id,assigned_price_list_id,credit_limit,show_stock,portal_enabled)
                   VALUES(?,?,?,?,1)
                   ON CONFLICT(customer_id) DO UPDATE SET
                   assigned_price_list_id=excluded.assigned_price_list_id,
                   credit_limit=excluded.credit_limit, show_stock=excluded.show_stock""",
                (cust["id"], pl_id, credit, int(show_stock)),
            )
            conn.execute(
                """INSERT INTO distributor_price_lists(customer_id,price_list_id,priority,is_active,created_by)
                   VALUES(?,?,1,1,?)
                   ON CONFLICT DO NOTHING""",
                (cust["id"], pl_id, user.get("id")),
            )
        st.success("Distributor pricing updated.")
