"""Job cards — BOM-style: produced item header + raw material consumption lines."""

from datetime import date
import pandas as pd
import streamlit as st
from erp_ui import form_flow as ff
from application import data_gateway as db
from db_job_cards import (
    JOB_TYPES, DOC_TYPE_BY_JOB,
    save_job_card, get_job_card, get_job_cards, post_job_card, delete_job_card,
    job_card_stock_warnings,
    get_raw_material_items, get_finished_product_items, bom_material_lines,
)
from erp_ui.helpers import uid, std_page_header, fmt_money, money_input, sticky_page_tabs
from erp_ui.invoice_status_ui import status_badge_html


def _material_opts():
    """Saved products from Products master (same pool as BOM components)."""
    return {f"{r['code']} — {r['name']}": r for r in get_raw_material_items(active_only=True)}


def _fg_opts():
    return {f"{r['code']} — {r['name']}": r for r in get_finished_product_items(active_only=True)}


def _wh_opts():
    return {f"{w['code']} - {w['name']}": w["id"] for w in db.get_warehouses()}


def _blank_line():
    return {"product_id": None, "quantity": 0.0, "rate": 0.0}


def _lines_from_job_card(jc):
    return [
        {
            "product_id": ln["product_id"],
            "quantity": float(ln.get("quantity") or 0),
            "rate": float(ln.get("rate") or 0),
        }
        for ln in (jc.get("material_lines") or [])
        if ln.get("product_id")
    ]


def _clear_prefix_keys(prefix):
    for k in list(st.session_state.keys()):
        if k == prefix or k.startswith(f"{prefix}_"):
            del st.session_state[k]


def _seed_material_lines(prefix, lines):
    st.session_state[f"{prefix}_mat"] = lines if lines else [_blank_line(), _blank_line()]
    for k in list(st.session_state.keys()):
        if k.startswith(f"{prefix}_m_") or k.startswith(f"{prefix}_q_") or k.startswith(
            f"{prefix}_r_"
        ) or k.startswith(f"{prefix}_x_"):
            del st.session_state[k]


def _clear_job_card_edit():
    eid = st.session_state.pop("jc_edit_id", None)
    if eid:
        _clear_prefix_keys(f"jc_ed_{eid}")


def _material_lines_editor(raw_items, key_prefix):
    """BOM-like consumption grid: product | qty | rate | amount."""
    sk = f"{key_prefix}_mat"
    if sk not in st.session_state or not st.session_state[sk]:
        st.session_state[sk] = [_blank_line(), _blank_line(), _blank_line()]
    lines = st.session_state[sk]
    labels = list(raw_items.keys())
    none_lbl = "— select product —"
    pick = [none_lbl] + labels
    updated, remove = [], []

    st.markdown("**Materials consumed** (saved products — rate from purchase price)")
    hdr = st.columns([3, 1, 1, 1, 0.3])
    hdr[0].caption("**Product**")
    hdr[1].caption("**Qty**")
    hdr[2].caption("**Rate**")
    hdr[3].caption("**Amount**")

    for i, ln in enumerate(lines):
        c = st.columns([3, 1, 1, 1, 0.3])
        pid = ln.get("product_id")
        default = next((k for k, v in raw_items.items() if v["id"] == pid), none_lbl)
        sel = c[0].selectbox(
            "mat", pick, index=pick.index(default) if default in pick else 0,
            key=f"{key_prefix}_m_{i}", label_visibility="collapsed",
        )
        prod = raw_items.get(sel) if sel != none_lbl else None
        qty = c[1].number_input("q", min_value=0.0, value=float(ln.get("quantity") or 0),
                                key=f"{key_prefix}_q_{i}", label_visibility="collapsed")
        saved_rate = float(ln.get("rate") or 0)
        default_rate = saved_rate if saved_rate > 0 else float(prod.get("purchase_price") or 0) if prod else 0.0
        with c[2]:
            rate = money_input(
                "r", value=default_rate, min_value=0.0,
                key=f"{key_prefix}_r_{i}", label_visibility="collapsed",
            )
        c[3].write(f"{qty * rate:,.2f}")
        if c[4].button("✕", key=f"{key_prefix}_x_{i}"):
            remove.append(i)
        elif prod:
            updated.append({"product_id": prod["id"], "quantity": qty, "rate": rate or default_rate})
        else:
            updated.append({"product_id": None, "quantity": qty, "rate": rate})
    if remove:
        st.session_state[sk] = [x for j, x in enumerate(lines) if j not in remove]
        st.rerun()
    st.session_state[sk] = updated if updated else [_blank_line()]
    if st.button("+ Add material line", key=f"{key_prefix}_add"):
        st.session_state[sk].append(_blank_line())
        st.rerun()
    total = sum(l["quantity"] * l["rate"] for l in updated if l.get("product_id"))
    st.caption(f"**{len([l for l in updated if l.get('product_id')])}** line(s) | Material cost **{fmt_money(total)}**")
    return [l for l in updated if l.get("product_id") and l.get("quantity", 0) > 0]


def _job_card_form_body(prefix, raw_items, fg_items, wh_items, jc=None, edit_id=None):
    """Shared header + materials form. jc set when editing an existing draft."""
    wh_keys = list(wh_items.keys()) if wh_items else ["—"]
    fg_keys = ["—"] + list(fg_items.keys())

    if jc:
        try:
            default_date = date.fromisoformat(str(jc["job_date"])[:10])
        except ValueError:
            default_date = date.today()
        wh_lbl = next((k for k, v in wh_items.items() if v == jc.get("warehouse_id")), wh_keys[0])
        fg_lbl = "—"
        if jc.get("finished_product_id"):
            fg_lbl = next(
                (k for k, v in fg_items.items() if v["id"] == jc["finished_product_id"]),
                fg_lbl,
            )
            if fg_lbl == "—" and jc.get("finished_product_code"):
                fg_lbl = f"{jc['finished_product_code']} — {jc.get('finished_product_name') or jc.get('job_name') or ''}"
        default_fgq = float(jc.get("finished_qty") or 1)
        default_name = jc.get("job_name") or ""
        default_remarks = jc.get("remarks") or ""
        doc_val = jc["document_no"]
    else:
        default_date = date.today()
        wh_lbl = wh_keys[0]
        fg_lbl = "—"
        default_fgq = 1.0
        default_name = ""
        default_remarks = ""
        doc_val = db.peek_document(DOC_TYPE_BY_JOB.get(st.session_state.get("jc_type", "gravure"), "JCG"))

    c1, c2, c3 = st.columns(3)
    c1.text_input("Job Card No", value=doc_val, disabled=bool(jc), key=f"{prefix}_doc")
    job_date = c2.date_input("Date", value=default_date, key=f"{prefix}_date")
    wh_lbl = c3.selectbox(
        "Warehouse",
        wh_keys,
        index=wh_keys.index(wh_lbl) if wh_lbl in wh_keys else 0,
        key=f"{prefix}_wh",
    )

    st.markdown("#### Produced item (header — like BOM finished product)")
    h1, h2, h3 = st.columns([3, 1, 1])
    fg_lbl = h1.selectbox(
        "Produced item *",
        fg_keys,
        index=fg_keys.index(fg_lbl) if fg_lbl in fg_keys else 0,
        key=f"{prefix}_fg",
    )
    fg_qty = h2.number_input("Production qty *", min_value=0.0, value=default_fgq, key=f"{prefix}_fgq")
    fg_id = fg_items[fg_lbl]["id"] if fg_lbl in fg_items else (jc.get("finished_product_id") if jc else None)

    if h3.button("Load from BOM", key=f"{prefix}_bom") and fg_id and fg_qty > 0:
        loaded = bom_material_lines(fg_id, fg_qty)
        if loaded:
            st.session_state[f"{prefix}_mat"] = [
                {"product_id": ln["product_id"], "quantity": ln["quantity"], "rate": ln["rate"]}
                for ln in loaded
            ]
            _seed_material_lines(prefix, st.session_state[f"{prefix}_mat"])
            ff.action_done(f"Loaded {len(loaded)} line(s) from approved BOM (adjust qty for actual use).")
        else:
            st.warning("No approved BOM with material lines for this product.")

    job_name = st.text_input(
        "Job name / description",
        value=default_name or (fg_lbl.split(" — ", 1)[-1] if fg_lbl != "—" else ""),
        key=f"{prefix}_name",
        placeholder="Defaults to produced item name",
    )
    remarks = st.text_input("Remarks", value=default_remarks, key=f"{prefix}_rem")

    mat_lines = _material_lines_editor(raw_items, prefix)

    hdr = {
        "document_no": doc_val,
        "job_type": jc["job_type"] if jc else st.session_state.get("jc_type", "gravure"),
        "job_date": str(job_date),
        "job_name": job_name.strip(),
        "finished_product_id": fg_id,
        "warehouse_id": wh_items.get(wh_lbl),
        "finished_qty": fg_qty,
        "remarks": remarks,
    }
    return hdr, mat_lines, edit_id


def _post_job_card_feedback(warnings):
    if warnings:
        st.warning(
            "Posted — some materials were below required stock. "
            "Correct stock levels when ready; strict blocking will be added later."
        )
        for w in warnings:
            st.caption(f"• {w}")
    else:
        st.success("Posted.")


def _after_save_cleanup(prefix):
    _clear_prefix_keys(prefix)
    st.session_state.pop(f"{prefix}_edit_id", None)
    _clear_job_card_edit()


def _new_job_card_tab():
    raw_items = _material_opts()
    fg_items = _fg_opts()
    wh_items = _wh_opts()
    if not raw_items:
        st.warning("Add products first (**Products** screen).")
    if not fg_items:
        st.warning("Add **finished** products for the produced item.")

    edit_jc = None
    edit_id = st.session_state.get("jc_edit_id")
    if edit_id and st.session_state.get("jc_edit_from") == "new":
        edit_jc = get_job_card(edit_id)
        if edit_jc and edit_jc.get("status") == "draft":
            st.info(f"Editing draft **{edit_jc['document_no']}** — save to update or cancel below.")
        else:
            edit_jc = None
            _clear_job_card_edit()

    job_type = st.selectbox(
        "Job card type",
        list(JOB_TYPES.keys()),
        index=list(JOB_TYPES.keys()).index(edit_jc["job_type"]) if edit_jc else 0,
        format_func=lambda x: JOB_TYPES[x],
        key="jc_type",
        disabled=bool(edit_jc),
    )
    prefix = f"jc_{job_type}"
    st.session_state["jc_prefix"] = prefix

    if edit_jc and not st.session_state.get(f"{prefix}_mat"):
        _seed_material_lines(prefix, _lines_from_job_card(edit_jc))
        st.session_state[f"{prefix}_edit_id"] = edit_jc["id"]

    hdr, mat_lines, eid = _job_card_form_body(
        prefix, raw_items, fg_items, wh_items, edit_jc, st.session_state.get(f"{prefix}_edit_id")
    )
    hdr["job_type"] = job_type

    b1, b2, b3 = st.columns(3)
    if b1.button("Save draft", type="primary", key=f"{prefix}_save"):
        try:
            jid = save_job_card(hdr, mat_lines, st.session_state.get(f"{prefix}_edit_id"), uid())
            _after_save_cleanup(prefix)
            ff.action_done(f"Saved job card **{hdr['document_no']}** (#{jid}).")
        except Exception as e:
            st.error(str(e))
    if b2.button("Save & post to stock", key=f"{prefix}_post"):
        try:
            if not hdr.get("finished_product_id") or hdr.get("finished_qty", 0) <= 0:
                raise ValueError("Select produced item and production qty.")
            jid = save_job_card(hdr, mat_lines, st.session_state.get(f"{prefix}_edit_id"), uid())
            warns = post_job_card(jid, uid())
            _post_job_card_feedback(warns)
            st.caption("Materials out, finished goods in.")
            _after_save_cleanup(prefix)
            st.rerun()
        except Exception as e:
            st.error(str(e))
    if edit_jc and b3.button("Cancel edit", key=f"{prefix}_cancel"):
        _after_save_cleanup(prefix)
        st.rerun()


def _register_edit_form(jc, raw_items, fg_items, wh_items):
    prefix = f"jc_ed_{jc['id']}"
    st.markdown("#### Edit job card")
    hdr, mat_lines, _ = _job_card_form_body(prefix, raw_items, fg_items, wh_items, jc, jc["id"])
    u1, u2, u3 = st.columns(3)
    if u1.button("Update draft", type="primary", key=f"{prefix}_upd"):
        try:
            save_job_card(hdr, mat_lines, jc["id"], uid())
            _clear_prefix_keys(prefix)
            st.session_state.pop("jc_edit_id", None)
            ff.action_done(f"Updated **{jc['document_no']}**.")
        except Exception as e:
            st.error(str(e))
    if u2.button("Update & post to stock", key=f"{prefix}_post"):
        try:
            if not hdr.get("finished_product_id") or hdr.get("finished_qty", 0) <= 0:
                raise ValueError("Select produced item and production qty.")
            save_job_card(hdr, mat_lines, jc["id"], uid())
            warns = post_job_card(jc["id"], uid())
            _post_job_card_feedback(warns)
            st.caption("Updated and posted.")
            _clear_prefix_keys(prefix)
            st.session_state.pop("jc_edit_id", None)
            st.rerun()
        except Exception as e:
            st.error(str(e))
    if u3.button("Cancel", key=f"{prefix}_cancel"):
        _clear_prefix_keys(prefix)
        st.session_state.pop("jc_edit_id", None)
        st.rerun()


def _register_tab():
    raw_items = _material_opts()
    fg_items = _fg_opts()
    wh_items = _wh_opts()

    c1, c2, c3 = st.columns(3)
    jtype = c1.selectbox(
        "Type", ["All"] + list(JOB_TYPES.keys()),
        format_func=lambda x: "All types" if x == "All" else JOB_TYPES[x],
        key="jc_reg_type",
    )
    fd = str(c2.date_input("From", value=date.today().replace(day=1), key="jc_reg_from"))
    td = str(c3.date_input("To", value=date.today(), key="jc_reg_to"))
    rows = get_job_cards(None if jtype == "All" else jtype, fd, td)
    if not rows:
        st.info("No job cards in this period.")
        return

    draft_n = sum(1 for r in rows if (r.get("status") or "draft") == "draft")
    posted_n = sum(1 for r in rows if (r.get("status") or "") == "posted")
    k1, k2, k3 = st.columns(3, gap="small")
    k1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Job Cards</p>"
        f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
        unsafe_allow_html=True,
    )
    k2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Draft</p>"
        f"<p class='txn-kpi-val'>{draft_n:,}</p></div>",
        unsafe_allow_html=True,
    )
    k3.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Posted</p>"
        f"<p class='txn-kpi-val'>{posted_n:,}</p></div>",
        unsafe_allow_html=True,
    )
    from html import escape
    ths = "".join(
        f"<th>{h}</th>"
        for h in ("Job Card", "Date", "Type", "Produced", "Prod Qty", "Material Cost", "Status")
    )
    body = []
    for r in rows:
        st_key = (r.get("status") or "draft").lower()
        badge = (
            '<span class="inv-badge inv-badge-approved">Posted</span>'
            if st_key == "posted"
            else status_badge_html("draft")
        )
        body.append(
            "<tr>"
            f"<td>{escape(str(r.get('document_no') or ''))}</td>"
            f"<td>{escape(str(r.get('job_date') or ''))}</td>"
            f"<td>{escape(JOB_TYPES.get(r.get('job_type'), r.get('job_type') or ''))}</td>"
            f"<td>{escape(str(r.get('finished_product_name') or r.get('job_name') or ''))}</td>"
            f"<td class='txn-num'>{float(r.get('finished_qty') or 0):,.3f}</td>"
            f"<td class='txn-num'>{escape(fmt_money(r.get('total_material_cost')))}</td>"
            f"<td class='txn-status-cell'>{badge}</td>"
            "</tr>"
        )
    st.markdown(
        '<div class="txn-reg-wrap"><table class="txn-reg-table">'
        f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
        unsafe_allow_html=True,
    )

    opts = {f"{r['document_no']} — {r.get('finished_product_name') or r['job_name']} [{r['status']}]": r["id"] for r in rows}
    sel = st.selectbox("Select", list(opts.keys()), key="jc_reg_sel")
    jid = opts[sel]
    jc = get_job_card(jid)
    if not jc:
        return

    if st.session_state.get("jc_edit_id") and st.session_state["jc_edit_id"] != jid:
        _clear_job_card_edit()

    st.markdown(
        f"### {jc['document_no']}  \n"
        f"**Type:** {JOB_TYPES.get(jc['job_type'], jc['job_type'])} · "
        f"**Date:** {jc['job_date']} · **Status:** {jc['status']}"
    )

    if jc["status"] == "draft":
        stock_warns = job_card_stock_warnings(jc)
        if stock_warns:
            for w in stock_warns:
                st.warning(w)
            st.info("Post is still allowed; stock checks will be enforced after stock levels are corrected.")

        a1, a2, a3, a4 = st.columns(4)
        with a1:
            if st.button("Edit / Update", type="primary", key="jc_reg_edit"):
                st.session_state["jc_edit_id"] = jid
                _seed_material_lines(f"jc_ed_{jid}", _lines_from_job_card(jc))
                st.rerun()
        with a2:
            if st.button("Post to stock", key="jc_reg_post"):
                try:
                    warns = post_job_card(jid, uid())
                    st.session_state.pop("jc_edit_id", None)
                    st.session_state["jc_post_warns"] = warns
                    st.rerun()
                except Exception as e:
                    st.error(str(e))
        with a3:
            if st.button("Delete", key="jc_reg_del"):
                try:
                    delete_job_card(jid)
                    _clear_job_card_edit()
                    ff.action_done("Deleted.")
                except Exception as e:
                    st.error(str(e))
        with a4:
            if st.button("Edit on New tab", key="jc_reg_edit_new"):
                st.session_state["jc_edit_id"] = jid
                st.session_state["jc_edit_from"] = "new"
                st.session_state["jc_type"] = jc["job_type"]
                prefix = f"jc_{jc['job_type']}"
                _clear_prefix_keys(prefix)
                _seed_material_lines(prefix, _lines_from_job_card(jc))
                st.session_state[f"{prefix}_edit_id"] = jid
                st.info("Switch to **New Job Card** tab to edit, then **Save draft** or **Update**.")
                st.rerun()
    else:
        st.caption("Posted job cards cannot be edited or deleted.")

    pending = st.session_state.pop("jc_post_warns", None)
    if pending is not None and jc["status"] == "posted":
        _post_job_card_feedback(pending)

    if jc["status"] == "draft" and st.session_state.get("jc_edit_id") == jid:
        _register_edit_form(jc, raw_items, fg_items, wh_items)
        st.divider()

    if jc.get("material_lines") and st.session_state.get("jc_edit_id") != jid:
        st.subheader("Consumption")
        from erp_ui.helpers import render_dataframe_html_table
        render_dataframe_html_table(pd.DataFrame([{
            "Code": ln.get("product_code") or "—",
            "Material": ln.get("product_name"),
            "Qty": float(ln["quantity"]),
            "Rate": float(ln.get("rate") or 0),
            "Amount": float(ln.get("amount") or 0),
        } for ln in jc["material_lines"]]))

    from erp_ui.document_print import document_print_toolbar
    document_print_toolbar("Job Card", jc["id"], key_prefix="jc_reg_print")


def page_job_cards():
    peek = st.session_state.get("jc_page_tab") or "Register & Print"
    std_page_header(
        "Job Cards",
        status="register" if peek == "Register & Print" else None,
        status_kind="shell" if peek == "Register & Print" else "invoice",
    )
    tab = sticky_page_tabs(["New Job Card", "Register & Print"], "jc_page_tab")
    if tab == "New Job Card":
        _new_job_card_tab()
    elif tab == "Register & Print":
        _register_tab()
