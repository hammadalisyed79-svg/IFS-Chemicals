"""V14 RC1 — complete document open center for all transactional types."""

from __future__ import annotations

import streamlit as st

from erp_ui import form_flow as ff
from erp_core.document_workflow import execute_action, get_document_history, resolve_doc_type
from erp_core.approval_engine import get_approval_history
from erp_core.gl_drilldown import render_gl_drilldown_panel
from erp_core.transaction_engine import (
    document_label,
    get_document_spec,
    is_editable,
    log_document_open,
    search_documents,
)
from erp_ui.helpers import fmt_money, section_header
from erp_ui.nav import request_nav


def render_document_hub(doc_type: str, key_prefix: str, *, show_duplicate: bool = True) -> int | None:
    key = resolve_doc_type(doc_type)
    spec = get_document_spec(key)
    if not spec:
        st.warning(f"Document type '{doc_type}' is not registered.")
        return None

    section_header(f"Open — {spec.label}")
    q = st.text_input(
        "Search",
        placeholder=f"{spec.label} number, party, notes…",
        key=f"{key_prefix}_hub_q",
    )
    rows = search_documents(spec, q, limit=30) if (q or "").strip() else []
    if (q or "").strip() and not rows:
        st.info("No matching documents.")

    selected_id = st.session_state.get(f"{key_prefix}_open_id")
    uid = st.session_state.get("user", {}).get("id")
    user = st.session_state.get("user") or {}

    if rows:
        labels = [document_label(r, spec) for r in rows]
        pick = st.selectbox("Select document", labels, key=f"{key_prefix}_hub_pick")
        row = rows[labels.index(pick)]
        selected_id = row["id"]
        st.session_state[f"{key_prefix}_open_id"] = selected_id
        _render_actions(spec, row, key_prefix, uid, user, show_duplicate)

    ent_id = st.session_state.get("enterprise_open_record_id")
    ent_type = st.session_state.get("enterprise_open_doc_type")
    if ent_type == key and ent_id:
        st.session_state[f"{key_prefix}_open_id"] = ent_id
        if spec.get_fn:
            row = spec.get_fn(ent_id)
            if row:
                _seed_open(spec, row, key_prefix)
        st.session_state.pop("enterprise_open_record_id", None)
        st.session_state.pop("enterprise_open_doc_type", None)

    if selected_id and spec.get_fn:
        full = spec.get_fn(selected_id)
        if full and st.checkbox("Show history & GL", key=f"{key_prefix}_show_hist"):
            _render_history(spec, selected_id, full)

    return selected_id


def _render_actions(spec, row, key_prefix, uid, user, show_duplicate):
    rid = row["id"]
    editable = is_editable(row, spec)
    can_approve = bool(spec.approve_fn or spec.post_fn)
    can_reject = spec.key in ("sales_invoice", "purchase_invoice")
    status = (row.get("status") or "draft").lower()

    r1c = st.columns(6)
    if r1c[0].button("Open", key=f"{key_prefix}_open", use_container_width=True):
        _seed_open(spec, row, key_prefix)
        log_document_open(spec, rid, row.get(spec.no_field, ""), uid)
        st.rerun()
    if r1c[1].button("Edit Draft", key=f"{key_prefix}_edit", use_container_width=True, disabled=not editable):
        _seed_open(spec, row, key_prefix, edit=True)
        st.rerun()
    if show_duplicate and r1c[2].button("Duplicate", key=f"{key_prefix}_dup", use_container_width=True):
        st.session_state[f"{key_prefix}_duplicate_from"] = rid
        st.success("Open the **New** tab to complete the duplicate.")
    if r1c[3].button("Delete Draft", key=f"{key_prefix}_del", use_container_width=True,
                     disabled=not (spec.delete_fn and editable)):
        try:
            execute_action(spec.key, "delete", rid, uid)
            st.success("Deleted.")
            st.session_state.pop(f"{key_prefix}_open_id", None)
            st.rerun()
        except Exception as exc:
            st.error(str(exc))
    if r1c[4].button("Export PDF", key=f"{key_prefix}_pdf", use_container_width=True):
        st.session_state[f"{key_prefix}_print_id"] = rid
        _render_print_panel(spec, rid, key_prefix)
    if r1c[5].button("History", key=f"{key_prefix}_hist", use_container_width=True):
        st.session_state[f"{key_prefix}_show_hist_flag"] = True

    r2c = st.columns(5)
    reject_reason = r2c[0].text_input("Reject reason", key=f"{key_prefix}_rej_reason", label_visibility="collapsed",
                                       placeholder="Reject reason…") if can_reject else ""
    if r2c[1].button("Approve", key=f"{key_prefix}_app", use_container_width=True,
                     disabled=not can_approve or status in ("approved", "posted")):
        try:
            execute_action(spec.key, "approve", rid, uid)
            ff.action_done("Approved.")
        except Exception as exc:
            st.error(str(exc))
    if r2c[2].button("Reject", key=f"{key_prefix}_rej", use_container_width=True,
                     disabled=not can_reject or status not in ("draft", "pending_approval")):
        try:
            execute_action(spec.key, "reject", rid, uid, reason=reject_reason)
            ff.action_done("Rejected.")
        except Exception as exc:
            st.error(str(exc))
    if r2c[3].button("Post", key=f"{key_prefix}_post", use_container_width=True,
                     disabled=not spec.post_fn or status == "posted"):
        try:
            execute_action(spec.key, "post", rid, uid)
            ff.action_done("Posted.")
        except Exception as exc:
            st.error(str(exc))
    if r2c[4].button("Print", key=f"{key_prefix}_prt", use_container_width=True):
        st.session_state[f"{key_prefix}_print_id"] = rid
        _render_print_panel(spec, rid, key_prefix)

    from erp_ui.invoice_status_ui import status_badge_html
    st.markdown(
        f'{status_badge_html(row.get("status") or "draft")} · '
        f"<strong>{fmt_money(row.get('total') or row.get('subtotal') or 0)}</strong>",
        unsafe_allow_html=True,
    )

    if st.session_state.get(f"{key_prefix}_print_id") == rid:
        _render_print_panel(spec, rid, key_prefix)


def _render_print_panel(spec, rid, key_prefix):
    from erp_core.print_engine import record_print
    from erp_ui.document_print import document_print_toolbar, PRINTERS

    doc_no = ""
    if spec.get_fn:
        rec = spec.get_fn(rid)
        doc_no = rec.get(spec.no_field, "") if rec else ""
        is_draft = (rec.get("status") or "draft").lower() in ("draft", "rejected")
    else:
        is_draft = True
    ptype = spec.label
    if ptype in PRINTERS or spec.key in ("sales_invoice", "purchase_invoice"):
        document_print_toolbar(ptype if ptype in PRINTERS else "Sales Invoice", rid, key_prefix=f"{key_prefix}_doc")
    record_print(spec.key, spec.table, rid, doc_no, st.session_state.get("user", {}).get("id"), is_draft=is_draft)


def _render_history(spec, rid, full):
    section_header("Audit & approval history")
    for h in get_approval_history(spec.key, rid):
        st.caption(
            f"{h.get('acted_at', '')} — **{h.get('action', '')}** by {h.get('acted_by_name', '—')}"
            + (f" — {h.get('comments')}" if h.get("comments") else "")
        )
    for h in get_document_history(spec, rid)[:10]:
        st.caption(f"Audit: {h.get('action', '')} — {h.get('summary', h.get('details', ''))}")
    ref_type = spec.key.replace("_invoice", "")
    render_gl_drilldown_panel(ref_type if ref_type != "sales" else "sales_invoice", rid, key_prefix=f"hub_{rid}")


def _seed_open(spec, row: dict, key_prefix: str, *, edit: bool = False) -> None:
    st.session_state["draft_open_id"] = row["id"]
    st.session_state["draft_open_table"] = spec.table
    seeds = {
        "sales_invoice": ("sal_edit_id", "sal_open_tab", "edit"),
        "purchase_invoice": ("pur_edit_id", "pur_open_tab", "edit"),
        "sales_return": ("sr_edit_id", "sr_open_tab", "edit"),
        "purchase_return": ("pr_edit_id", "pr_open_tab", "edit"),
    }
    if spec.key in seeds:
        k1, k2, val = seeds[spec.key]
        st.session_state[k1] = row["id"]
        if k2:
            st.session_state[k2] = val
    if edit:
        request_nav(spec.nav_group, spec.nav_screen)
