"""Professional BOM (Composition) & Production — detergents, liquids, corrugated, gravure printing."""

from datetime import date
import pandas as pd
import streamlit as st
from application import data_gateway as db
from application.data_gateway import COMPOSITION_TYPES, suggest_next_bom_version
from erp_ui.helpers import uid, std_page_header, fmt_money, money_input, sticky_page_tabs, render_dataframe_html_table
from erp_ui.invoice_status_ui import status_badge_html
from erp_ui import form_flow as ff


def _fmt(v):
    return fmt_money(v)


def _composition_label(code):
    return COMPOSITION_TYPES.get(code, code or "—")


def _draft_production_orders(rows):
    return [r for r in rows if (r.get("status") or "draft") == "draft"]


def _deletable_production_orders(rows):
    """Draft, issued, or completed (delete reverses stock/GL)."""
    ok = {"draft", "issued", "completed"}
    return [r for r in rows if (r.get("status") or "draft").lower() in ok]


def _production_order_edit_form(po, bom_opts, wh_opts, mach_opts, key_prefix="prod_edit"):
    """Form to edit a draft production order; returns payload dict or None if not submitted."""
    bom_keys = list(bom_opts.keys())
    bom_default = 0
    for i, k in enumerate(bom_keys):
        if bom_opts[k]["id"] == po.get("bom_id"):
            bom_default = i
            break
    wh_keys = list(wh_opts.keys()) if wh_opts else []
    wh_default = 0
    for i, k in enumerate(wh_keys):
        if wh_opts.get(k) == po.get("warehouse_id"):
            wh_default = i
            break
    mach_keys = ["— None —"] + list(mach_opts.keys())
    mach_default = 0
    if po.get("machine_id"):
        for i, m in enumerate(mach_keys[1:], start=1):
            if mach_opts.get(m) == po["machine_id"]:
                mach_default = i
                break
    try:
        od_val = date.fromisoformat(str(po.get("order_date") or date.today()))
    except ValueError:
        od_val = date.today()

    with st.form(f"{key_prefix}_form"):
        st.caption(f"Order **{po.get('document_no')}** | Batch **{po.get('batch_no')}** (document no. cannot change)")
        bl = st.selectbox("Approved Composition *", bom_keys, index=min(bom_default, len(bom_keys) - 1))
        b = bom_opts[bl]
        c1, c2, c3 = st.columns(3)
        pq = c1.number_input(
            "Planned Qty *", min_value=0.001,
            value=float(po.get("planned_qty") or 1), key=f"{key_prefix}_pq",
        )
        od = c2.date_input("Production Date", value=od_val, key=f"{key_prefix}_od")
        batch = c3.text_input("Batch No *", value=po.get("batch_no") or "", key=f"{key_prefix}_bat")
        wh_lbl = st.selectbox(
            "Warehouse",
            wh_keys or ["—"],
            index=min(wh_default, max(len(wh_keys) - 1, 0)),
            key=f"{key_prefix}_wh",
        )
        mach_lbl = st.selectbox(
            "Machine / Line", mach_keys,
            index=min(mach_default, len(mach_keys) - 1),
            key=f"{key_prefix}_mach",
        )
        st.markdown("**Conversion Costs (optional)**")
        cc1, cc2, cc3, cc4 = st.columns(4)
        with cc1:
            labour = money_input("Labour", value=float(po.get("labour_cost") or 0), min_value=0.0, key=f"{key_prefix}_lab")
        with cc2:
            utility = money_input("Utility / Power", value=float(po.get("utility_cost") or 0), min_value=0.0, key=f"{key_prefix}_ut")
        with cc3:
            packing = money_input("Packing", value=float(po.get("packing_cost") or 0), min_value=0.0, key=f"{key_prefix}_pk")
        with cc4:
            overhead = money_input("Overhead", value=float(po.get("overhead_cost") or 0), min_value=0.0, key=f"{key_prefix}_oh")
        notes = st.text_input("Notes", value=po.get("notes") or "", key=f"{key_prefix}_notes")
        if st.form_submit_button("Update Production Order", type="primary"):
            return {
                "order_date": str(od),
                "bom_id": b["id"],
                "finished_product_id": b["finished_product_id"],
                "planned_qty": pq,
                "batch_no": batch.strip(),
                "warehouse_id": wh_opts.get(wh_lbl) if wh_opts and wh_lbl in wh_opts else None,
                "machine_id": mach_opts.get(mach_lbl) if mach_lbl != "— None —" else None,
                "labour_cost": labour,
                "utility_cost": utility,
                "packing_cost": packing,
                "overhead_cost": overhead,
                "notes": notes,
            }
    return None


def _finished_product_opts():
    rows = [r for r in db.get_items(active_only=True) if r.get("item_type") == "finished" or r.get("product_type") == "finished"]
    if not rows:
        rows = db.get_items(active_only=True)
    return {f"{r['code']} - {r['name']}": r for r in rows}


def _all_material_opts():
    return {f"{r['code']} - {r['name']}": r for r in db.get_items(active_only=True)}


def _bom_line_editor(items_dict, key_prefix, default_lines=None):
    sk = f"{key_prefix}_lines"
    if default_lines is not None:
        st.session_state[sk] = default_lines
    if sk not in st.session_state or not st.session_state[sk]:
        st.session_state[sk] = [{
            "raw_product_id": None, "quantity": 1.0, "wastage_pct": 0.0,
            "standard_cost": 0.0, "line_cost": 0.0,
        }]
    st.markdown(
        "**Components** — Item | Type | Unit | Qty | Wastage % | Rate | Amount"
    )
    labels = list(items_dict.keys()) if items_dict else []
    updated, to_remove = [], []
    for i, line in enumerate(st.session_state[sk]):
        cols = st.columns([3, 1, 0.8, 1, 1, 1, 1, 0.4])
        pid = line.get("raw_product_id")
        default_lbl = next((k for k, v in items_dict.items() if v["id"] == pid), labels[0] if labels else None)
        sel = cols[0].selectbox(
            "Item", labels,
            index=labels.index(default_lbl) if default_lbl in labels else 0,
            key=f"{key_prefix}_item_{i}", label_visibility="collapsed",
        ) if labels else None
        prod = items_dict.get(sel) if sel else None
        ptype = (prod.get("item_type") or prod.get("product_type") or "—") if prod else "—"
        cols[1].caption(str(ptype).replace("_", " ").title())
        cols[2].caption(prod.get("unit") or "—" if prod else "—")
        qty = cols[3].number_input("Qty", min_value=0.0, value=float(line.get("quantity", 1)), key=f"{key_prefix}_q_{i}", label_visibility="collapsed")
        wastage = cols[4].number_input("Wast %", min_value=0.0, max_value=100.0, value=float(line.get("wastage_pct", 0)), key=f"{key_prefix}_w_{i}", label_visibility="collapsed")
        with cols[5]:
            rate = money_input(
                "Rate",
                value=float(line.get("standard_cost") or (prod.get("purchase_price") if prod else 0) or 0),
                min_value=0.0,
                key=f"{key_prefix}_r_{i}",
                label_visibility="collapsed",
            )
        amount = qty * rate
        cols[6].write(f"{amount:,.2f}")
        if cols[7].button("✕", key=f"{key_prefix}_del_{i}"):
            to_remove.append(i)
        elif prod:
            updated.append({
                "raw_product_id": prod["id"],
                "quantity": qty,
                "unit_id": prod.get("unit_id"),
                "wastage_pct": wastage,
                "standard_cost": rate,
                "line_cost": amount,
                "weight_required": qty * float(prod.get("standard_weight") or 0),
            })
    if to_remove:
        st.session_state[sk] = [ln for j, ln in enumerate(st.session_state[sk]) if j not in to_remove]
        st.rerun()
    st.session_state[sk] = updated
    if st.button("+ Add Component", key=f"{key_prefix}_add"):
        st.session_state[sk].append({
            "raw_product_id": None, "quantity": 1.0, "wastage_pct": 0.0,
            "standard_cost": 0.0, "line_cost": 0.0,
        })
        st.rerun()
    total = sum(l.get("line_cost", 0) for l in updated)
    st.caption(f"**{len(updated)}** component(s) | Standard material cost: **{_fmt(total)}**")
    return updated, total


def _bom_register():
    c1, c2, c3, c4 = st.columns([2, 2, 1, 1])
    q = c1.text_input("Search", placeholder="Code, product, description...", key="bom_reg_q")
    ctype = c2.selectbox(
        "Composition Type",
        ["All"] + list(COMPOSITION_TYPES.keys()),
        format_func=lambda x: "All types" if x == "All" else _composition_label(x),
        key="bom_reg_type",
    )
    status = c3.selectbox("Status", ["All", "draft", "approved", "inactive"], key="bom_reg_st")
    fp_opts = _finished_product_opts()
    fp_lbl = c4.selectbox("Product", ["All"] + list(fp_opts.keys()), key="bom_reg_fp")
    fp_id = fp_opts[fp_lbl]["id"] if fp_lbl != "All" else None
    result = db.search_bom_formulas(
        q=q or None,
        composition_type=ctype,
        status=status,
        finished_product_id=fp_id,
        page=1,
        page_size=50,
    )
    # run_paginated_list returns "items" (not "rows")
    rows = result.get("items") or result.get("rows") or []
    if not rows:
        tip = (
            "No compositions match these filters. "
            "Clear **Search**, set **Composition Type** to **All types**, "
            "then look under **Other / General Assembly** for FMYE-imported formulas "
            "(e.g. BASE POWDER)."
        )
        if ctype and ctype != "All":
            tip += f" Current type filter: **{_composition_label(ctype)}**."
        st.info(tip)
        return
    df = pd.DataFrame([{
        "Code": r["document_no"],
        "Date": r.get("composition_date") or r.get("created_at", "")[:10],
        "Finished Product": f"{r.get('finished_product_code','')} — {r.get('finished_product_name','')}",
        "Type": _composition_label(r.get("composition_type")),
        "Version": r.get("version_no"),
        "Output Qty": r.get("standard_output_qty"),
        "Std Cost": _fmt(r.get("standard_cost")),
        "Status": r.get("status"),
    } for r in rows])
    draft_n = sum(1 for r in rows if (r.get("status") or "").lower() == "draft")
    appr_n = sum(1 for r in rows if (r.get("status") or "").lower() == "approved")
    k1, k2, k3 = st.columns(3, gap="small")
    k1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Compositions</p>"
        f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
        unsafe_allow_html=True,
    )
    k2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Approved</p>"
        f"<p class='txn-kpi-val'>{appr_n:,}</p></div>",
        unsafe_allow_html=True,
    )
    k3.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Draft</p>"
        f"<p class='txn-kpi-val'>{draft_n:,}</p></div>",
        unsafe_allow_html=True,
    )
    if draft_n or appr_n:
        parts = []
        if appr_n:
            parts.append(f'{status_badge_html("approved")}&nbsp;<strong>{appr_n}</strong>')
        if draft_n:
            parts.append(f'{status_badge_html("draft")}&nbsp;<strong>{draft_n}</strong>')
        st.markdown(
            f'<div class="txn-status-strip">{" &nbsp;·&nbsp; ".join(parts)}</div>',
            unsafe_allow_html=True,
        )
    render_dataframe_html_table(df)
    st.caption(f"{len(rows)} of {result.get('total', len(rows))} composition(s)")


def _render_production_order_table(rows):
    """Production order register with status badges."""
    from html import escape

    if not rows:
        return
    draft_n = sum(1 for r in rows if (r.get("status") or "draft") == "draft")
    issued_n = sum(1 for r in rows if (r.get("status") or "").lower() == "issued")
    done_n = sum(1 for r in rows if (r.get("status") or "").lower() == "completed")
    k1, k2, k3, k4 = st.columns(4, gap="small")
    k1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Orders</p>"
        f"<p class='txn-kpi-val'>{len(rows):,}</p></div>",
        unsafe_allow_html=True,
    )
    k2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Draft</p>"
        f"<p class='txn-kpi-val'>{draft_n:,}</p></div>",
        unsafe_allow_html=True,
    )
    k3.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Issued</p>"
        f"<p class='txn-kpi-val'>{issued_n:,}</p></div>",
        unsafe_allow_html=True,
    )
    k4.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Completed</p>"
        f"<p class='txn-kpi-val'>{done_n:,}</p></div>",
        unsafe_allow_html=True,
    )
    ths = "".join(
        f"<th>{h}</th>"
        for h in ("Order No", "Batch", "Date", "Product", "BOM", "Planned", "Actual", "Status", "QC")
    )
    body = []
    for r in rows:
        st_key = (r.get("status") or "draft").lower()
        badge = status_badge_html(st_key if st_key in ("draft", "approved", "cancelled") else "approved")
        if st_key == "issued":
            badge = '<span class="inv-badge inv-badge-pending">Issued</span>'
        elif st_key == "completed":
            badge = '<span class="inv-badge inv-badge-approved">Completed</span>'
        qc = (r.get("qc_status") or "—").strip()
        qc_badge = (
            '<span class="inv-badge inv-badge-approved">Passed</span>'
            if qc.lower() in ("passed", "pass", "ok")
            else f'<span class="inv-badge inv-badge-draft">{escape(qc)}</span>'
        )
        body.append(
            "<tr>"
            f"<td>{escape(str(r.get('document_no') or ''))}</td>"
            f"<td>{escape(str(r.get('batch_no') or '—'))}</td>"
            f"<td>{escape(str(r.get('order_date') or ''))}</td>"
            f"<td>{escape(str(r.get('product_name') or ''))}</td>"
            f"<td>{escape(str(r.get('bom_no') or '—'))}</td>"
            f"<td class='txn-num'>{float(r.get('planned_qty') or 0):,.3f}</td>"
            f"<td class='txn-num'>{float(r.get('actual_qty') or 0):,.3f}</td>"
            f"<td class='txn-status-cell'>{badge}</td>"
            f"<td class='txn-status-cell'>{qc_badge}</td>"
            "</tr>"
        )
    st.markdown(
        '<div class="txn-reg-wrap"><table class="txn-reg-table">'
        f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
        unsafe_allow_html=True,
    )


def page_bom_composition():
    peek = st.session_state.get("bom_page_tab") or "Register"
    std_page_header(
        "BOM",
        title="Composition / BOM",
        status="register" if peek == "Register" else None,
        status_kind="shell" if peek == "Register" else "invoice",
    )
    # One-shot: classify imported FMYE formulas still tagged "other"
    if not st.session_state.get("_bom_types_repaired"):
        try:
            db.repair_bom_composition_types()
        except Exception:
            pass
        st.session_state["_bom_types_repaired"] = True
    tab = sticky_page_tabs(["Register", "New Composition", "Edit / Approve"], "bom_page_tab")

    if tab == "Register":
        _bom_register()

    fp_opts = _finished_product_opts()
    mat_opts = _all_material_opts()

    if tab == "New Composition":
        if not fp_opts or not mat_opts:
            st.warning("Add finished products and raw/packaging materials first.")
            return
        with st.form("bom_new_form"):
            c1, c2, c3 = st.columns(3)
            comp_code = c1.text_input("Composition Code", value=db.peek_document("BOM"))
            comp_date = c2.date_input("Date", value=date.today())
            comp_type = c3.selectbox(
                "Composition Type",
                list(COMPOSITION_TYPES.keys()),
                format_func=_composition_label,
            )
            fp_lbl = st.selectbox("Finished Product (Item Name) *", list(fp_opts.keys()))
            fp = fp_opts[fp_lbl]
            suggested_ver = suggest_next_bom_version(fp["id"])
            c4, c5, c6 = st.columns(3)
            version = c4.text_input("Version", value=suggested_ver)
            out_qty = c5.number_input("Standard Output Qty", min_value=0.001, value=1.0, step=1.0)
            out_unit = fp.get("unit") or "—"
            c6.text_input("Output Unit", value=out_unit, disabled=True)
            description = st.text_area("Description / Process Notes", placeholder="Mixing time, print colours, board GSM, fill volume...")
            notes = st.text_input("Internal Notes")
            hdr_ok = st.form_submit_button("Continue to Components")
        if hdr_ok or st.session_state.get("bom_new_hdr"):
            if hdr_ok:
                st.session_state["bom_new_hdr"] = {
                    "document_no": comp_code,
                    "finished_product_id": fp["id"],
                    "version_no": version,
                    "standard_output_qty": out_qty,
                    "output_unit_id": fp.get("unit_id"),
                    "composition_type": comp_type,
                    "composition_date": str(comp_date),
                    "description": description,
                    "notes": notes,
                }
                st.session_state.pop("bom_new_lines", None)
            hdr = st.session_state["bom_new_hdr"]
            st.info(
                f"**{hdr['document_no']}** — {_composition_label(hdr.get('composition_type'))} | "
                f"Version **{hdr['version_no']}** | Output **{hdr['standard_output_qty']}**"
            )
            existing = db.get_bom_by_product_version(hdr["finished_product_id"], hdr["version_no"])
            if existing:
                st.warning(
                    f"Version **{hdr['version_no']}** already exists. "
                    f"Use **{suggest_next_bom_version(hdr['finished_product_id'])}** or edit the existing composition."
                )
            lines, total = _bom_line_editor(mat_opts, "bom_new", st.session_state.get("bom_new_lines"))
            if st.button("Save Composition", type="primary", key="bom_save_new"):
                try:
                    db.save_bom(hdr, lines, None, uid())
                    for k in ("bom_new_hdr", "bom_new_lines"):
                        st.session_state.pop(k, None)
                    ff.action_done("Composition saved as draft.")
                except Exception as e:
                    st.error(str(e).replace("**", ""))

    elif tab == "Edit / Approve":
        if st.button("Refresh all BOM costs from purchase prices", key="bom_refresh_costs"):
            try:
                with db.get_connection() as conn:
                    n = db.refresh_bom_costs(conn)
                ff.action_done(f"Updated rates on {n} BOM component line(s).")
            except Exception as e:
                st.error(str(e))
        rows = db.get_bom_list()
        if not rows:
            st.info("No compositions yet.")
            return
        if not fp_opts or not mat_opts:
            st.warning("Add finished products and materials before editing compositions.")
            return
        opts = {
            f"{r['document_no']} — {r.get('finished_product_name')} v{r.get('version_no')} [{r.get('status')}]": r["id"]
            for r in rows
        }
        sel = st.selectbox("Select Composition", list(opts.keys()), key="bom_edit_sel")
        bid = opts[sel]
        b = db.get_bom(bid)
        if not b:
            return
        used_n = 0
        try:
            used_n = db.bom_production_usage(bid)
        except Exception:
            used_n = 0
        st.markdown(
            f"**Type:** {_composition_label(b.get('composition_type'))} | "
            f"**Status:** {b.get('status')} | "
            f"**Product:** {b.get('finished_product_name') or '—'} | "
            f"**Output:** {b.get('standard_output_qty')} | "
            f"**Used on {used_n} production order(s)**"
        )
        if b.get("description"):
            st.caption(b["description"])

        editing = st.session_state.get("bom_edit_id") == bid

        a1, a2, a3, a4 = st.columns(4)
        if a1.button("Edit Composition", type="primary", key="bom_load_edit", disabled=editing):
            st.session_state["bom_edit_id"] = bid
            st.session_state["bom_edit_hdr"] = {
                "document_no": b["document_no"],
                "finished_product_id": b["finished_product_id"],
                "version_no": b["version_no"],
                "standard_output_qty": float(b.get("standard_output_qty") or 1),
                "output_unit_id": b.get("output_unit_id"),
                "composition_type": b.get("composition_type") or "other",
                "composition_date": b.get("composition_date") or str(date.today()),
                "description": b.get("description") or "",
                "notes": b.get("notes") or "",
                "status": b.get("status") or "draft",
            }
            st.session_state["bom_edit_lines"] = [{
                "raw_product_id": ln["raw_product_id"],
                "quantity": ln["quantity"],
                "unit_id": ln.get("unit_id"),
                "wastage_pct": ln.get("wastage_pct") or 0,
                "standard_cost": ln.get("standard_cost") or 0,
                "line_cost": ln.get("line_cost") or 0,
                "weight_required": ln.get("weight_required") or 0,
            } for ln in b.get("lines") or []]
            # Force line editor to reload from defaults
            st.session_state.pop("bom_edit_lines_loaded", None)
            st.rerun()
        if b.get("status") != "approved" and a2.button("Approve", key="bom_appr"):
            try:
                db.approve_bom(bid, uid())
                ff.action_done("Approved — available for production orders.")
            except Exception as e:
                st.error(str(e))
        if b.get("status") == "approved" and a2.button("Unapprove → Draft", key="bom_unappr"):
            try:
                db.set_bom_status(bid, "draft", uid())
                ff.action_done("Set back to **draft** for editing.")
            except Exception as e:
                st.error(str(e))
        if b.get("status") != "inactive" and a3.button("Set Inactive", key="bom_inactive"):
            try:
                db.set_bom_status(bid, "inactive", uid())
                ff.action_done("Composition marked **inactive**.")
            except Exception as e:
                st.error(str(e))
        if b.get("status") == "inactive" and a3.button("Reactivate → Draft", key="bom_reactivate"):
            try:
                db.set_bom_status(bid, "draft", uid())
                ff.action_done("Reactivated as **draft**.")
            except Exception as e:
                st.error(str(e))
        if a4.button("Copy to New Version", key="bom_copy"):
            try:
                nv = suggest_next_bom_version(b["finished_product_id"])
                db.copy_bom(bid, nv, uid())
                ff.action_done(f"Copied to version {nv} (draft).")
            except Exception as e:
                st.error(str(e))

        d1, d2 = st.columns([1, 3])
        force_del = d1.checkbox(
            "Force delete",
            value=False,
            key="bom_force_del",
            help="Allow delete even if used on production orders",
        )
        if d2.button("Delete Composition", key="bom_del"):
            try:
                db.delete_bom(bid, uid(), allow_used=force_del)
                for k in ("bom_edit_id", "bom_edit_hdr", "bom_edit_lines", "bom_edit_lines_loaded"):
                    st.session_state.pop(k, None)
                ff.action_done("Composition deleted.")
            except Exception as e:
                st.error(str(e).replace("**", ""))

        if editing:
            st.divider()
            st.subheader("Edit composition")
            st.caption(
                "Change product, type, version, output qty, components, rates, and status. "
                "Saving updates this record in place (no new version unless you Copy)."
            )
            hdr = dict(st.session_state.get("bom_edit_hdr") or {})
            ctype_keys = list(COMPOSITION_TYPES.keys())
            ctype_default = hdr.get("composition_type") or "other"
            if ctype_default not in ctype_keys:
                ctype_keys = ctype_keys + [ctype_default]
            fp_keys = list(fp_opts.keys())
            fp_default = next(
                (k for k, v in fp_opts.items() if v["id"] == hdr.get("finished_product_id")),
                fp_keys[0] if fp_keys else None,
            )
            try:
                cd_val = date.fromisoformat(str(hdr.get("composition_date") or date.today())[:10])
            except ValueError:
                cd_val = date.today()

            c1, c2, c3 = st.columns(3)
            c1.text_input("Composition Code", value=hdr.get("document_no") or "", disabled=True, key="bom_ed_code")
            comp_date = c2.date_input("Date", value=cd_val, key="bom_ed_date")
            status_opts = ["draft", "approved", "inactive"]
            st_cur = hdr.get("status") or "draft"
            status_sel = c3.selectbox(
                "Status",
                status_opts,
                index=status_opts.index(st_cur) if st_cur in status_opts else 0,
                key="bom_ed_status",
            )
            comp_type = st.selectbox(
                "Composition Type",
                ctype_keys,
                index=ctype_keys.index(ctype_default) if ctype_default in ctype_keys else 0,
                format_func=_composition_label,
                key="bom_ed_type",
            )
            fp_lbl = st.selectbox(
                "Finished Product *",
                fp_keys,
                index=fp_keys.index(fp_default) if fp_default in fp_keys else 0,
                key="bom_ed_fp",
            )
            fp = fp_opts[fp_lbl]
            c4, c5, c6 = st.columns(3)
            version = c4.text_input("Version", value=str(hdr.get("version_no") or "1.0"), key="bom_ed_ver")
            out_qty = c5.number_input(
                "Standard Output Qty",
                min_value=0.001,
                value=float(hdr.get("standard_output_qty") or 1),
                step=1.0,
                key="bom_ed_out",
            )
            c6.text_input("Output Unit", value=fp.get("unit") or "—", disabled=True, key="bom_ed_ou")
            description = st.text_area(
                "Description / Process Notes",
                value=hdr.get("description") or "",
                key="bom_ed_desc",
            )
            notes = st.text_input("Internal Notes", value=hdr.get("notes") or "", key="bom_ed_notes")

            # Load lines into editor once when Edit is pressed
            default_lines = None
            if not st.session_state.get("bom_edit_lines_loaded"):
                default_lines = st.session_state.get("bom_edit_lines")
                st.session_state["bom_edit_lines_loaded"] = True
            lines, _ = _bom_line_editor(mat_opts, "bom_edit", default_lines)

            s1, s2 = st.columns(2)
            if s1.button("Save Changes", type="primary", key="bom_upd"):
                try:
                    payload = {
                        "document_no": hdr.get("document_no"),
                        "finished_product_id": fp["id"],
                        "version_no": version,
                        "standard_output_qty": out_qty,
                        "output_unit_id": fp.get("unit_id"),
                        "composition_type": comp_type,
                        "composition_date": str(comp_date),
                        "description": description,
                        "notes": notes,
                        "status": status_sel,
                    }
                    db.save_bom(payload, lines, bid, uid())
                    for k in ("bom_edit_id", "bom_edit_hdr", "bom_edit_lines", "bom_edit_lines_loaded"):
                        st.session_state.pop(k, None)
                    st.session_state.pop("bom_edit_lines", None)
                    # Clear line editor widget state prefix leftovers via session key
                    st.session_state.pop("bom_edit_lines", None)
                    ff.action_done("Composition updated.")
                except Exception as e:
                    st.error(str(e).replace("**", ""))
            if s2.button("Cancel Edit", key="bom_edit_cancel"):
                for k in ("bom_edit_id", "bom_edit_hdr", "bom_edit_lines", "bom_edit_lines_loaded"):
                    st.session_state.pop(k, None)
                st.session_state.pop("bom_edit_lines", None)
                st.rerun()
        else:
            st.subheader("Components")
            if b.get("lines"):
                df = pd.DataFrame([{
                    "Item Code": ln.get("raw_product_code"),
                    "Item Name": ln.get("raw_product_name"),
                    "Type": (ln.get("raw_product_type") or "").title(),
                    "Unit": ln.get("unit") or "—",
                    "Qty": float(ln.get("quantity") or 0),
                    "Wastage %": float(ln.get("wastage_pct") or 0),
                    "Rate": float(ln.get("standard_cost") or 0),
                    "Amount": float(ln.get("line_cost") or 0),
                } for ln in b["lines"]])
                render_dataframe_html_table(df)
            else:
                st.info("No component lines.")
            st.metric("Standard Cost", _fmt(b.get("standard_cost")))


def page_production_orders():
    peek = st.session_state.get("prod_ord_tab") or "Register"
    std_page_header(
        "Production Orders",
        status="register" if peek == "Register" else None,
        status_kind="shell" if peek == "Register" else "invoice",
    )
    tab = sticky_page_tabs(
        ["Register", "New Order", "Edit Draft", "Issue / Complete"],
        "prod_ord_tab",
    )

    approved_boms = [b for b in db.get_bom_list() if b.get("status") == "approved"]
    bom_opts = {
        f"{b['document_no']} — {b['finished_product_name']} ({_composition_label(b.get('composition_type'))})": b
        for b in approved_boms
    }
    machines = db.get_machines() if hasattr(db, "get_machines") else []
    mach_opts = {f"{m.get('code','')} — {m.get('name','')} ({m.get('production_line','')})": m["id"] for m in machines}
    wh_opts = {f"{w['code']} - {w['name']}": w["id"] for w in db.get_warehouses()}

    if tab == "Register":
        rows = db.get_production_orders()
        if rows:
            _render_production_order_table(rows)
            draft_rows = _draft_production_orders(rows)
            del_rows = _deletable_production_orders(rows)
            if del_rows:
                st.divider()
                st.subheader("Delete production order")
                st.caption(
                    "Deletes **draft**, **issued**, or **completed** orders. "
                    "Issued materials and finished goods are restored to stock; GL entries are reversed. "
                    "If FG was already sold, tick force or enable negative stock."
                )
                del_opts = {
                    (
                        f"{r['document_no']} — {r.get('product_name')} "
                        f"| Batch {r.get('batch_no') or '—'} | {r.get('order_date') or '—'} "
                        f"({r.get('status')})"
                    ): r
                    for r in del_rows
                }
                del_lbl = st.selectbox("Select order to delete", list(del_opts.keys()), key="prod_del_sel")
                del_po = del_opts[del_lbl]
                del_reason = st.text_input("Reason", value="User delete", key="prod_del_reason")
                force_del = st.checkbox(
                    "Force delete if FG already used (may go negative)",
                    value=False,
                    key="prod_del_force",
                )
                if st.button("Delete Production Order", type="secondary", key="prod_del_btn"):
                    try:
                        db.delete_production_order(
                            del_po["id"], uid(), reason=del_reason, allow_force=force_del,
                        )
                        ff.action_done(f"Deleted **{del_po['document_no']}**.")
                    except Exception as e:
                        st.error(str(e))
            elif draft_rows:
                pass
        else:
            st.info("No production orders.")

    elif tab == "New Order":
        if not bom_opts:
            st.warning("Approve at least one composition (BOM) before creating production orders.")
        else:
            with st.form("prod_new"):
                bl = st.selectbox("Approved Composition *", list(bom_opts.keys()))
                b = bom_opts[bl]
                st.caption(
                    f"Type: **{_composition_label(b.get('composition_type'))}** | "
                    f"Std output: **{b.get('standard_output_qty')}** | "
                    f"Material cost: **{_fmt(b.get('standard_cost'))}**"
                )
                c1, c2, c3 = st.columns(3)
                pq = c1.number_input("Planned Qty *", min_value=0.001, value=float(b.get("standard_output_qty") or 1))
                od = c2.date_input("Production Date", value=date.today())
                batch = c3.text_input("Batch No", value=db.peek_document("BAT"))
                wh_lbl = st.selectbox("Warehouse", list(wh_opts.keys()) if wh_opts else ["—"])
                mach_lbl = st.selectbox("Machine / Line", ["— None —"] + list(mach_opts.keys()))
                st.markdown("**Conversion Costs (optional)**")
                cc1, cc2, cc3, cc4 = st.columns(4)
                with cc1:
                    labour = money_input("Labour", value=0.0, min_value=0.0, key="po_new_lab")
                with cc2:
                    utility = money_input("Utility / Power", value=0.0, min_value=0.0, key="po_new_ut")
                with cc3:
                    packing = money_input("Packing", value=0.0, min_value=0.0, key="po_new_pk")
                with cc4:
                    overhead = money_input("Overhead", value=0.0, min_value=0.0, key="po_new_oh")
                notes = st.text_input("Notes")
                if st.form_submit_button("Create Production Order", type="primary"):
                    reqs = db.calc_bom_requirements(b["id"], pq)
                    if reqs:
                        st.session_state["prod_preview_reqs"] = reqs
                    db.save_production_order({
                        "order_date": str(od),
                        "bom_id": b["id"],
                        "finished_product_id": b["finished_product_id"],
                        "planned_qty": pq,
                        "batch_no": batch,
                        "warehouse_id": wh_opts.get(wh_lbl) if wh_opts else None,
                        "machine_id": mach_opts.get(mach_lbl) if mach_lbl != "— None —" else None,
                        "labour_cost": labour,
                        "utility_cost": utility,
                        "packing_cost": packing,
                        "overhead_cost": overhead,
                        "notes": notes,
                    }, uid())
                    ff.finish_new_entry(also=["prod_preview_reqs"], message="Production order created.")
            if st.session_state.get("prod_preview_reqs"):
                st.subheader("Estimated Material Requirements")
                render_dataframe_html_table(pd.DataFrame(st.session_state["prod_preview_reqs"]))

    elif tab == "Edit Draft":
        rows = db.get_production_orders()
        for r in rows:
            if (r.get("status") or "").lower() == "issued" and "QC/completion rolled back" in (r.get("notes") or ""):
                try:
                    db.reopen_rolled_back_production_to_draft(r["id"], uid())
                except Exception:
                    pass
        rows = db.get_production_orders()
        draft_rows = _draft_production_orders(rows)
        if not bom_opts:
            st.warning("Approve at least one composition (BOM) first.")
        elif not draft_rows:
            st.info("No draft production orders to edit.")
        else:
            st.caption("Edit **draft** orders only — not issued or completed.")
            edit_opts = {
                f"{r['document_no']} — {r.get('product_name')} (batch {r.get('batch_no')})": r
                for r in draft_rows
            }
            edit_lbl = st.selectbox("Select draft order", list(edit_opts.keys()), key="prod_edit_sel")
            po_row = edit_opts[edit_lbl]
            po = db.get_production_order(po_row["id"]) or po_row
            payload = _production_order_edit_form(po, bom_opts, wh_opts, mach_opts, "prod_edit")
            if payload:
                try:
                    db.update_production_order(po["id"], payload, uid())
                    reqs = db.calc_bom_requirements(payload["bom_id"], payload["planned_qty"])
                    if reqs:
                        st.session_state["prod_edit_preview"] = reqs
                    else:
                        st.session_state.pop("prod_edit_preview", None)
                    ff.action_done(f"Updated **{po['document_no']}** — form refreshed from database.")
                except Exception as e:
                    st.error(str(e))
            if st.session_state.get("prod_edit_preview"):
                st.subheader("Updated material requirements (estimate)")
                render_dataframe_html_table(pd.DataFrame(st.session_state["prod_edit_preview"]))

    elif tab == "Issue / Complete":
        rows = db.get_production_orders()
        if not rows:
            st.info("No orders.")
            return
        active = [r for r in rows if r.get("status") in ("draft", "issued", "completed")]
        if not active:
            st.info("No production orders.")
            return
        sel = st.selectbox(
            "Production Order",
            [f"{r['document_no']} — {r.get('product_name')} [{r.get('status')}]" for r in active],
            key="prod_proc_sel",
        )
        po = next(r for r in active if r["document_no"] in sel)
        bom = db.get_bom(po["bom_id"])
        if bom:
            st.caption(f"Composition: **{bom.get('document_no')}** | {_composition_label(bom.get('composition_type'))}")
        reqs = db.calc_bom_requirements(po["bom_id"], po["planned_qty"])
        if reqs:
            st.subheader("Material Requirements (incl. wastage)")
            render_dataframe_html_table(pd.DataFrame([{
                "Material": r.get("product_name"),
                "Required Qty": float(r.get("quantity") or 0),
                "Weight (kg)": float(r.get("weight") or 0),
            } for r in reqs]))
        st.markdown("---")
        if po["status"] == "draft":
            st.info("To change planned qty, BOM, batch, or costs before issuing — use **Edit Draft** tab.")
            if st.button("Delete Draft Order", type="secondary", key="prod_proc_del"):
                try:
                    db.delete_production_order(po["id"], uid())
                    ff.action_done(f"Deleted **{po['document_no']}**.")
                except Exception as e:
                    st.error(str(e))
            st.divider()
            shortages = db.production_material_shortages(po["id"])
            allow_neg = db.get_setting("allow_negative_stock") == "1"
            confirm_key = f"prod_issue_confirm_{po['id']}"
            if shortages:
                st.warning(
                    "**Insufficient stock** for one or more materials. "
                    "You can still issue after confirming — warehouse qty may go negative."
                )
                render_dataframe_html_table(pd.DataFrame([{
                    "Material": s["product_name"],
                    "Required": float(s["required"]),
                    "Available": float(s["available"]),
                    "Short": float(s["shortfall"]),
                } for s in shortages]))
            if shortages and not allow_neg:
                if st.session_state.get(confirm_key):
                    c_yes, c_no = st.columns(2)
                    if c_yes.button("Confirm — issue with insufficient stock", type="primary", key="prod_issue_yes"):
                        try:
                            db.issue_production_materials(po["id"], uid(), allow_insufficient=True)
                            st.session_state.pop(confirm_key, None)
                            ff.action_done("Materials issued (including short items) → WIP.")
                        except Exception as e:
                            st.error(str(e))
                    if c_no.button("Cancel", key="prod_issue_no"):
                        st.session_state.pop(confirm_key, None)
                        st.rerun()
                elif st.button("Issue Materials to Production", type="primary", key="prod_issue"):
                    st.session_state[confirm_key] = True
                    st.rerun()
            else:
                if st.button("Issue Materials to Production", type="primary", key="prod_issue"):
                    try:
                        db.issue_production_materials(po["id"], uid())
                        ff.action_done("Materials issued from stock → WIP.")
                    except Exception as e:
                        st.error(str(e))
        elif po["status"] == "issued":
            st.subheader("Complete Batch")
            fid = "prod_complete"
            wk = lambda n: ff.widget_key(fid, n)
            c1, c2, c3 = st.columns(3)
            aq = c1.number_input("Actual Output Qty", min_value=0.0, value=float(po["planned_qty"]), key=wk("aq"))
            wq = c2.number_input("Process Wastage Qty", min_value=0.0, value=0.0, key=wk("wq"))
            qc = c3.selectbox("QC Status", ["Pending", "Passed", "Failed"], index=1, key=wk("qc"))
            if st.button("Complete Production & Receive FG", type="primary", key="prod_complete"):
                db.complete_production(po["id"], aq, wq, qc, uid())
                ff.finish_post_new_form(fid, "Finished goods received into stock.")
        elif po["status"] == "completed":
            detail = db.get_production_order(po["id"]) or po
            st.success(
                f"Order **{detail['document_no']}** completed — QC **{detail.get('qc_status', '—')}**, "
                f"output **{float(detail.get('actual_qty') or 0):,.4f}**, "
                f"wastage **{float(detail.get('wastage_qty') or 0):,.4f}**."
            )
            if detail.get("issues"):
                st.subheader("Materials Issued")
                render_dataframe_html_table(pd.DataFrame(detail["issues"]))
            if detail.get("receipts"):
                st.subheader("Finished Goods Receipts")
                render_dataframe_html_table(pd.DataFrame(detail["receipts"]))
            st.divider()
            st.subheader("Rollback QC / completion")
            st.caption(
                "Reverses FG receipt, un-issues materials to stock, and sets order back to **draft**. "
                "Use **Edit Draft** to fix BOM/qty, then **Issue / Complete** again."
            )
            rb_reason = st.text_input(
                "Reason for rollback *",
                key=f"prod_rb_reason_{po['id']}",
                placeholder="e.g. wrong QC qty, failed batch to rework",
            )
            rb_force = st.checkbox(
                "Confirm rollback even if batch FG was partly used (warehouse qty may go negative)",
                key=f"prod_rb_force_{po['id']}",
            )
            if st.button("Rollback & Reopen for Correction", type="secondary", key=f"prod_rb_{po['id']}"):
                try:
                    db.rollback_production_completion(
                        po["id"], uid(), rb_reason, allow_force=rb_force,
                    )
                    ff.action_done(f"**{detail['document_no']}** is **draft** again — open **Edit Draft** to change, "
                        f"then **Issue / Complete** to re-issue and complete.")
                except Exception as e:
                    st.error(str(e))
        else:
            st.info(f"Order **{po['document_no']}** status: **{po.get('status')}**.")
            detail = db.get_production_order(po["id"])
            if detail and detail.get("issues"):
                st.subheader("Materials Issued")
                render_dataframe_html_table(pd.DataFrame(detail["issues"]))


# Legacy aliases
page_bom = page_bom_composition
page_production = page_production_orders


def page_daily_production():
    """One-screen daily production: BOM → issue RM → receive FG (stock update)."""
    peek = st.session_state.get("daily_prod_tab") or "Post Production"
    std_page_header(
        "Daily Production",
        status="register" if peek == "Today / Recent" else None,
        status_kind="shell" if peek == "Today / Recent" else "invoice",
    )
    approved_boms = [b for b in db.get_bom_list() if b.get("status") == "approved"]
    if not approved_boms:
        st.warning("Approve at least one BOM / composition first (Production → BOM).")
        return

    bom_opts = {
        f"{b['document_no']} — {b.get('finished_product_name')} (std {b.get('standard_output_qty')})": b
        for b in approved_boms
    }
    wh_opts = {f"{w['code']} — {w['name']}": w["id"] for w in db.get_warehouses()}
    tab = sticky_page_tabs(["Post Production", "Today / Recent"], "daily_prod_tab")

    if tab == "Post Production":
        with st.form("daily_prod_form"):
            bl = st.selectbox("Approved BOM *", list(bom_opts.keys()))
            b = bom_opts[bl]
            c1, c2, c3 = st.columns(3)
            prod_date = c1.date_input("Production Date", value=date.today())
            qty = c2.number_input(
                "Actual output qty *",
                min_value=0.001,
                value=float(b.get("standard_output_qty") or 1),
            )
            wastage = c3.number_input("Wastage qty", min_value=0.0, value=0.0)
            wh_lbl = st.selectbox("Warehouse", list(wh_opts.keys()) if wh_opts else ["—"])
            batch = st.text_input("Batch No", value=db.peek_document("BAT"))
            notes = st.text_input("Notes", value="Daily production")
            allow_neg = st.checkbox("Allow post if material short (may go negative)", value=False)
            allow_dup = st.checkbox(
                "Allow duplicate (same BOM + qty on this date)",
                value=False,
                help="Required if this BOM and output qty were already posted for the production date.",
            )
            # Material preview
            try:
                reqs = db.calc_bom_requirements(b["id"], qty)
            except Exception:
                reqs = []
            if reqs:
                st.caption("Materials to issue (from BOM)")
                render_dataframe_html_table(pd.DataFrame([{
                    "Code": r.get("product_code") or "—",
                    "Material": r.get("product_name"),
                    "Qty": float(r.get("quantity") or 0),
                } for r in reqs]))
            submitted = st.form_submit_button("Post to Stock", type="primary")
        if submitted:
            try:
                dups = db.find_same_day_production_duplicates(b["id"], str(prod_date), qty)
                if dups and not allow_dup:
                    docs = ", ".join(
                        f"**{d.get('document_no')}** ({d.get('batch_no') or '—'})" for d in dups[:5]
                    )
                    st.warning(
                        f"Same BOM and qty already posted on **{prod_date}**: {docs}. "
                        "Tick **Allow duplicate (same BOM + qty on this date)** and post again only if intentional."
                    )
                else:
                    po_id = db.post_daily_production(
                        {
                            "bom_id": b["id"],
                            "finished_product_id": b["finished_product_id"],
                            "production_date": str(prod_date),
                            "planned_qty": qty,
                            "actual_qty": qty,
                            "wastage_qty": wastage,
                            "warehouse_id": wh_opts.get(wh_lbl) if wh_opts else None,
                            "batch_no": batch,
                            "notes": notes,
                            "qc_status": "Passed",
                        },
                        uid(),
                        allow_insufficient=allow_neg,
                        allow_duplicate=allow_dup,
                    )
                    po = db.get_production_order(po_id)
                    ff.action_done(f"Posted **{po.get('document_no') if po else po_id}** — "
                        f"RM issued and FG **{qty}** received into stock.")
            except Exception as e:
                st.error(str(e).replace("**", ""))

    elif tab == "Today / Recent":
        rows = db.get_production_orders() or []
        today = str(date.today())
        recent = [r for r in rows if (r.get("order_date") or "") >= today[:8]][:50]
        if not recent:
            recent = rows[:30]
        if recent:
            _render_production_order_table(recent)
            del_rows = _deletable_production_orders(recent)
            if del_rows:
                st.divider()
                st.subheader("Delete production")
                st.caption(
                    "Removes the order and reverses warehouse stock + inventory GL "
                    "(Raw/Pack → WIP → Finished Goods)."
                )
                del_opts = {
                    (
                        f"{r['document_no']} — {r.get('product_name')} "
                        f"| Batch {r.get('batch_no') or '—'} | {r.get('order_date') or '—'} "
                        f"({r.get('status')})"
                    ): r
                    for r in del_rows
                }
                d1, d2 = st.columns([3, 1])
                with d1:
                    del_lbl = st.selectbox(
                        "Select production to delete",
                        list(del_opts.keys()),
                        key="daily_prod_del_sel",
                    )
                with d2:
                    force_del = st.checkbox("Force", value=False, key="daily_prod_del_force")
                del_reason = st.text_input("Reason", value="Daily production delete", key="daily_prod_del_reason")
                if st.button("Delete selected production", type="secondary", key="daily_prod_del_btn"):
                    try:
                        po = del_opts[del_lbl]
                        db.delete_production_order(
                            po["id"], uid(), reason=del_reason, allow_force=force_del,
                        )
                        ff.action_done(f"Deleted **{po['document_no']}** — stock and GL reversed.")
                    except Exception as e:
                        st.error(str(e).replace("**", ""))
        else:
            st.info("No production orders yet.")
