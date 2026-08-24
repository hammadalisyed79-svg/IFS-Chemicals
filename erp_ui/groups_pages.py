"""IFS-style account & item groups — header record + membership grid."""

import pandas as pd
import streamlit as st
from erp_ui import form_flow as ff
from application import data_gateway as db
from db_groups import (
    CODE_PREFIX,
    ENTITY_LABELS,
    MEMBERS_GRID_TITLE,
    assign_entities_to_group,
    get_entities_for_group_add,
    get_group_members,
    get_master_group,
    get_master_groups,
    remove_entities_from_group,
    resolve_entity_ids_by_codes,
)
from erp_ui.helpers import uid, std_page_header, export_buttons, sticky_page_tabs, render_dataframe_html_table


def _group_picker_options(entity_type, groups):
    opts = {"— New group —": None}
    for g in groups:
        opts[f"{g['code']} — {g['name']}"] = g["id"]
    return opts


def _save_group_header(entity_type, group_id, code, name, active, notes, sort_order):
    payload = {
        "entity_type": entity_type,
        "code": code.strip(),
        "name": name.strip(),
        "parent_id": None,
        "notes": notes.strip() or None,
        "sort_order": sort_order,
        "is_active": int(active),
    }
    if group_id:
        db.update_master_group(group_id, payload, uid())
        return group_id
    return db.add_master_group(payload, uid())


def _maintain_group_workspace(entity_type):
    """Finance Manager pattern: group code/name + grid of members + add/remove."""
    label = ENTITY_LABELS[entity_type]
    grid_title = MEMBERS_GRID_TITLE[entity_type]
    sk = f"grp_{entity_type}"

    groups = db.get_master_groups(entity_type, active_only=False)
    picker = _group_picker_options(entity_type, groups)
    labels = list(picker.keys())

    if f"{sk}_id" not in st.session_state:
        st.session_state[f"{sk}_id"] = groups[0]["id"] if groups else None

    top = st.columns([3, 1, 1])
    prev_id = st.session_state.get(f"{sk}_id")
    default_lbl = next((k for k, v in picker.items() if v == prev_id), labels[0])
    sel_lbl = top[0].selectbox(
        "Group Code",
        labels,
        index=labels.index(default_lbl) if default_lbl in labels else 0,
        key=f"{sk}_pick",
    )
    st.session_state[f"{sk}_id"] = picker[sel_lbl]

    if top[1].button("New", key=f"{sk}_new"):
        st.session_state[f"{sk}_id"] = None
        st.rerun()
    if top[2].button("Refresh", key=f"{sk}_ref"):
        st.rerun()

    group_id = st.session_state[f"{sk}_id"]
    group = db.get_master_group(group_id) if group_id else None
    prefix = CODE_PREFIX[entity_type]

    hdr1, hdr2, hdr3 = st.columns([2, 3, 1])
    code_val = group["code"] if group else db.next_code(prefix, "master_groups")
    with hdr1:
        code = st.text_input("Group Code", value=code_val, key=f"{sk}_code")
    with hdr2:
        name = st.text_input("Group Name *", value=(group["name"] if group else ""), key=f"{sk}_name")
    with hdr3:
        active = st.checkbox("Active", value=bool(group.get("is_active", 1)) if group else True, key=f"{sk}_act")

    notes = st.text_input("Notes (optional)", value=(group.get("notes") or "") if group else "", key=f"{sk}_notes")
    sort_order = st.number_input(
        "Sort order", min_value=0,
        value=int(group.get("sort_order") or 0) if group else 0,
        key=f"{sk}_sort",
    )

    act_save, act_del, _ = st.columns([1, 1, 4])
    if act_save.button("Save Group", type="primary", key=f"{sk}_save"):
        if not name.strip():
            st.error("Group name is required.")
        else:
            try:
                new_id = _save_group_header(
                    entity_type, group_id, code, name, active, notes, sort_order,
                )
                st.session_state[f"{sk}_id"] = new_id
                ff.action_done("Group saved.")
            except Exception as e:
                st.error(str(e))

    if group_id and act_del.button("Delete Group", key=f"{sk}_del"):
        try:
            db.delete_master_group(group_id)
            st.session_state[f"{sk}_id"] = None
            ff.action_done("Group deleted.")
        except Exception as e:
            st.error(str(e))

    if not group_id:
        st.info(f"Save the group first, then add {label.lower()} records below.")
        return

    st.divider()
    st.markdown(f"**{grid_title}**")
    members = get_group_members(group_id)
    if members:
        if entity_type == "product":
            df = pd.DataFrame(members)
            show = [c for c in ("code", "name", "item_type", "category") if c in df.columns]
            render_dataframe_html_table(
                df[show].rename(columns={
                    "code": "Item Code", "name": "Item Name",
                    "item_type": "Item Type", "category": "Category",
                }),
            )
        else:
            render_dataframe_html_table(
                pd.DataFrame(members)[["code", "name"]].rename(
                    columns={"code": "Account Code", "name": "Description"},
                ),
            )
        export_buttons(pd.DataFrame(members), f"group_{group_id}", grid_title)
    else:
        st.caption(f"No {label.lower()}s in this group yet.")

    code_label = "Item Code" if entity_type == "product" else "Account Code"
    add_btn = "Add Items" if entity_type == "product" else "Add Accounts"
    del_btn = "Remove Items" if entity_type == "product" else "Remove Accounts"

    st.markdown("**Add multiple to group**")
    with st.expander("Paste codes (bulk add)", expanded=False):
        st.caption(f"One {code_label.lower()} per line, or separated by commas.")
        pasted = st.text_area(
            f"{code_label}s",
            height=120,
            key=f"{sk}_paste",
            placeholder="100005\n100006\n100007",
        )
        if st.button(f"Add pasted {code_label.lower()}s", key=f"{sk}_paste_btn"):
            raw = []
            for line in (pasted or "").replace(",", "\n").splitlines():
                raw.append(line.strip())
            ids, missing = resolve_entity_ids_by_codes(entity_type, raw)
            if not ids:
                st.warning("No valid codes found.")
            else:
                try:
                    n = assign_entities_to_group(entity_type, ids, group_id, uid())
                    msg = f"Added **{n}** record(s) to the group."
                    if missing:
                        msg += f" Not found: {', '.join(missing[:20])}"
                        if len(missing) > 20:
                            msg += f" … (+{len(missing) - 20} more)"
                    ff.action_done(msg)
                except Exception as e:
                    st.error(str(e))

    search = st.text_input(
        "Search list",
        key=f"{sk}_addq",
        placeholder="Code or name — shows unassigned or members of other groups",
    )
    pool = get_entities_for_group_add(entity_type, group_id, search=search or None)
    id_map = {}
    for r in pool:
        extra = ""
        if r.get("group_id"):
            og = db.get_master_group(r["group_id"])
            if og:
                extra = f" [was: {og['code']}]"
        lbl = f"{r['code']} — {r['name']}{extra}"
        id_map[lbl] = r["id"]

    pick_key = f"{sk}_addsel"
    if st.session_state.pop(f"{sk}_reset_addsel", False):
        st.session_state.pop(pick_key, None)

    if not id_map:
        st.caption("No matching records to add.")
    else:
        st.caption(f"**{len(id_map)}** available — select one or many, then click **{add_btn}**.")
        c_all, c_clr, c_cnt = st.columns([1, 1, 2])
        if c_all.button("Select all in list", key=f"{sk}_selall"):
            st.session_state[pick_key] = list(id_map.keys())
            st.rerun()
        if c_clr.button("Clear selection", key=f"{sk}_selclr"):
            st.session_state[pick_key] = []
            st.rerun()
        c_cnt.caption(f"Selected: **{len(st.session_state.get(pick_key) or [])}**")

        pick = st.multiselect(
            f"Select {label.lower()}(s) to add",
            list(id_map.keys()),
            key=pick_key,
        )
        if st.button(add_btn, key=f"{sk}_addbtn", type="primary", disabled=not pick):
            try:
                n = assign_entities_to_group(
                    entity_type, [id_map[lbl] for lbl in pick], group_id, uid(),
                )
                st.session_state[f"{sk}_reset_addsel"] = True
                ff.action_done(f"Added **{n}** record(s) to the group.")
            except Exception as e:
                st.error(str(e))

    st.divider()
    st.markdown("**Remove from group**")
    if not members:
        st.caption("Nothing to remove.")
    else:
        rem_map = {f"{m['code']} — {m['name']}": m["id"] for m in members}
        rem_key = f"{sk}_remsel"
        if st.session_state.pop(f"{sk}_reset_remsel", False):
            st.session_state.pop(rem_key, None)
        rem_pick = st.multiselect(
            f"Select {label.lower()}(s) to remove",
            list(rem_map.keys()),
            key=rem_key,
        )
        r1, r2 = st.columns(2)
        if r1.button(del_btn, key=f"{sk}_rembtn", disabled=not rem_pick):
            try:
                n = remove_entities_from_group(
                    entity_type, [rem_map[lbl] for lbl in rem_pick], uid(),
                )
                st.session_state[f"{sk}_reset_remsel"] = True
                ff.action_done(f"Removed **{n}** record(s) from the group.")
            except Exception as e:
                st.error(str(e))
        if r2.button("Remove all from group", key=f"{sk}_remall"):
            try:
                n = remove_entities_from_group(entity_type, [m["id"] for m in members], uid())
                ff.action_done(f"Removed **{n}** record(s) from the group.")
            except Exception as e:
                st.error(str(e))


def page_master_groups():
    std_page_header("Account & Item Groups", status="register", status_kind="shell")
    tab = sticky_page_tabs([
        "Customer Account Groups",
        "Supplier Account Groups",
        "Item / Product Groups",
        "Chart Account Groups",
    ], "master_groups_tab")
    if tab == "Customer Account Groups":
        st.caption("Like **Maintain Account Groups** — e.g. territory, channel, or CUSTOMER batches for reports.")
        _maintain_group_workspace("customer")
    elif tab == "Supplier Account Groups":
        st.caption("Supplier batches for payment runs, purchase analysis, or regional grouping.")
        _maintain_group_workspace("supplier")
    elif tab == "Item / Product Groups":
        st.caption("Like **Maintain Item Groups** — e.g. buyer ranges, brand lines, or production families.")
        _maintain_group_workspace("product")
    elif tab == "Chart Account Groups":
        st.caption("Group GL accounts for **Trial Balance**, **Balance Sheet**, and **General Ledger** (summary by group).")
        _maintain_group_workspace("account")
