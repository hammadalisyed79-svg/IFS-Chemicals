"""Internal admin — distributor portal orders and enable portal access."""

from __future__ import annotations

import secrets
import string

import streamlit as st
from erp_ui import form_flow as ff
import pandas as pd

from erp_core import portal_service as ps
from application.data_gateway import user_can
from application import data_gateway as db
from db_v15 import PORTAL_ORDER_STATUSES
from erp_ui import helpers as hlp


def _temp_password(length: int = 10) -> str:
    alphabet = string.ascii_letters + string.digits
    # Ensure letter + digit for validate_password_strength
    pwd = [
        secrets.choice(string.ascii_letters),
        secrets.choice(string.digits),
    ]
    pwd += [secrets.choice(alphabet) for _ in range(max(0, length - 2))]
    secrets.SystemRandom().shuffle(pwd)
    return "".join(pwd)


def page_distributor_orders():
    user = st.session_state.get("user") or {}
    if not user_can(user, "Portal", "view") and not user_can(user, "Sales", "view") and user.get("role") != "admin":
        st.error("Access denied.")
        return

    hlp.std_page_header("Distributor Orders", status="register", status_kind="shell")

    tab = hlp.sticky_page_tabs(
        ["Existing Portals", "Portal Orders", "Payment Proofs", "Enable Portal"],
        "dist_orders_tab",
    )
    if tab == "Existing Portals":
        _tab_existing_portals(user)
    elif tab == "Portal Orders":
        _tab_orders(user)
    elif tab == "Payment Proofs":
        _tab_payment_proofs(user)
    elif tab == "Enable Portal":
        _tab_enable_portal(user)


def _tab_payment_proofs(user: dict):
    st.subheader("Distributor payment proofs")
    st.caption(
        "When a distributor uploads a bank slip on the portal, it appears here. "
        "Approve or reject after verifying the slip — the distributor is notified. "
        "Post the receipt in Finance (Bank Receipt) separately if not already done."
    )
    status = st.selectbox(
        "Status",
        ["pending", "All", "approved", "rejected"],
        key="dist_pp_status",
    )
    rows = ps.list_all_payment_proofs(status=None if status == "All" else status)
    if not rows:
        st.info("No payment proofs in this filter.")
        return

    df = pd.DataFrame(rows)
    show = [
        c for c in (
            "id", "customer_code", "customer_name", "proof_date", "amount",
            "reference_no", "bank_name", "status", "uploaded_by", "created_at",
        ) if c in df.columns
    ]
    hlp.render_dataframe_html_table(df[show])

    labels = [
        f"#{r['id']} · {r.get('customer_code')} · Rs. {float(r.get('amount') or 0):,.2f} · {r.get('status')}"
        for r in rows
    ]
    sel = st.selectbox("Review proof", labels, key="dist_pp_sel")
    row = rows[labels.index(sel)]
    detail = ps.get_payment_proof(row["id"]) or row

    st.markdown(
        f"**{detail.get('customer_code')} — {detail.get('customer_name')}**  \n"
        f"Amount **Rs. {float(detail.get('amount') or 0):,.2f}** · "
        f"Date {detail.get('proof_date')} · Status **{detail.get('status')}**  \n"
        f"Bank: {detail.get('bank_name') or '—'} · Ref: {detail.get('reference_no') or '—'}  \n"
        f"{detail.get('notes') or ''}"
    )

    path = (detail.get("file_path") or "").strip()
    if path:
        from pathlib import Path
        p = Path(path)
        if p.is_file():
            data = p.read_bytes()
            ext = p.suffix.lower()
            if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
                st.image(data, caption=p.name, use_container_width=True)
            else:
                st.download_button(
                    "Download slip",
                    data=data,
                    file_name=p.name,
                    mime="application/pdf" if ext == ".pdf" else "application/octet-stream",
                    key=f"dist_pp_dl_{detail['id']}",
                )
            if ext == ".pdf":
                st.caption(f"PDF slip: {p.name}")
        else:
            st.warning("Slip file missing on server disk.")
    else:
        st.info("No slip file was attached with this submission.")

    if (detail.get("status") or "").lower() == "pending":
        reason = st.text_input("Rejection reason (if rejecting)", key=f"dist_pp_reason_{detail['id']}")
        c1, c2 = st.columns(2)
        if c1.button("Approve proof", type="primary", key=f"dist_pp_ok_{detail['id']}", use_container_width=True):
            try:
                ps.review_payment_proof(detail["id"], "approved", user_id=user.get("id"))
                ff.action_done("Approved — distributor notified. Post bank receipt in Finance if needed.")
            except Exception as e:
                st.error(str(e))
        if c2.button("Reject proof", key=f"dist_pp_no_{detail['id']}", use_container_width=True):
            try:
                ps.review_payment_proof(
                    detail["id"], "rejected", user_id=user.get("id"), reason=reason,
                )
                ff.action_done("Rejected — distributor notified.")
            except Exception as e:
                st.error(str(e))
    else:
        st.caption(
            f"Reviewed at {detail.get('reviewed_at') or '—'} "
            f"(user {detail.get('reviewed_by') or '—'})"
        )


def _tab_existing_portals(user: dict):
    st.subheader("Existing portal accounts")
    st.caption("Distributors already set up with a portal login.")
    rows = ps.list_existing_portals()
    if not rows:
        st.info("No portal accounts yet. Use Enable Portal to create one.")
        return

    q = st.text_input("Search", placeholder="Code, name, or username", key="exist_portal_q")
    if q and q.strip():
        needle = q.strip().lower()
        rows = [
            r for r in rows
            if needle in str(r.get("customer_code") or "").lower()
            or needle in str(r.get("customer_name") or "").lower()
            or needle in str(r.get("username") or "").lower()
        ]

    df = pd.DataFrame(rows)
    show = [
        c for c in (
            "customer_code", "customer_name", "username", "full_name",
            "is_active", "portal_enabled", "credit_limit",
            "price_list_code", "catalog_items", "must_change_password", "last_login_at",
        ) if c in df.columns
    ]
    hlp.render_dataframe_html_table(df[show])
    st.caption(f"{len(rows)} portal account(s)")

    labels = [
        f"{r.get('customer_code')} — {r.get('customer_name') or '—'} — "
        f"{r.get('username')} ({'active' if r.get('is_active') else 'inactive'})"
        for r in rows
    ]
    sel = st.selectbox("Manage account", ["—"] + labels, key="exist_portal_sel")
    if sel == "—":
        return
    row = rows[labels.index(sel)]
    st.markdown(
        f"**{row.get('customer_code')} — {row.get('customer_name')}**  \n"
        f"Username: `{row.get('username')}` · User id {row.get('user_id')} · "
        f"Product list items: {row.get('catalog_items') or 0}"
    )

    # Profile fields the distributor saves on portal → Profile
    prof = ps.get_customer_portal_profile(int(row["customer_id"])) or row
    st.markdown("#### Profile from portal (customer updates)")
    st.caption(
        "When the distributor saves **Profile** on the portal, these fields update on the "
        "customer master. You can also edit them under **Masters → Customers → Edit**."
    )
    p1, p2 = st.columns(2)
    with p1:
        st.write(f"**Contact:** {prof.get('contact_person') or '—'}")
        st.write(f"**Main phone:** {prof.get('phone') or '—'}")
        st.write(f"**Email:** {prof.get('email') or '—'}")
        st.write(f"**City / Province:** {prof.get('city') or '—'} / {prof.get('province') or '—'}")
    with p2:
        st.write(f"**Dispatch phone:** {prof.get('dispatch_phone') or '—'}")
        st.write(f"**Accounts phone:** {prof.get('accounts_phone') or '—'}")
        st.write(f"**Owner phone:** {prof.get('owner_phone') or '—'}")
        st.write(f"**NTN / STRN:** {prof.get('ntn') or '—'} / {prof.get('strn') or '—'}")
    if prof.get("address"):
        st.write(f"**Address:** {prof.get('address')}")
    touched = prof.get("customer_modified_at") or prof.get("profile_modified_at")
    if touched:
        st.caption(f"Last customer/profile update: {touched}")

    new_credit = st.number_input(
        "Credit limit",
        value=float(row.get("credit_limit") or 0),
        min_value=0.0,
        key=f"exist_portal_credit_{row['user_id']}",
    )
    if st.button("Update credit limit only", type="primary", key="exist_portal_credit_save"):
        try:
            ps.update_distributor_portal_settings(
                int(row["customer_id"]),
                credit_limit=float(new_credit),
                modified_by=user.get("id"),
            )
            st.success(f"Credit limit updated to Rs. {float(new_credit):,.2f}. Password unchanged.")
            ff.action_done("Credit limit updated")
        except Exception as e:
            st.error(str(e))

    c1, c2, c3 = st.columns(3)
    if c1.button("Disable login", key="exist_portal_off", use_container_width=True):
        ps.set_portal_user_active(row["user_id"], False, modified_by=user.get("id"))
        ff.action_done("Portal login disabled")
    if c2.button("Enable login", key="exist_portal_on", use_container_width=True):
        ps.set_portal_user_active(row["user_id"], True, modified_by=user.get("id"))
        ff.action_done("Portal login enabled")
    if c3.button("Open Enable Portal for reset", key="exist_portal_goto", use_container_width=True):
        st.info("Switch to the **Enable Portal** tab and select this customer to reset the password.")


def _tab_orders(user: dict):
    # Highlight newly submitted distributor orders
    try:
        from erp_core import notifications as ntf
        unread = ntf.get_notifications_for_user(user.get("id"), unread_only=True, limit=20)
        new_orders = [n for n in unread if (n.get("category") or "") == "portal_order"]
        deleted = [n for n in unread if (n.get("category") or "") == "order_deleted"]
        if new_orders:
            st.success(
                f"🔔 {len(new_orders)} new distributor order notification(s) — "
                f"latest: {new_orders[0].get('title')}"
            )
        if deleted:
            st.warning(
                f"🗑️ {len(deleted)} order deletion(s) — "
                f"latest: {deleted[0].get('title')}"
            )
    except Exception:
        pass

    status = st.selectbox("Status filter", ["All"] + list(PORTAL_ORDER_STATUSES), key="dist_ord_status")
    rows = ps.list_all_portal_orders(status=None if status == "All" else status)
    if rows:
        odf = pd.DataFrame(rows)
        show = [c for c in (
            "order_no", "customer_name", "order_date", "delivery_date", "dispatch_town",
            "status", "total", "sales_order_id",
        ) if c in odf.columns]
        hlp.render_dataframe_html_table(odf[show])
    else:
        st.info("No portal orders.")

    sel = st.selectbox("Manage order", ["—"] + [r["order_no"] for r in rows], key="dist_ord_sel") if rows else "—"
    if sel != "—":
        order = next(r for r in rows if r["order_no"] == sel)
        detail = ps.get_portal_order_internal(order["id"])
        if detail:
            st.subheader(detail["order_no"])
            st.write(
                f"**Customer:** {detail.get('customer_code')} — {detail.get('customer_name')}  \n"
                f"**Status:** {detail.get('status')} · **Total:** Rs. {float(detail.get('total') or 0):,.2f}  \n"
                f"**Order date:** {detail.get('order_date') or '—'} · "
                f"**Delivery:** {detail.get('delivery_date') or '—'}  \n"
                f"**Dispatch town:** {detail.get('dispatch_town') or '—'}"
            )
            if detail.get("rejection_reason"):
                st.warning(f"Rejection reason: {detail['rejection_reason']}")
            items = detail.get("items") or []
            if items:
                idf = pd.DataFrame(items)
                show = [
                    c for c in (
                        "product_code", "product_name", "quantity",
                        "rate", "discount_pct", "amount",
                    ) if c in idf.columns
                ]
                hlp.render_dataframe_html_table(idf[show] if show else idf)

            cur = (detail.get("status") or "").strip()
            can_decide = cur in ("Submitted", "Under Review", "Draft", "Approved")
            st.markdown("### Approve or reject")
            st.caption("Reject notifies the distributor in My Orders / Notifications with your reason.")
            reject_reason = st.text_area(
                "Rejection reason (required to reject)",
                key=f"dist_ord_rej_reason_{detail['id']}",
                placeholder="e.g. Credit limit / stock not available / wrong rates…",
                height=80,
            )
            c1, c2, c3 = st.columns(3)
            if c1.button(
                "Approve order",
                type="primary",
                key=f"dist_ord_approve_{detail['id']}",
                use_container_width=True,
                disabled=not can_decide or cur == "Approved",
            ):
                try:
                    ps.update_portal_status(detail["id"], "Approved", user_id=user.get("id"))
                    ff.action_done(f"{detail['order_no']} approved — distributor notified.")
                except Exception as e:
                    st.error(str(e))
            if c2.button(
                "Reject order",
                key=f"dist_ord_reject_{detail['id']}",
                use_container_width=True,
                disabled=cur in ("Rejected", "Delivered", "Invoiced", "Cancelled"),
            ):
                try:
                    ps.reject_portal_order(
                        detail["id"], reject_reason, user_id=user.get("id"),
                    )
                    ff.action_done(
                        f"{detail['order_no']} rejected — distributor notified with your reason."
                    )
                except Exception as e:
                    st.error(str(e))
            if c3.button(
                "Mark under review",
                key=f"dist_ord_review_{detail['id']}",
                use_container_width=True,
                disabled=cur == "Under Review",
            ):
                try:
                    ps.update_portal_status(detail["id"], "Under Review", user_id=user.get("id"))
                    ff.action_done(f"{detail['order_no']} marked under review.")
                except Exception as e:
                    st.error(str(e))

            with st.expander("Other status update"):
                other_statuses = [
                    s for s in PORTAL_ORDER_STATUSES
                    if s not in ("Rejected",)  # use Reject button above
                ]
                new_st = st.selectbox(
                    "Update status",
                    other_statuses,
                    index=other_statuses.index(cur) if cur in other_statuses else 0,
                    key=f"dist_ord_new_st_{detail['id']}",
                )
                if st.button("Apply status", key=f"dist_ord_upd_{detail['id']}"):
                    try:
                        ps.update_portal_status(
                            detail["id"], new_st, user_id=user.get("id"),
                        )
                        ff.action_done("Status updated")
                    except Exception as e:
                        st.error(str(e))


def _tab_enable_portal(user: dict):
    st.subheader("Enable distributor portal")
    st.caption(
        "Marks the customer as a distributor, assigns a price list, and creates a portal login. "
        "Share the temporary password once — the distributor must change it on first login."
    )
    customers = db.get_customers(active_only=True) or []
    if not customers:
        st.info("Add customers first.")
        return
    cmap = {f"{c['code']} — {c['name']}": c for c in customers}
    cust_labels, blank = hlp.options_with_blank(cmap.keys())
    cust_lbl = st.selectbox("Customer", cust_labels, key="en_portal_cust")
    if not hlp.require_selected("customer", cust_lbl, blank, soft=True):
        return
    cust = cmap[cust_lbl]

    with db.get_connection() as conn:
        pls = [dict(r) for r in conn.execute(
            "SELECT id, code, name FROM price_lists WHERE is_active=1 ORDER BY code"
        ).fetchall()]
        existing = conn.execute(
            """SELECT id, username, is_active FROM users
               WHERE linked_customer_id=? AND LOWER(COALESCE(user_type,'')) LIKE 'distributor%'
               LIMIT 1""",
            (cust["id"],),
        ).fetchone()

    pl_map = {f"{p['code']} — {p['name']}": p["id"] for p in pls}
    if not pl_map:
        st.warning("Create a price list first (Price Lists).")
        return

    cur_pl = cust.get("assigned_price_list_id")
    default_pl = next((k for k, v in pl_map.items() if v == cur_pl), list(pl_map.keys())[0])
    pl_sel = st.selectbox(
        "Price list",
        list(pl_map.keys()),
        index=list(pl_map.keys()).index(default_pl),
        key="en_portal_pl",
    )
    credit = st.number_input(
        "Credit limit",
        value=float(cust.get("credit_limit") or 0),
        min_value=0.0,
        key="en_portal_credit",
    )
    show_stock = st.checkbox("Show stock in portal", value=False, key="en_portal_stock")

    # Update settings without resetting password
    if existing:
        st.caption("To change credit limit / price list only — use **Save settings** (does not reset password).")
        if st.button("Save settings (credit / price list)", type="primary", key="en_portal_settings_only"):
            try:
                ps.update_distributor_portal_settings(
                    cust["id"],
                    credit_limit=float(credit),
                    price_list_id=pl_map[pl_sel],
                    show_stock=show_stock,
                    modified_by=user.get("id"),
                )
                st.success(
                    f"Settings saved for {cust.get('code')}. "
                    f"Credit limit Rs. {float(credit):,.2f}. Password unchanged."
                )
                ff.action_done("Portal settings updated")
            except Exception as e:
                st.error(str(e))
        st.divider()
        st.caption("Password reset (optional) — only if the distributor forgot their login.")

    suggested = (cust.get("code") or "dist").lower().replace(" ", "")
    if existing:
        st.info(f"Portal user already exists: **{existing[1]}** (id {existing[0]}). **Enable portal access** will reset the password.")
        username = existing[1]
        st.text_input("Username", value=username, disabled=True, key="en_portal_user_ro")
    else:
        username = st.text_input("Portal username", value=suggested, key="en_portal_user")
    full_name = st.text_input(
        "Display name",
        value=cust.get("name") or "",
        key="en_portal_name",
    )
    gen = st.checkbox("Generate temporary password", value=True, key="en_portal_gen")
    if gen:
        if "en_portal_temp_pwd" not in st.session_state:
            st.session_state["en_portal_temp_pwd"] = _temp_password()
        if st.button("Regenerate password", key="en_portal_regen"):
            st.session_state["en_portal_temp_pwd"] = _temp_password()
            st.rerun()
        password = st.session_state["en_portal_temp_pwd"]
        st.code(password, language=None)
    else:
        password = st.text_input("Temporary password", type="password", key="en_portal_pwd")

    if st.button("Enable portal access", type="primary", key="en_portal_go"):
        if not username or not password:
            st.error("Username and password are required.")
            return
        try:
            creds = ps.enable_distributor_portal(
                cust["id"],
                username=username.strip(),
                password=password,
                full_name=full_name.strip() or None,
                price_list_id=pl_map[pl_sel],
                credit_limit=float(credit),
                show_stock=show_stock,
                created_by=user.get("id"),
            )
            st.session_state["en_portal_last_creds"] = creds
            st.session_state.pop("en_portal_temp_pwd", None)
            st.success("Portal enabled. Share these credentials once with the distributor.")
        except Exception as e:
            st.error(str(e))
            return

    creds = st.session_state.get("en_portal_last_creds")
    if creds and creds.get("customer_id") == cust["id"]:
        st.warning("Copy now — password is not shown again after you leave this page.")
        st.markdown(
            f"""
| | |
|---|---|
| **Customer** | {creds.get('customer_code')} — {creds.get('customer_name')} |
| **URL** | https://erp.ifschemicals.com |
| **Username** | `{creds.get('username')}` |
| **Temp password** | `{creds.get('password')}` |
| **Must change password** | Yes |
"""
        )
