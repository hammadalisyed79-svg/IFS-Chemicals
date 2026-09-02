"""Shared UI helpers for IFS Chemicals ERP."""

import io
import streamlit as st
from erp_ui import form_flow as ff
import pandas as pd
from application import data_gateway as db


def uid():
    u = st.session_state.get("user")
    return u["id"] if u else None


def user_role():
    u = st.session_state.get("user")
    return u.get("role") if u else None


def fmt_money(val):
    return f"Rs. {float(val or 0):,.2f}"


def party_download_filename(doc_label: str, party_name: str | None = "", *, ext: str = "pdf") -> str:
    """Build a Windows-safe download name like ``Sale Order - Customer Name.pdf``."""
    import re

    label = (doc_label or "Document").strip() or "Document"
    party = (party_name or "").strip()
    stem = f"{label} - {party}" if party else label
    stem = re.sub(r'[\\/:*?"<>|]+', " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip(" .")
    if not stem:
        stem = "document"
    # Keep filenames reasonably short for downloads
    if len(stem) > 120:
        stem = stem[:117].rstrip(" .") + "..."
    ext = (ext or "pdf").lstrip(".")
    return f"{stem}.{ext}"


def fmt_datetime(doc_date=None, time_val=None) -> str:
    """Format document date with time: ``YYYY-MM-DD HH:MM:SS``.

    Uses ``time_val`` (``created_at``, ``pass_time``, etc.) when the date field
    has no time. If only a date is available, returns the date alone.
    """
    date_s = ""
    time_s = ""

    raw = str(doc_date or "").strip().replace("T", " ")
    if raw:
        if len(raw) >= 19 and raw[10] == " ":
            return raw[:19]
        if len(raw) >= 16 and raw[10] == " ":
            hhmm = raw[11:16]
            return f"{raw[:10]} {hhmm}:00" if len(hhmm) == 5 else raw[:16]
        # date only
        date_s = raw[:10]

    tv = str(time_val or "").strip().replace("T", " ")
    if tv:
        if len(tv) >= 19 and tv[10] == " ":
            if not date_s:
                return tv[:19]
            time_s = tv[11:19]
        elif len(tv) >= 8 and tv[2] == ":":
            time_s = tv[:8]
        elif len(tv) >= 5 and tv[2] == ":":
            time_s = f"{tv[:5]}:00"

    if date_s and time_s:
        return f"{date_s} {time_s}"
    if date_s:
        return date_s
    if time_s:
        return time_s
    return "—"


def fmt_datetime_from_record(record, date_field: str, *, time_field: str | None = None) -> str:
    """Pick date + best available time from a voucher/invoice record."""
    if not record:
        return "—"
    d = record.get(date_field)
    t = record.get(time_field) if time_field else None
    if not t:
        for k in ("created_at", "posted_at", "approved_at", "modified_at", "pass_time", "slip_time"):
            if record.get(k):
                t = record.get(k)
                break
    return fmt_datetime(d, t)


def fmt_signed_dr_cr(val):
    """Finance Manager style: amount with Dr / Cr (positive = Debit, negative = Credit)."""
    try:
        v = float(val or 0)
    except (TypeError, ValueError):
        v = 0.0
    if abs(v) < 0.005:
        return "Rs. 0.00"
    side = "Dr" if v > 0 else "Cr"
    return f"Rs. {abs(v):,.2f} {side}"


def format_amount(val, decimals: int = 2) -> str:
    """Plain amount with thousand separators, e.g. 1,500,000.00"""
    try:
        return f"{float(val or 0):,.{int(decimals)}f}"
    except (TypeError, ValueError):
        return f"{0.0:,.{int(decimals)}f}"


def parse_money(text, default: float = 0.0) -> float:
    """Parse typed money that may include commas / Rs. prefix."""
    if text is None:
        return float(default or 0)
    if isinstance(text, (int, float)):
        return float(text)
    s = str(text).strip()
    if not s:
        return float(default or 0)
    for token in ("Rs.", "Rs", "PKR", "pkr", "RS."):
        s = s.replace(token, "")
    s = s.replace(",", "").replace(" ", "").strip()
    try:
        return float(s)
    except ValueError:
        return float(default or 0)


def set_money_widget_value(key: str, amount: float, *, decimals: int = 2) -> None:
    """Force a money_input widget (and its internal keys) to a numeric amount."""
    amt = round(float(amount or 0), int(decimals))
    st.session_state[key] = format_amount(amt, decimals)
    st.session_state[f"{key}__num"] = amt
    st.session_state[f"{key}__seed"] = amt


def money_input(
    label,
    value=0.0,
    *,
    key,
    min_value=None,
    max_value=None,
    help=None,
    disabled=False,
    label_visibility="visible",
    decimals: int = 2,
    placeholder=None,
    on_change=None,
    args=None,
    kwargs=None,
) -> float:
    """
    Professional amount entry with thousand separators (1,500,000.00).
    Returns float. Use instead of st.number_input for money fields.
    """
    raw_key = f"{key}__num"
    seed_key = f"{key}__seed"
    want = float(value or 0)

    # Migrate leftover float session values from old number_input widgets
    if key in st.session_state and not isinstance(st.session_state.get(key), str):
        try:
            want = float(st.session_state[key] or 0)
        except (TypeError, ValueError):
            pass
        st.session_state[key] = format_amount(want, decimals)

    if seed_key not in st.session_state:
        st.session_state[seed_key] = want
        st.session_state[raw_key] = want
        if key not in st.session_state:
            st.session_state[key] = format_amount(want, decimals)
    elif abs(want - float(st.session_state.get(seed_key) or 0)) > 1e-9:
        # Parent default changed (e.g. Load for Edit)
        st.session_state[seed_key] = want
        st.session_state[raw_key] = want
        st.session_state[key] = format_amount(want, decimals)

    if raw_key not in st.session_state:
        st.session_state[raw_key] = parse_money(st.session_state.get(key), want)
    if key not in st.session_state:
        st.session_state[key] = format_amount(st.session_state[raw_key], decimals)

    ph = placeholder if placeholder is not None else format_amount(0, decimals)
    # Reformat on each script run after Enter/blur.
    cur = str(st.session_state.get(key) or "").strip()
    if cur and not cur.endswith((".", ",")):
        probed = parse_money(cur, want)
        if min_value is not None:
            probed = max(float(min_value), probed)
        if max_value is not None:
            probed = min(float(max_value), probed)
        probed = round(probed, int(decimals))
        nice = format_amount(probed, decimals)
        if nice != cur:
            st.session_state[key] = nice
        st.session_state[raw_key] = probed

    ti_kwargs = {
        "label": label,
        "key": key,
        "help": help or "Type 1500000 or 1,500,000.00 — shown with thousand separators",
        "disabled": disabled,
        "label_visibility": label_visibility,
        "placeholder": ph,
    }
    # on_change is not supported inside st.form — callers must avoid that case.
    if on_change is not None:
        ti_kwargs["on_change"] = on_change
        if args is not None:
            ti_kwargs["args"] = args
        if kwargs is not None:
            ti_kwargs["kwargs"] = kwargs
    st.text_input(**ti_kwargs)
    live = parse_money(st.session_state.get(key), st.session_state.get(raw_key, 0))
    if min_value is not None:
        live = max(float(min_value), live)
    if max_value is not None:
        live = min(float(max_value), live)
    live = round(float(live), int(decimals))
    st.session_state[raw_key] = live
    return live


def dr_cr_money_inputs(
    *,
    dr_key: str,
    cr_key: str,
    debit: float = 0.0,
    credit: float = 0.0,
    dr_label: str = "Dr",
    cr_label: str = "Cr",
    min_value: float = 0.0,
    decimals: int = 2,
    help_dr: str | None = None,
    help_cr: str | None = None,
) -> tuple[float, float]:
    """Paired Debit/Credit amounts — entering one side clears the other to NIL.

    Use on Journal Voucher lines and any other Dr/Cr entry screens.
    Must not be used inside ``st.form`` (needs on_change).
    """
    side_key = f"{dr_key}__{cr_key}__last_side"
    prev_dr_key = f"{dr_key}__pair_prev"
    prev_cr_key = f"{cr_key}__pair_prev"

    def _on_dr():
        v = parse_money(st.session_state.get(dr_key), 0.0)
        st.session_state[side_key] = "dr"
        if v > 0.0005:
            set_money_widget_value(cr_key, 0.0, decimals=decimals)

    def _on_cr():
        v = parse_money(st.session_state.get(cr_key), 0.0)
        st.session_state[side_key] = "cr"
        if v > 0.0005:
            set_money_widget_value(dr_key, 0.0, decimals=decimals)

    dr = money_input(
        dr_label,
        value=float(debit or 0),
        min_value=min_value,
        key=dr_key,
        decimals=decimals,
        help=help_dr or "Debit amount — Credit on this line clears to 0",
        on_change=_on_dr,
    )
    cr = money_input(
        cr_label,
        value=float(credit or 0),
        min_value=min_value,
        key=cr_key,
        decimals=decimals,
        help=help_cr or "Credit amount — Debit on this line clears to 0",
        on_change=_on_cr,
    )

    # Safety if both somehow non-zero (paste / load / race): keep last side
    if dr > 0.0005 and cr > 0.0005:
        last = st.session_state.get(side_key)
        prev_dr = float(st.session_state.get(prev_dr_key) or 0)
        prev_cr = float(st.session_state.get(prev_cr_key) or 0)
        if last == "dr" or (last != "cr" and abs(dr - prev_dr) >= abs(cr - prev_cr)):
            set_money_widget_value(cr_key, 0.0, decimals=decimals)
            cr = 0.0
        else:
            set_money_widget_value(dr_key, 0.0, decimals=decimals)
            dr = 0.0

    st.session_state[prev_dr_key] = dr
    st.session_state[prev_cr_key] = cr
    return dr, cr


def sale_payment_ui(
    key_prefix, invoice_total, payment_mode=None, paid_amount=None, retail_sale=False,
):
    """Payment mode + paid amount. Full invoice paid auto-fill only for **retail** cash sales."""
    total = float(invoice_total or 0)
    if retail_sale:
        st.info(
            f"**Retail / cash sale:** cash received must equal invoice total (**{fmt_money(total)}**). "
            "A **Cash Book** receipt is created when the invoice is **approved**."
        )
        st.metric("Cash paid (required)", fmt_money(total))
        return "cash", total

    modes = ["credit", "cash", "bank"]
    idx = modes.index(payment_mode) if payment_mode in modes else 0
    pay_mode = st.selectbox("Payment Mode", modes, index=idx, key=f"{key_prefix}_paymode")
    default_paid = float(paid_amount or 0)
    paid = money_input(
        "Paid Amount",
        value=default_paid,
        key=f"{key_prefix}_paid",
        min_value=0.0,
        help="Leave 0 for credit unless customer pays now (bank/cash on account).",
    )
    if pay_mode == "cash":
        st.caption(
            f"Cash sale: on save, paid must equal invoice total (**{fmt_money(total)}**). "
            "Use **Retail / cash only** above to lock paid amount automatically."
        )
    elif pay_mode == "bank" and paid > 0:
        st.caption("Bank receipt posts on approval when paid amount is entered.")
    elif pay_mode == "credit" and paid <= 0:
        st.caption("Credit — no payment until you enter paid amount or approve with receipt.")
    return pay_mode, paid


def gate_pass_payment_caption(gp_row):
    """Human-readable payment line for gate pass display."""
    mode = (gp_row.get("invoice_payment_mode") or gp_row.get("payment_mode") or "").lower()
    if not mode and not gp_row.get("sales_invoice_id"):
        return ""
    total = float(gp_row.get("invoice_total") or 0)
    paid = float(gp_row.get("invoice_paid_amount") or gp_row.get("paid_amount") or 0)
    label = mode.title() if mode else "—"
    if mode == "cash" and paid > 0:
        return f"Payment: **Cash** — cash paid **{fmt_money(paid)}**"
    if mode == "cash":
        return "Payment: **Cash**"
    if mode == "credit":
        return "Payment: **Credit**"
    if mode == "bank":
        return "Payment: **Bank**"
    return f"Payment: **{label}**"


def page_header(title, subtitle="", compact=True, *, status=None, status_kind="shell"):
    from erp_ui.page_shell import render_page_header_block
    st.session_state["_page_header_rendered"] = True
    render_page_header_block(
        title, subtitle, compact=compact, status=status, status_kind=status_kind,
    )


def std_page_header(screen: str, title: str | None = None, subtitle: str | None = None, **kwargs):
    """Standard header using nav titles/taglines — breadcrumbs + subtitle on every screen."""
    from erp_ui.nav import screen_title, screen_tagline
    page_header(
        title or screen_title(screen),
        screen_tagline(screen) if subtitle is None else subtitle,
        **kwargs,
    )


def sticky_page_tabs(
    labels: list[str],
    state_key: str,
    *,
    open_alias_key: str | None = None,
) -> str:
    """Section switcher that keeps the active tab across save / approve / rerun.

    Streamlit ``st.tabs`` always jumps back to the first tab after ``st.rerun()``.
    Use this for Register / Drafts / New / Edit style pages.
    """
    opts = [str(x) for x in labels]
    if not opts:
        return ""

    # External open requests (e.g. document hub sets sal_open_tab = "edit")
    if open_alias_key:
        raw = st.session_state.pop(open_alias_key, None)
        if raw is not None:
            want = str(raw).strip()
            mapped = None
            for o in opts:
                if o == want or o.lower() == want.lower() or o.lower().replace(" ", "_") == want.lower().replace(" ", "_"):
                    mapped = o
                    break
            if mapped is None and want.lower() in ("edit", "edit_delete", "edit / delete"):
                mapped = next((o for o in opts if o.lower().startswith("edit")), None)
            if mapped is None and want.lower() in ("new", "add", "add new"):
                mapped = next((o for o in opts if o.lower() in ("new", "add", "add new")), None)
            if mapped:
                st.session_state[state_key] = mapped

    if state_key not in st.session_state or st.session_state.get(state_key) not in opts:
        st.session_state[state_key] = opts[0]

    st.markdown('<div class="erp-section-tabs">', unsafe_allow_html=True)
    cols = st.columns(len(opts), gap="small")
    for i, label in enumerate(opts):
        active = st.session_state.get(state_key) == label
        with cols[i]:
            if st.button(
                label,
                key=f"{state_key}_tab_{i}",
                type="primary" if active else "secondary",
                use_container_width=True,
            ):
                if st.session_state.get(state_key) != label:
                    st.session_state[state_key] = label
                    st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)
    return st.session_state[state_key]


def section_header(title: str) -> None:
    """Section heading — matches CEO desktop Quick Actions / module sections."""
    from html import escape
    st.markdown(f'<p class="erp-desk-section">{escape(title)}</p>', unsafe_allow_html=True)


def province_city_fields(key_prefix: str, province: str = "", city: str = "", *, reset_token=None):
    """
  Province + city pickers with auto-suggested cities (place outside st.form).
  Returns (province, city) from current widget state.
    """
    from erp_ui.pakistan_locations import (
        PROVINCES,
        _OTHER_CITY,
        _SELECT_CITY,
        _SELECT_PROVINCE,
        cities_for_province,
        province_for_city,
    )
    from application import data_gateway as db

    prov_key = f"{key_prefix}_province"
    city_key = f"{key_prefix}_city"
    other_key = f"{key_prefix}_city_other"
    reset_key = f"{key_prefix}_loc_reset"

    if reset_token is not None and st.session_state.get(reset_key) != reset_token:
        st.session_state[reset_key] = reset_token
        prov_val = (province or "").strip() or province_for_city(city) or _SELECT_PROVINCE
        st.session_state[prov_key] = prov_val if prov_val in PROVINCES else _SELECT_PROVINCE
        known = cities_for_province(st.session_state[prov_key])
        if city and city in known:
            st.session_state[city_key] = city
            st.session_state[other_key] = ""
        elif city:
            st.session_state[city_key] = _OTHER_CITY
            st.session_state[other_key] = city
        else:
            st.session_state[city_key] = _SELECT_CITY
            st.session_state[other_key] = ""

    prov_options = [_SELECT_PROVINCE] + PROVINCES
    c1, c2 = st.columns(2)
    with c1:
        sel_prov = st.selectbox("Province", prov_options, key=prov_key)
    last_prov_key = f"{key_prefix}_last_prov"
    if last_prov_key not in st.session_state:
        st.session_state[last_prov_key] = sel_prov
    elif st.session_state.get(last_prov_key) != sel_prov:
        st.session_state[last_prov_key] = sel_prov
        st.session_state[city_key] = _SELECT_CITY
        st.session_state[other_key] = ""

    with c2:
        city_opts: list[str] = []
        if sel_prov and sel_prov != _SELECT_PROVINCE:
            city_opts.extend(cities_for_province(sel_prov))
        for c in db.get_distinct_cities():
            if c and c not in city_opts:
                if sel_prov == _SELECT_PROVINCE or province_for_city(c) in (None, sel_prov):
                    city_opts.append(c)
        city_opts = sorted(set(city_opts), key=str.casefold)
        city_labels = [_SELECT_CITY] + city_opts + [_OTHER_CITY]
        sel_city = st.selectbox("City", city_labels, key=city_key)

    final_city = ""
    if sel_city == _OTHER_CITY:
        final_city = st.text_input(
            "City name",
            key=other_key,
            placeholder="Type city if not listed",
        ).strip()
    elif sel_city != _SELECT_CITY:
        final_city = sel_city

    final_prov = "" if sel_prov == _SELECT_PROVINCE else sel_prov
    return final_prov, final_city


def filter_master_records(records, query, extra_fields=None):
    """Filter master rows by code, name, phone, city, etc. Supports multi-word search."""
    if not query or not str(query).strip():
        return records
    tokens = str(query).strip().lower().split()
    fields = [
        "code", "name", "full_name", "phone", "mobile", "ntn", "strn", "email",
        "city", "address", "contact_person", "category", "unit", "item_type",
        "group_name", "group_code",
    ]
    if extra_fields:
        fields.extend(extra_fields)

    def _blob(r):
        return " ".join(str(r.get(f, "") or "") for f in fields).lower()

    return [r for r in records if all(t in _blob(r) for t in tokens)]


def natural_code_sort_key(code) -> list:
    """Sort product/party codes in sequence: DW1005 before DW1006, DTT010 before DTT013."""
    import re
    s = str(code or "").strip()
    if not s:
        return [("", 0, "")]
    parts = re.split(r"(\d+)", s)
    key = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            key.append((0, int(part), ""))
        else:
            key.append((1, 0, part.casefold()))
    return key


def filter_products_for_line(products, query, max_results=500):
    """Rank product matches: exact code, code prefix, code contains, then name.

    Within each rank, codes are sorted in sequence (natural code order).
    """
    if not query or not str(query).strip():
        return sorted(products, key=lambda p: natural_code_sort_key(p.get("code")))[:max_results]
    q = str(query).strip().lower()
    # Ignore common separators so "DT 1060" / "DT-1060" still match DT1060
    q_compact = "".join(ch for ch in q if ch.isalnum())
    exact, prefix, code_hit, name_hit = [], [], [], []
    seen = set()
    for p in products:
        code = str(p.get("code") or "").lower()
        name = str(p.get("name") or "").lower()
        code_compact = "".join(ch for ch in code if ch.isalnum())
        pid = p.get("id")
        if pid in seen:
            continue
        if code == q or (q_compact and code_compact == q_compact):
            exact.append(p); seen.add(pid)
        elif code.startswith(q) or (q_compact and code_compact.startswith(q_compact)):
            prefix.append(p); seen.add(pid)
        elif q in code or (q_compact and q_compact in code_compact):
            code_hit.append(p); seen.add(pid)
        elif q in name or all(t in f"{code} {name}" for t in q.split()):
            name_hit.append(p); seen.add(pid)
    _ck = lambda p: natural_code_sort_key(p.get("code"))
    exact.sort(key=_ck)
    prefix.sort(key=_ck)
    code_hit.sort(key=_ck)
    name_hit.sort(key=_ck)
    ranked = exact + prefix + code_hit + name_hit
    return ranked[:max_results]


def form_compact(key: str):
    """Wrap voucher/entry UI so fields use adequate widths (not full-bleed).

    Use a key ending in ``_form_blk`` (or include that substring) so layout CSS
    caps width and restores Streamlit column ratios.
    """
    k = key if "_form_blk" in key else f"{key}_form_blk"
    return st.container(key=k)


def form_line(key: str):
    """Visually group one multi-field entry line inside a compact form."""
    k = key if "_form_line" in key else f"{key}_form_line"
    return st.container(key=k)


def smart_select(
    label,
    records,
    key,
    id_field="id",
    format_fn=None,
    placeholder="Type code, name, phone, or city...",
    max_results=100,
    allow_all=False,
    all_label=None,
    default_id=None,
    blank_default=None,
    blank_label="- Select -",
    layout: str = "stack",
):
    """Instant search — filters as you type; safe for thousands of master records.

    ``default_id``: prefer this record when the search box is empty (e.g. edit forms).
    ``blank_default``: when True (default if no ``default_id`` and not ``allow_all``),
    the select starts blank so new forms never auto-pick the first row.
    ``layout``: ``stack`` = Search above Select (default; safe inside nested columns);
    ``row`` = Search | Select side-by-side (use only at top level — Streamlit allows
    one column-nesting level).
    """
    if not records:
        st.warning(f"No {label} found.")
        return None, None, None

    # Edit forms with a saved id should open on that row, not a blank option
    use_blank = blank_default if blank_default is not None else (
        default_id is None and not allow_all
    )

    total = len(records)
    # Keys under ``{key}_*`` so form clears (prefix sal_/pur_/…) wipe search + selection
    search_key = f"{key}_srch"
    sel_key = f"{key}_sel"
    # Drop legacy keys that stuck the first master row across New screens
    for legacy in (f"srch_{key}", f"sel_{key}"):
        st.session_state.pop(legacy, None)

    all_lbl = all_label or f"(All {label.lower()}s)"

    def _fmt(r):
        return format_fn(r) if format_fn else f"{r.get('code', '')} - {r.get('name', r.get('full_name', ''))}"

    def _render_search():
        return st.text_input(
            f"Search {label}",
            key=search_key,
            placeholder=placeholder,
        ).strip()

    # Need search value before filtering — render search first
    if layout == "row":
        c_search, c_pick = st.columns([1.15, 2.35])
        with c_search:
            search = _render_search()
    else:
        search = _render_search()
        c_pick = None

    if search:
        filtered = filter_master_records(records, search)
        exact = [r for r in filtered if str(r.get("code", "")).lower() == search.lower()]
        if exact:
            filtered = exact + [r for r in filtered if r not in exact]
    else:
        filtered = sorted(records, key=lambda r: natural_code_sort_key(r.get("code")))[:max_results]

    # Pin saved/default record so edit screens don't jump to first account (e.g. CASH)
    if default_id is not None and not search:
        pinned = [r for r in records if r.get(id_field) == default_id]
        if not pinned:
            pinned = [r for r in records if str(r.get(id_field)) == str(default_id)]
        if pinned:
            pid = pinned[0].get(id_field)
            filtered = pinned + [r for r in filtered if r.get(id_field) != pid]
            filtered = filtered[:max_results]

    def _caption_and_select():
        if not filtered:
            if allow_all:
                st.caption(f"No match in {total:,} {label.lower()} records — **{all_lbl}** still applies.")
                sel = st.selectbox(f"Select {label}", [all_lbl], key=sel_key)
                return sel, None, None
            st.caption(f"No match in {total:,} {label.lower()} records — try another search.")
            return None, None, None

        shown = min(len(filtered), max_results)
        if search:
            st.caption(
                f"Typing: **{search}** · **{len(filtered):,}** match(es)"
                + (f" — showing first **{shown}**" if len(filtered) > max_results else "")
            )
        else:
            st.caption(f"Showing first **{shown}** of **{total:,}** — type to search all")

        labels = [_fmt(r) for r in filtered[:max_results]]
        id_map = {labels[i]: filtered[i] for i in range(len(labels))}
        box_labels = list(labels)
        if allow_all:
            box_labels = [all_lbl] + box_labels
        elif use_blank:
            box_labels = [blank_label] + box_labels

        default_idx = 0
        if default_id is not None and not search and box_labels:
            for i, r in enumerate(filtered[:max_results]):
                if r.get(id_field) == default_id or str(r.get(id_field)) == str(default_id):
                    default_idx = i + (1 if allow_all else 0)
                    break

        if sel_key not in st.session_state:
            sel = st.selectbox(
                f"Select {label}", box_labels, index=min(default_idx, len(box_labels) - 1), key=sel_key,
            )
        else:
            prev = st.session_state.get(sel_key)
            if prev not in box_labels:
                st.session_state[sel_key] = box_labels[min(default_idx, len(box_labels) - 1)]
            sel = st.selectbox(f"Select {label}", box_labels, key=sel_key)

        if allow_all and sel == all_lbl:
            return sel, None, None
        if use_blank and sel == blank_label:
            return None, None, None
        row = id_map.get(sel)
        return sel, row[id_field] if row else None, row

    if layout == "row":
        with c_pick:
            return _caption_and_select()
    return _caption_and_select()


BLANK_SELECT = "- Select -"



def options_with_blank(labels, blank=BLANK_SELECT):
    """Prepend a blank placeholder for plain st.selectbox New forms."""
    labs = list(labels)
    return [blank] + labs, blank


def require_selected(label, selected, blank=BLANK_SELECT, *, soft=False):
    """Return False when the blank placeholder is still selected."""
    if selected is None or selected == blank or selected == "":
        msg = f"Select a {label}."
        if soft:
            st.info(msg)
        else:
            st.error(msg)
        return False
    return True


def master_group_filter(entity_type, key_prefix):
    """List-tab filter: returns group_id or None."""
    from db_groups import group_options
    opts = group_options(entity_type, include_none=False, active_only=True)
    if not opts:
        return None
    labels = ["(All groups)"] + list(opts.keys())
    sel = st.selectbox("Filter by group", labels, key=f"{key_prefix}_gfilt")
    return opts[sel] if sel != "(All groups)" else None


def master_group_select(entity_type, key_prefix, current_id=None):
    """Select a custom group (product / customer / supplier)."""
    from db_groups import group_options
    opts = group_options(entity_type)
    labels = list(opts.keys())
    default_idx = 0
    if current_id:
        for i, lbl in enumerate(labels):
            if opts[lbl] == current_id:
                default_idx = i
                break
    sel = st.selectbox("Group", labels, index=default_idx, key=f"{key_prefix}_grp")
    return opts[sel]


def master_list_search(
    label, records, key, columns, rename, extra_fields=None,
    *, show_balance_dr_cr: bool = False, export_title: str | None = None,
):
    """Searchable list tab for master data.

    When ``show_balance_dr_cr`` is True and rows have ``balance`` (signed:
    +Debit / −Credit), Debit & Credit columns plus totals KPIs are shown,
    and PDF / Excel / CSV export is offered.
    """
    q = st.text_input(
        f"Search {label}",
        key=f"list_{key}",
        placeholder="Code, name, group, phone, city — type to filter...",
    )
    rows = filter_master_records(records, q, extra_fields=extra_fields) if q.strip() else records
    st.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>{label}</p>"
        f"<p class='txn-kpi-val'>{len(rows):,} <span style='font-size:0.75rem;font-weight:600;"
        f"opacity:0.7'>of {len(records):,}</span></p></div>",
        unsafe_allow_html=True,
    )
    if not rows:
        st.info("No records match your search.")
        return
    from html import escape
    df = pd.DataFrame(rows)
    use = [c for c in columns if c in df.columns]
    rename = dict(rename or {})
    total_dr = total_cr = 0.0
    if show_balance_dr_cr and "balance" in df.columns:
        bals = [float(v or 0) for v in df["balance"].tolist()]
        total_dr = round(sum(b for b in bals if b > 0.005), 2)
        total_cr = round(sum(abs(b) for b in bals if b < -0.005), 2)
        df["debit"] = [round(b, 2) if b > 0.005 else 0.0 for b in bals]
        df["credit"] = [round(abs(b), 2) if b < -0.005 else 0.0 for b in bals]
        # Insert Debit / Credit after Balance (or at end)
        if "balance" in use:
            bi = use.index("balance")
            use = use[: bi + 1] + ["debit", "credit"] + use[bi + 1 :]
        else:
            use = use + ["debit", "credit"]
        rename.setdefault("debit", "Debit")
        rename.setdefault("credit", "Credit")
        k1, k2, k3 = st.columns(3)
        k1.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Total Debit</p>"
            f"<p class='txn-kpi-val'>{escape(fmt_money(total_dr))}</p></div>",
            unsafe_allow_html=True,
        )
        k2.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Total Credit</p>"
            f"<p class='txn-kpi-val'>{escape(fmt_money(total_cr))}</p></div>",
            unsafe_allow_html=True,
        )
        net = round(total_dr - total_cr, 2)
        k3.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Net Balance</p>"
            f"<p class='txn-kpi-val'>{escape(fmt_signed_dr_cr(net))}</p></div>",
            unsafe_allow_html=True,
        )
    # Prefer HTML table when Active column present so status badges show
    if "is_active" in use:
        labels = [rename.get(c, c) for c in use]
        ths = "".join(f"<th>{escape(str(h))}</th>" for h in labels)
        body = []
        for _, rec in df[use].iterrows():
            cells = []
            for c in use:
                val = rec.get(c)
                if c == "is_active":
                    active = bool(int(val or 0)) if val is not None and str(val) != "" else bool(val)
                    cells.append(
                        '<td class="txn-status-cell">'
                        + (
                            '<span class="inv-badge inv-badge-approved">Active</span>'
                            if active
                            else '<span class="inv-badge inv-badge-cancelled">Inactive</span>'
                        )
                        + "</td>"
                    )
                elif c in ("credit_limit", "balance", "opening_balance", "rate", "cost", "debit", "credit"):
                    try:
                        cells.append(f"<td class='txn-num'>{escape(fmt_money(val))}</td>")
                    except Exception:
                        cells.append(f"<td>{escape(str(val if val is not None else '—'))}</td>")
                else:
                    cells.append(f"<td>{escape(str(val if val is not None else '—'))}</td>")
            body.append("<tr>" + "".join(cells) + "</tr>")
        if show_balance_dr_cr and ("debit" in use or "credit" in use):
            foot = []
            for c in use:
                if c == "debit":
                    foot.append(f"<td class='txn-num'><b>{escape(fmt_money(total_dr))}</b></td>")
                elif c == "credit":
                    foot.append(f"<td class='txn-num'><b>{escape(fmt_money(total_cr))}</b></td>")
                elif c == "balance":
                    foot.append(
                        f"<td class='txn-num'><b>{escape(fmt_signed_dr_cr(total_dr - total_cr))}</b></td>"
                    )
                elif c == use[0]:
                    foot.append("<td><b>TOTAL</b></td>")
                else:
                    foot.append("<td></td>")
            body.append("<tr>" + "".join(foot) + "</tr>")
        st.markdown(
            '<div class="txn-reg-wrap"><table class="txn-reg-table">'
            f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
            unsafe_allow_html=True,
        )
    else:
        render_dataframe_html_table(df[use].rename(columns=rename))

    if show_balance_dr_cr or export_title:
        export_df = df[use].rename(columns=rename).copy()
        title = export_title or f"{label} List"
        summary = None
        if show_balance_dr_cr:
            summary = {
                "Total Debit": total_dr,
                "Total Credit": total_cr,
                "Net Balance": total_dr - total_cr,
            }
        from erp_ui.report_print import report_toolbar
        report_toolbar(
            export_df, title, f"{key}_list",
            summary=summary, key_prefix=f"ml_{key}", layout="landscape",
        )


def stock_status_badge(qty, reorder_level=0):
    q = float(qty or 0)
    r = float(reorder_level or 0)
    if q < 0:
        return '<span class="inv-badge inv-badge-rejected">Negative</span>'
    if r > 0 and q <= r:
        return '<span class="inv-badge inv-badge-pending">Low</span>'
    return '<span class="inv-badge inv-badge-approved">OK</span>'


def render_stock_kpi_strip(rows):
    """KPI cards + optional status strip for inventory rows."""
    from html import escape

    n = len(rows)
    total_val = sum(
        float(r.get("stock_qty") or 0) * float(r.get("purchase_price") or 0) for r in rows
    )
    low = sum(
        1 for r in rows
        if float(r.get("reorder_level") or 0) > 0
        and float(r.get("stock_qty") or 0) <= float(r.get("reorder_level") or 0)
    )
    neg = sum(1 for r in rows if float(r.get("stock_qty") or 0) < 0)
    c1, c2, c3, c4 = st.columns(4 if neg else 3, gap="small")
    c1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Items</p>"
        f"<p class='txn-kpi-val'>{n:,}</p></div>",
        unsafe_allow_html=True,
    )
    c2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Stock Value</p>"
        f"<p class='txn-kpi-val'>{escape(fmt_money(total_val))}</p></div>",
        unsafe_allow_html=True,
    )
    c3.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Below Reorder</p>"
        f"<p class='txn-kpi-val'>{low:,}</p></div>",
        unsafe_allow_html=True,
    )
    if neg:
        c4.markdown(
            f"<div class='txn-kpi-card'><p class='txn-kpi'>Negative Qty</p>"
            f"<p class='txn-kpi-val'>{neg:,}</p></div>",
            unsafe_allow_html=True,
        )
    if low or neg:
        parts = []
        if low:
            parts.append(
                '<span class="inv-badge inv-badge-pending">Low</span>&nbsp;'
                f"<strong>{low}</strong>"
            )
        if neg:
            parts.append(
                '<span class="inv-badge inv-badge-rejected">Negative</span>&nbsp;'
                f"<strong>{neg}</strong>"
            )
        st.markdown(
            f'<div class="txn-status-strip">{" &nbsp;·&nbsp; ".join(parts)}</div>',
            unsafe_allow_html=True,
        )


def render_stock_html_table(rows):
    """Register-style stock table with qty status badges."""
    from html import escape

    ths = "".join(
        f"<th>{h}</th>"
        for h in ("Code", "Name", "Category", "Unit", "Qty", "Cost", "Reorder", "Value", "Status")
    )
    body = []
    for r in rows:
        qty = float(r.get("stock_qty") or 0)
        cost = float(r.get("purchase_price") or 0)
        body.append(
            "<tr>"
            f"<td>{escape(str(r.get('code') or ''))}</td>"
            f"<td>{escape(str(r.get('name') or ''))}</td>"
            f"<td>{escape(str(r.get('category') or '—'))}</td>"
            f"<td>{escape(str(r.get('unit') or ''))}</td>"
            f"<td class='txn-num'>{qty:,.3f}</td>"
            f"<td class='txn-num'>{escape(fmt_money(cost))}</td>"
            f"<td class='txn-num'>{float(r.get('reorder_level') or 0):,.3f}</td>"
            f"<td class='txn-num'>{escape(fmt_money(qty * cost))}</td>"
            f"<td class='txn-status-cell'>"
            f"{stock_status_badge(qty, r.get('reorder_level'))}</td>"
            "</tr>"
        )
    st.markdown(
        '<div class="txn-reg-wrap"><table class="txn-reg-table">'
        f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
        unsafe_allow_html=True,
    )


def adjustment_type_badge(adj_type: str | None) -> str:
    """IN/OUT badge for stock adjustment rows."""
    t = (adj_type or "").lower()
    if t == "in":
        return '<span class="inv-badge inv-badge-approved">IN</span>'
    if t == "out":
        return '<span class="inv-badge inv-badge-rejected">OUT</span>'
    from html import escape
    return f'<span class="inv-badge inv-badge-draft">{escape(str(adj_type or "—"))}</span>'


def render_adjustment_html_table(hist):
    """Adjustment history register with IN/OUT badges and KPI strip."""
    from html import escape

    if not hist:
        return
    ins = sum(1 for r in hist if (r.get("adjustment_type") or "").lower() == "in")
    outs = sum(1 for r in hist if (r.get("adjustment_type") or "").lower() == "out")
    k1, k2, k3 = st.columns(3, gap="small")
    k1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Adjustments</p>"
        f"<p class='txn-kpi-val'>{len(hist):,}</p></div>",
        unsafe_allow_html=True,
    )
    k2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Stock IN</p>"
        f"<p class='txn-kpi-val'>{ins:,}</p></div>",
        unsafe_allow_html=True,
    )
    k3.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Stock OUT</p>"
        f"<p class='txn-kpi-val'>{outs:,}</p></div>",
        unsafe_allow_html=True,
    )
    if ins or outs:
        parts = []
        if ins:
            parts.append(
                '<span class="inv-badge inv-badge-approved">IN</span>&nbsp;'
                f"<strong>{ins}</strong>"
            )
        if outs:
            parts.append(
                '<span class="inv-badge inv-badge-rejected">OUT</span>&nbsp;'
                f"<strong>{outs}</strong>"
            )
        st.markdown(
            f'<div class="txn-status-strip">{" &nbsp;·&nbsp; ".join(parts)}</div>',
            unsafe_allow_html=True,
        )
    ths = "".join(f"<th>{h}</th>" for h in ("Date", "Code", "Item", "Type", "Qty", "Reason"))
    body = []
    for r in hist:
        qty = float(r.get("quantity") or 0)
        body.append(
            "<tr>"
            f"<td>{escape(str(r.get('adjustment_date') or ''))}</td>"
            f"<td>{escape(str(r.get('item_code') or ''))}</td>"
            f"<td>{escape(str(r.get('item_name') or ''))}</td>"
            f"<td class='txn-status-cell'>{adjustment_type_badge(r.get('adjustment_type'))}</td>"
            f"<td class='txn-num'>{qty:,.3f}</td>"
            f"<td>{escape(str(r.get('reason') or '—'))}</td>"
            "</tr>"
        )
    st.markdown(
        '<div class="txn-reg-wrap"><table class="txn-reg-table">'
        f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
        unsafe_allow_html=True,
    )


def render_stock_report_item_table(rows):
    """Stock report item-wise register with status badges."""
    from html import escape

    ths = "".join(
        f"<th>{h}</th>"
        for h in (
            "Code", "Name", "Category", "Group", "Type", "Unit",
            "Stock Qty", "Unit Cost", "Stock Value", "Reorder", "Status",
        )
    )
    body = []
    for r in rows:
        qty = float(r.get("stock_qty") or 0)
        cost = float(r.get("unit_cost") or r.get("purchase_price") or 0)
        val = float(r.get("stock_value") or 0)
        status = r.get("status") or "OK"
        if status == "Low":
            badge = '<span class="inv-badge inv-badge-pending">Low</span>'
        elif qty < 0:
            badge = '<span class="inv-badge inv-badge-rejected">Negative</span>'
        else:
            badge = '<span class="inv-badge inv-badge-approved">OK</span>'
        body.append(
            "<tr>"
            f"<td>{escape(str(r.get('code') or ''))}</td>"
            f"<td>{escape(str(r.get('name') or ''))}</td>"
            f"<td>{escape(str(r.get('category') or '—'))}</td>"
            f"<td>{escape(str(r.get('group_name') or 'Unassigned'))}</td>"
            f"<td>{escape(str(r.get('item_type') or ''))}</td>"
            f"<td>{escape(str(r.get('unit') or ''))}</td>"
            f"<td class='txn-num'>{qty:,.4f}</td>"
            f"<td class='txn-num'>{escape(fmt_money(cost))}</td>"
            f"<td class='txn-num'>{escape(fmt_money(val))}</td>"
            f"<td class='txn-num'>{float(r.get('reorder_level') or 0):,.4f}</td>"
            f"<td class='txn-status-cell'>{badge}</td>"
            "</tr>"
        )
    st.markdown(
        '<div class="txn-reg-wrap"><table class="txn-reg-table">'
        f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
        unsafe_allow_html=True,
    )


def render_ledger_kpi_strip(opening, period_debit, period_credit, closing, *, signed_open_close=True):
    """Ledger opening / period / closing KPI cards."""
    from html import escape

    o = fmt_signed_dr_cr(opening) if signed_open_close else fmt_money(opening)
    c = fmt_signed_dr_cr(closing) if signed_open_close else fmt_money(closing)
    m1, m2, m3, m4 = st.columns(4, gap="small")
    m1.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Opening</p>"
        f"<p class='txn-kpi-val'>{escape(o)}</p></div>",
        unsafe_allow_html=True,
    )
    m2.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Debit (period)</p>"
        f"<p class='txn-kpi-val'>{escape(fmt_money(period_debit))}</p></div>",
        unsafe_allow_html=True,
    )
    m3.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Credit (period)</p>"
        f"<p class='txn-kpi-val'>{escape(fmt_money(period_credit))}</p></div>",
        unsafe_allow_html=True,
    )
    m4.markdown(
        f"<div class='txn-kpi-card'><p class='txn-kpi'>Closing</p>"
        f"<p class='txn-kpi-val'>{escape(c)}</p></div>",
        unsafe_allow_html=True,
    )


def render_ledger_summary_table(entries):
    """Styled summary ledger (Date / Ref / Description / Dr / Cr / Balance)."""
    from html import escape

    if not entries:
        return
    ths = "".join(
        f"<th>{h}</th>" for h in ("Date", "Ref", "Description", "Debit", "Credit", "Balance")
    )
    body = []
    for e in entries:
        debit = float(e.get("debit") or 0)
        credit = float(e.get("credit") or 0)
        bal = float(e.get("balance") or 0)
        body.append(
            "<tr>"
            f"<td>{escape(str(e.get('date') or ''))}</td>"
            f"<td>{escape(str(e.get('ref') or '—'))}</td>"
            f"<td>{escape(str(e.get('description') or ''))}</td>"
            f"<td class='txn-num'>{escape(fmt_money(debit)) if debit else '—'}</td>"
            f"<td class='txn-num'>{escape(fmt_money(credit)) if credit else '—'}</td>"
            f"<td class='txn-num'>{escape(fmt_signed_dr_cr(bal))}</td>"
            "</tr>"
        )
    st.markdown(
        f'<div class="txn-reg-wrap txn-reg-wrap--ledger"><table class="txn-reg-table">'
        f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
        unsafe_allow_html=True,
    )


def render_ledger_detailed_table(entries):
    """Finance Manager detailed ledger with line qty/rate/amount."""
    from html import escape

    from database import parse_ledger_balance_display

    if not entries:
        return
    headers = ("Date", "Type", "Vr. #", "Narration", "Qty", "Rate", "Amount", "Debit", "Credit", "Balance")
    ths = "".join(f"<th>{h}</th>" for h in headers)
    body = []
    for e in entries:
        qty = e.get("qty")
        rate = e.get("rate")
        amount = e.get("amount")
        debit = float(e.get("debit") or 0)
        credit = float(e.get("credit") or 0)
        bal_raw = e.get("balance")
        if bal_raw in (None, ""):
            bal_txt = "—"
        else:
            bal_txt = fmt_signed_dr_cr(parse_ledger_balance_display(bal_raw))
        qty_txt = f"{float(qty):,.3f}" if qty not in (None, "") else "—"
        rate_txt = fmt_money(rate) if rate not in (None, "") and float(rate or 0) else "—"
        amt_txt = fmt_money(amount) if amount not in (None, "") and float(amount or 0) else "—"
        body.append(
            "<tr>"
            f"<td>{escape(str(e.get('date') or ''))}</td>"
            f"<td>{escape(str(e.get('type') or '—'))}</td>"
            f"<td>{escape(str(e.get('vr_no') or '—'))}</td>"
            f"<td>{escape(str(e.get('narration') or ''))}</td>"
            f"<td class='txn-num'>{qty_txt}</td>"
            f"<td class='txn-num'>{escape(rate_txt)}</td>"
            f"<td class='txn-num'>{escape(amt_txt)}</td>"
            f"<td class='txn-num'>{escape(fmt_money(debit)) if debit else '—'}</td>"
            f"<td class='txn-num'>{escape(fmt_money(credit)) if credit else '—'}</td>"
            f"<td class='txn-num'>{escape(bal_txt)}</td>"
            "</tr>"
        )
    st.markdown(
        f'<div class="txn-reg-wrap txn-reg-wrap--ledger"><table class="txn-reg-table">'
        f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
        unsafe_allow_html=True,
    )


def render_dataframe_html_table(df, *, max_rows: int = 1000):
    """Generic register table from a DataFrame (reports, GL, etc.)."""
    from html import escape
    from erp_ui.invoice_status_ui import status_badge_html

    if df is None or df.empty:
        return
    cols = list(df.columns)
    money_keys = (
        "amount", "debit", "credit", "balance", "total", "value", "price", "cost",
        "qty", "quantity", "rate", "opening", "closing", "sales", "purchase", "profit",
    )
    show = df.head(max_rows)
    ths = "".join(f"<th>{escape(str(c))}</th>" for c in cols)
    body = []
    for _, row in show.iterrows():
        cells = []
        for c in cols:
            val = row[c]
            c_low = str(c).lower()
            if "status" in c_low and val is not None and str(val).strip():
                cells.append(f"<td class='txn-status-cell'>{status_badge_html(str(val))}</td>")
            elif any(k in c_low for k in money_keys):
                try:
                    num = float(val or 0)
                    if "balance" in c_low:
                        txt = fmt_signed_dr_cr(num)
                    elif abs(num) < 0.005:
                        txt = "—"
                    elif "qty" in c_low or "quantity" in c_low:
                        txt = f"{num:,.3f}"
                    else:
                        txt = fmt_money(num)
                except (TypeError, ValueError):
                    txt = str(val if val is not None else "—")
                cells.append(f"<td class='txn-num'>{escape(txt)}</td>")
            else:
                cells.append(f"<td>{escape(str(val if val is not None else '—'))}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    st.markdown(
        f'<div class="txn-reg-wrap"><table class="txn-reg-table">'
        f"<thead><tr>{ths}</tr></thead><tbody>{''.join(body)}</tbody></table></div>",
        unsafe_allow_html=True,
    )
    if len(df) > max_rows:
        st.caption(f"Showing first **{max_rows:,}** of **{len(df):,}** rows.")


def customer_select(key="cust"):
    rows = db.get_customers()
    _, cid, _ = smart_select("Customer", rows, key, "id", lambda r: f"{r['code']} - {r['name']}")
    return cid


def supplier_select(key="sup"):
    rows = db.get_suppliers()
    _, sid, _ = smart_select("Supplier", rows, key, "id", lambda r: f"{r['code']} - {r['name']}")
    return sid


def dual_role_party_caption(linked: dict, *, for_doc: str) -> None:
    """Explain dual-role link: one combined ledger under the same party code."""
    if not linked:
        return
    label = f"**{linked.get('code')} — {linked.get('name')}**"
    if linked.get("created"):
        mirror = "Supplier" if for_doc == "purchase" else "Customer"
        st.success(
            f"Dual-role enabled for {label} (mirrored on {mirror} master). "
            f"Purchases and sales share one **combined ledger** under this code."
        )
    elif linked.get("reactivated"):
        st.info(
            f"Reactivated dual-role link for {label}. "
            f"Ledger stays **combined** (Customer + Supplier, same code)."
        )
    else:
        st.caption(
            f"Dual-role party {label} — invoice posts on the "
            f"{'purchase' if for_doc == 'purchase' else 'sale'} book; "
            f"Customer/Supplier Ledger shows one **combined** statement."
        )


def resolve_purchase_party_id(*, from_customer: bool, key: str = "pur_new_party"):
    """Return supplier_id for a purchase invoice (optionally picked from Customers)."""
    if from_customer:
        st.markdown("**Select Customer** (purchase from customer)")
        _, cust_id, _ = smart_select(
            "Customer", db.get_customers(), f"{key}_cust", "id",
            lambda r: f"{r['code']} - {r['name']}",
        )
        if not cust_id:
            return None
        linked = db.ensure_linked_counterparty("customer", cust_id, created_by=uid())
        dual_role_party_caption(linked, for_doc="purchase")
        return linked["id"]
    st.markdown("**Select Supplier** (or load purchase order above)")
    _, sid, _ = smart_select(
        "Supplier", db.get_suppliers(), f"{key}_sup", "id",
        lambda r: f"{r['code']} - {r['name']}",
    )
    return sid


def resolve_sale_party_id(*, from_supplier: bool, key: str = "sal_new_party"):
    """Return customer_id for a sale invoice (optionally picked from Suppliers)."""
    if from_supplier:
        st.markdown("**Select Supplier** (sell to supplier)")
        _, sid, _ = smart_select(
            "Supplier", db.get_suppliers(), f"{key}_sup", "id",
            lambda r: f"{r['code']} - {r['name']}",
        )
        if not sid:
            return None
        linked = db.ensure_linked_counterparty("supplier", sid, created_by=uid())
        dual_role_party_caption(linked, for_doc="sale")
        return linked["id"]
    st.markdown("**Select Customer** (or load quotation / sales order above)")
    _, cid, _ = smart_select(
        "Customer", db.get_customers(), f"{key}_cust", "id",
        lambda r: f"{r['code']} - {r['name']}",
    )
    return cid


def product_select(key="prod", active_only=True):
    rows = db.get_items(active_only=active_only)
    _, pid, row = smart_select(
        "Product", rows, key, "id",
        lambda r: f"{r['code']} - {r['name']} ({r.get('stock_qty', 0)} {r.get('unit', '')})",
    )
    return pid, row


def account_select(key="acc"):
    rows = db.get_accounts()
    _, aid, _ = smart_select("Account", rows, key, "id", lambda r: f"{r['code']} - {r['name']}")
    return aid


def employee_select(key="emp"):
    rows = db.get_employees_hr() if hasattr(db, "get_employees_hr") else db.get_employees()
    _, eid, _ = smart_select("Employee", rows, key, "id", lambda r: f"{r['code']} - {r['full_name']}")
    return eid


def warehouse_select(key="wh"):
    rows = db.get_warehouses()
    _, wid, _ = smart_select("Warehouse", rows, key, "id", lambda r: f"{r['code']} - {r['name']}")
    return wid


def customer_opts(active_only=True):
    return {f"{r['code']} - {r['name']}": r["id"] for r in db.get_customers(active_only=active_only)}


def supplier_opts(active_only=True):
    return {f"{r['code']} - {r['name']}": r["id"] for r in db.get_suppliers(active_only=active_only)}


def product_opts(active_only=True):
    rows = sorted(
        db.get_items(active_only=active_only),
        key=lambda r: natural_code_sort_key(r.get("code")),
    )
    return {f"{r['code']} - {r['name']} ({r.get('stock_qty',0)} {r.get('unit','')})": r for r in rows}


def account_opts(active_only=True):
    return {f"{r['code']} - {r['name']}": r["id"] for r in db.get_accounts(active_only=active_only)}


def tax_opts():
    return {f"{r['code']} - {r['name']} ({r.get('sales_tax_pct',0)}%)": r for r in db.get_tax_rates()}


def warehouse_opts():
    return {f"{r['code']} - {r['name']}": r["id"] for r in db.get_warehouses()}


def apply_last_invoice_discounts_button(
    *,
    key_prefix: str,
    party_id,
    party_kind: str = "sale",
    lines_key: str | None = None,
    disc_key_suffix: str = "d",
) -> None:
    """
    Opt-in control: apply Disc % from this party's last invoices (header + per item).
    Does nothing unless the user clicks the button.
    """
    if not party_id:
        return
    lines_key = lines_key or f"{key_prefix}_lines"
    btn_key = f"{key_prefix}_apply_last_disc"
    c1, c2 = st.columns([2, 3])
    clicked = c1.button(
        "Apply discounts from last invoices",
        key=btn_key,
        help=(
            "Fills header Disc % and each line Disc % from this customer/supplier's "
            "last approved invoices. Only runs when you press this button."
        ),
        use_container_width=True,
    )
    c2.caption("Discounts stay **0** unless you type them or press this button.")
    if not clicked:
        return

    from product_rates_legacy import lookup_discounts_from_last_invoices

    kind = "purchase" if (party_kind or "").lower().startswith("purch") else "sale"
    lines = list(st.session_state.get(lines_key) or [])
    pids = [
        int(ln.get("item_id") or ln.get("product_id") or 0)
        for ln in lines
        if (ln.get("item_id") or ln.get("product_id"))
    ]
    found = lookup_discounts_from_last_invoices(int(party_id), pids, kind=kind)
    header_pct = float(found.get("header_pct") or 0)
    by_prod = found.get("by_product") or {}

    st.session_state[f"{key_prefix}_disc_pct"] = header_pct

    applied = 0
    new_lines = []
    for i, ln in enumerate(lines):
        row = dict(ln)
        pid = int(row.get("item_id") or row.get("product_id") or 0)
        if pid:
            disc = float(by_prod.get(pid, header_pct) or 0)
            row["discount_pct"] = disc
            row["_disc_locked"] = True
            if disc > 0.0001:
                applied += 1
        # Force Disc % widgets to pick up new values on next render
        for k in (
            f"{key_prefix}_{disc_key_suffix}_{i}",
            f"{key_prefix}_psig_{i}",
        ):
            st.session_state.pop(k, None)
        if pid:
            st.session_state[f"{key_prefix}_{disc_key_suffix}_{i}"] = float(
                row.get("discount_pct") or 0
            )
        new_lines.append(row)

    st.session_state[lines_key] = new_lines
    if applied or header_pct > 0:
        st.success(
            f"Applied last-invoice discounts"
            + (f" (header {header_pct:.2f}%)" if header_pct > 0 else "")
            + (f" on {applied} line(s)." if applied else ".")
        )
    else:
        st.info("No discounts found on last approved invoices for this party / items.")
    st.rerun()


def invoice_tax_form(key_prefix, line_items, defaults=None, party_id=None, party_kind=None):
    """Tax, discount, charges — V13.13 sales/purchase tax summary."""
    defaults = defaults or {}
    tax_map = tax_opts()
    default_disc = float(defaults.get("discount_pct", 0) or 0)
    # Do not auto-fill Disc % from last invoice — user must enter discount intentionally.
    c1, c2, c3 = st.columns(3)
    discount_pct = c1.number_input(
        "Discount % (header default)",
        min_value=0.0, max_value=100.0,
        value=float(default_disc),
        key=f"{key_prefix}_disc_pct",
        help="Optional. Applies to lines with Disc % left at 0. Use **Apply discounts from last invoices** above to fill from history.",
    )
    tax_inclusive = c2.checkbox("Tax Inclusive Pricing", value=bool(defaults.get("tax_inclusive", False)),
                                key=f"{key_prefix}_tax_inc")
    tax_labels = list(tax_map.keys()) if tax_map else []
    default_tax = defaults.get("tax_rate_id") or db.default_tax_rate_id()
    tax_idx = 0
    if default_tax and tax_map:
        for i, (_, tr) in enumerate(tax_map.items()):
            if tr["id"] == default_tax:
                tax_idx = i
                break
    tax_lbl = c3.selectbox("Tax Category", tax_labels or ["—"], index=min(tax_idx, max(len(tax_labels) - 1, 0)),
                           key=f"{key_prefix}_tax_cat") if tax_labels else None
    tax_rate_id = tax_map[tax_lbl]["id"] if tax_lbl and tax_lbl in tax_map else defaults.get("tax_rate_id")
    tax_pct = float(tax_map[tax_lbl].get("sales_tax_pct", 0)) if tax_lbl and tax_lbl in tax_map else float(defaults.get("tax_pct", 18))

    ch1, ch2, ch3, ch4 = st.columns(4)
    with ch1:
        freight = money_input(
            "Freight", value=float(defaults.get("freight", 0)), key=f"{key_prefix}_freight", min_value=0.0,
        )
    with ch2:
        loading = money_input(
            "Loading", value=float(defaults.get("loading_charges", 0)), key=f"{key_prefix}_load", min_value=0.0,
        )
    with ch3:
        other = money_input(
            "Other Charges", value=float(defaults.get("other_charges", 0)), key=f"{key_prefix}_other", min_value=0.0,
        )
    with ch4:
        round_off = money_input(
            "Round Off", value=float(defaults.get("round_off", 0)), key=f"{key_prefix}_round",
        )

    hdr = {
        "discount_pct": discount_pct,
        "tax_inclusive": tax_inclusive,
        "tax_rate_id": tax_rate_id,
        "tax_pct": tax_pct,
        "freight": freight,
        "loading_charges": loading,
        "other_charges": other,
        "round_off": round_off,
    }
    # Line Disc % > 0 overrides header; 0/missing uses header default.
    calc_lines = []
    for li in line_items:
        row = dict(li)
        if float(row.get("discount_pct") or 0) <= 0:
            row.pop("discount_pct", None)
        calc_lines.append(row)
    totals = db.compute_invoice_totals(calc_lines, hdr)
    charges = float(freight) + float(loading) + float(other) + float(round_off)
    net_with_charges = float(totals.get("total") or 0) + charges
    totals["freight"] = freight
    totals["loading_charges"] = loading
    totals["other_charges"] = other
    totals["round_off"] = round_off
    totals["total"] = net_with_charges
    st.markdown("**Invoice Tax Summary**")
    s1, s2, s3, s4 = st.columns(4)
    s1.metric("Subtotal", fmt_money(totals["subtotal"]))
    s2.metric("Discount", fmt_money(totals["discount_amt"]))
    s3.metric("Taxable", fmt_money(totals["taxable"]))
    s4.metric("Net Invoice", fmt_money(totals["total"]))
    t1, t2, t3, t4, t5 = st.columns(5)
    t1.metric("Sales Tax", fmt_money(totals["sales_tax"]))
    t2.metric("Further Tax", fmt_money(totals["further_tax"]))
    t3.metric("Extra Tax", fmt_money(totals["extra_tax"]))
    t4.metric("WHT", fmt_money(totals["wht_tax"]))
    t5.metric("FED", fmt_money(totals.get("fed_tax", 0)))
    hdr.update(totals)
    return hdr, totals


def invoice_material_lines_table(invoice_kind, invoice_id, key_prefix="inv_mat", line_prompt="Gate pass covers"):
    """Show invoice line items in a table (like sales invoice) for gate pass / weighbridge."""
    from db_commercial import get_invoice_line_items, summarize_invoice_lines, INVOICE_LINE_ALL, invoice_line_material_pick

    items = get_invoice_line_items(invoice_kind, invoice_id)
    if not items:
        st.warning("This invoice has no line items.")
        return None

    inv_key = f"{key_prefix}_inv_id"
    if st.session_state.get(inv_key) != invoice_id:
        st.session_state[inv_key] = invoice_id
        st.session_state.pop(f"{key_prefix}_pick", None)

    st.markdown("**Materials (same rows as invoice)**")
    df = pd.DataFrame(items)
    view = df[[c for c in ("item_code", "item_name", "quantity", "net_weight") if c in df.columns]].copy()
    if "quantity" in view.columns and "net_weight" in view.columns:
        q = view["quantity"].astype(float)
        nw = view["net_weight"].astype(float)
        view.insert(
            3, "unit_weight",
            [round(n / q, 4) if q > 0 and n > 0 else 0.0 for q, n in zip(q, nw)],
        )
        view.columns = ["Code", "Product", "Qty", "Unit Wt (kg)", "Net Wt (kg)"]
    else:
        view.columns = ["Code", "Product", "Qty", "Net Wt (kg)"][: len(view.columns)]
    render_dataframe_html_table(view)
    summary = summarize_invoice_lines(items)
    m1, m2 = st.columns(2)
    m1.metric("Total Qty", f"{summary['quantity']:,.2f}")
    m2.metric("Total Weight (kg)", f"{summary['net_weight']:,.3f}")

    opts = {f"(All {len(items)} lines on bill)": INVOICE_LINE_ALL}
    for i, ln in enumerate(items):
        code = ln.get("item_code") or "—"
        label = f"Line {i + 1}: {code} — {ln['item_name']} | Qty {ln['quantity']:,.2f}"
        opts[label] = str(i)
    labels = list(opts.keys())
    pick_key = f"{key_prefix}_pick"
    if pick_key not in st.session_state:
        st.session_state[pick_key] = labels[0]
    sel = st.selectbox(line_prompt, labels, key=pick_key)
    pick = opts[sel]
    mat = invoice_line_material_pick(items, pick)
    mat["pick"] = pick
    return mat


def invoice_bill_material_select(
    invoice_kind, invoice_id, key_prefix="inv_mat", default_pick=None, line_prompt=None,
):
    """
    Pick material from invoice bill lines or all lines combined.
    Returns dict: product_id, quantity, material_desc, net_weight, pick
    """
    from db_commercial import get_invoice_line_items, INVOICE_LINE_ALL

    items = get_invoice_line_items(invoice_kind, invoice_id)
    if not items:
        st.warning("This invoice has no line items.")
        return None
    pick_key = f"{key_prefix}_pick"
    if default_pick is not None and pick_key not in st.session_state:
        if default_pick == INVOICE_LINE_ALL:
            st.session_state[pick_key] = f"(All {len(items)} lines on bill)"
    prompt = line_prompt or "Gate pass covers"
    return invoice_material_lines_table(invoice_kind, invoice_id, key_prefix, line_prompt=prompt)


WEIGHT_SLIP_PLACEHOLDER = "— Select weight slip —"


def slip_party_display(slip) -> str:
    """Party account for weight-slip labels (code + name)."""
    if not slip:
        return "—"
    name = (slip.get("customer_name") or slip.get("supplier_name") or "").strip()
    code = (slip.get("customer_code") or slip.get("supplier_code") or "").strip()
    try:
        from db_invoice_workflow import UNKNOWN_PARTY_CODE, slip_party_is_unknown
        if name and name.upper() not in (UNKNOWN_PARTY_CODE, "UNKNOWN PARTY"):
            return f"{code} - {name}" if code else name
        if slip_party_is_unknown(slip) or not name:
            return "UNKNOWN — assign at 2nd weight"
        return (f"{code} - {name}" if code else name) or "—"
    except Exception:
        return (f"{code} - {name}" if code and name else name) or "—"


def weight_slip_option_label(r, *, role: str | None = None, primary_lbl: str = "") -> str:
    """Consistent slip dropdown text: Slip — Party — Vehicle — kg."""
    party = slip_party_display(r)
    net = float(r.get("net_weight") or r.get("first_weight") or 0)
    veh = (r.get("vehicle_no") or "—").strip() or "—"
    prefix = f"[{role}] " if role else ""
    return (
        f"{prefix}{r.get('document_no') or '—'} — {party} — {veh} — "
        f"{net:,.3f} kg{primary_lbl}"
    )


def weight_slip_select(
    key_prefix="ws",
    party_type=None,
    current_slip_id=None,
    customer_id=None,
    supplier_id=None,
    required=True,
    current_invoice_id=None,
):
    """
    Pick completed weight slip for invoice.

    Returns (slip_id, as_primary):
    - as_primary=True  -> this invoice owns full slip weight / variance
    - as_primary=False -> reference-only (slip already on another invoice)
    """
    from db_commercial import (
        get_unlinked_slips_for_party, get_referenceable_slips,
        weight_slip_is_linked, weight_slip_is_imported, get_weight_slip_invoice_attachment,
    )

    party_id = customer_id if party_type == "customer" else supplier_id if party_type == "supplier" else None
    ref_key = f"{key_prefix}_ws_ref_only"
    # When editing: if this slip's primary is another invoice, default to Reference only
    if current_slip_id and current_invoice_id and ref_key not in st.session_state:
        try:
            att = get_weight_slip_invoice_attachment(current_slip_id)
            if att and int(att.get("id") or 0) != int(current_invoice_id):
                st.session_state[ref_key] = True
        except Exception:
            pass

    ref_only = st.checkbox(
        "Reference only — share an existing slip (no weight split / variance)",
        key=ref_key,
        help=(
            "Primary invoice keeps the full weighbridge net weight. "
            "Other invoices on the same vehicle only show the slip number."
        ),
    )

    if ref_only:
        available = get_referenceable_slips(
            party_type, party_id, include_slip_id=current_slip_id,
        )
    elif party_type in ("customer", "supplier") and party_id:
        available = get_unlinked_slips_for_party(
            party_type, party_id, include_slip_id=current_slip_id,
        )
    else:
        rows = db.get_weight_slips_pro()
        available = [
            r for r in rows
            if r.get("status") == "completed" and float(r.get("net_weight") or 0) > 0
            and (not weight_slip_is_linked(r) or r["id"] == current_slip_id)
            and (r["id"] == current_slip_id or not weight_slip_is_imported(r))
        ]
        if party_type == "customer":
            available = [r for r in available if r.get("customer_id")]
        elif party_type == "supplier":
            available = [r for r in available if r.get("supplier_id")]

    if not available:
        if required:
            if ref_only:
                st.error(
                    "No slips already linked to another invoice. "
                    "Create the **primary** invoice on the slip first, then attach here as reference."
                )
            else:
                st.error(
                    "No completed weight slip for this party from the **current weighbridge**. "
                    "Record **1st weight** and **2nd weight** on **Weight Scale** first. "
                    "Or tick **Reference only** to share a slip already used on another invoice."
                )
        else:
            st.caption("No current weighbridge slips available for linking.")
        return None, not ref_only

    slip_opts = {}
    for r in available:
        primary = get_weight_slip_invoice_attachment(r["id"]) if ref_only else None
        primary_lbl = f" · primary {primary.get('invoice_no')}" if primary else ""
        role = "REF" if ref_only else "PRIMARY"
        slip_opts[weight_slip_option_label(r, role=role, primary_lbl=primary_lbl)] = r["id"]

    party_key = customer_id or supplier_id or "all"
    mode_key = "ref" if ref_only else "pri"
    sel_key = f"{key_prefix}_wssel_{mode_key}_{party_key}"

    if required:
        opts = {WEIGHT_SLIP_PLACEHOLDER: None, **slip_opts}
        labels = list(opts.keys())
        default_lbl = WEIGHT_SLIP_PLACEHOLDER
        if current_slip_id:
            default_lbl = next(
                (k for k, v in slip_opts.items() if v == current_slip_id),
                WEIGHT_SLIP_PLACEHOLDER,
            )
        st.caption(
            "**Reference-only** — pick a slip already used as primary on another invoice."
            if ref_only else
            "Weight slip is **required** — select an **unused** weighbridge slip "
            "(or tick Reference only to share one)."
        )
        idx = labels.index(default_lbl) if default_lbl in labels else 0
        sel = st.selectbox("Weight Slip *", labels, index=idx, key=sel_key)
        ws_id = opts[sel]
    else:
        opts_none = {"(None)": None, **slip_opts}
        labels_n = list(opts_none.keys())
        sel = st.selectbox("Weight Slip (optional)", labels_n, key=sel_key)
        ws_id = opts_none[sel]

    as_primary = not ref_only
    if ws_id:
        slip = next(r for r in available if r["id"] == ws_id)
        party_nm = slip_party_display(slip)
        if ref_only:
            st.info(
                f"Reference slip **{slip['document_no']}** — Party **{party_nm}** — "
                f"Vehicle **{slip.get('vehicle_no') or '—'}** | "
                f"Net **{float(slip.get('net_weight') or 0):,.3f} kg** stays on the **primary** invoice. "
                "This invoice only stores the slip number (no variance check)."
            )
        else:
            st.caption(
                f"Slip **{slip['document_no']}** — Party **{party_nm}** — "
                f"Vehicle **{slip.get('vehicle_no') or '—'}** | "
                f"Net **{float(slip.get('net_weight') or 0):,.3f} kg** (linked as **primary** when you save)."
            )
    elif required:
        st.warning("Select a weight slip before saving this invoice.")
    return ws_id, as_primary



def apply_weight_slip_to_invoice_lines(lines, slip_id, single_line_net=True):
    """Pre-fill item / net weight from completed slip when creating invoice after weighbridge."""
    if not slip_id or not lines:
        return lines
    slip = db.get_weight_slip_pro(slip_id)
    if not slip or slip.get("status") != "completed":
        return lines
    net = float(slip.get("net_weight") or 0)
    pid = slip.get("product_id")
    out = [dict(ln) for ln in lines]
    if len(out) == 1:
        if pid and not out[0].get("item_id"):
            out[0]["item_id"] = pid
        if single_line_net and net > 0 and not float(out[0].get("net_weight") or 0):
            out[0]["net_weight"] = net
    return out


def sales_order_dispatch_to(order: dict | None) -> str:
    """Resolved dispatch destination for picker labels (town field, notes, or customer city)."""
    o = order or {}
    town = (o.get("dispatch_town") or "").strip()
    if town:
        return town
    cached = (o.get("dispatch_to") or "").strip()
    if cached and cached != "-":
        return cached
    try:
        from erp_core.dispatch_planning import resolve_dispatch_to
        dest = resolve_dispatch_to(o.get("notes"), o.get("customer_city"))
        if dest and dest != "-":
            return dest
    except Exception:
        pass
    return ""


def _picker_status_suffix(status) -> str:
    try:
        from erp_ui.invoice_status_ui import status_label
        return status_label(status or "open")
    except Exception:
        raw = str(status or "open").strip().lower()
        return {"open": "Active", "partial": "Partial"}.get(
            raw, raw.replace("_", " ").title() or "—"
        )


def document_party_picker_label(
    row: dict,
    *,
    doc_key: str = "document_no",
    party_key: str = "customer_name",
    status_key: str = "status",
    date_key: str | None = None,
) -> str:
    """Search/picker label: doc — party [Status] (optional date)."""
    r = row or {}
    doc = r.get(doc_key) or r.get("invoice_no") or r.get("return_no") or "—"
    party = (
        r.get(party_key)
        or r.get("customer_name")
        or r.get("supplier_name")
        or ""
    )
    status = _picker_status_suffix(r.get(status_key))
    label = f"{doc} — {party} [{status}]"
    if date_key and r.get(date_key):
        label += f" ({str(r.get(date_key))[:10]})"
    return label


def purchase_order_picker_label(
    order: dict,
    *,
    show_total: bool = True,
    show_pending: bool = False,
) -> str:
    """Dropdown label: PO — supplier [Status] — pending / amount."""
    o = order or {}
    doc = o.get("document_no") or "PO"
    sup = o.get("supplier_name") or ""
    status = _picker_status_suffix(o.get("status") or "open")
    parts = [f"{doc} — {sup} [{status}]"]
    if show_pending:
        parts.append(f"pending {float(o.get('pending_qty') or 0):,.0f} units")
    if show_total:
        parts.append(f"Rs. {float(o.get('total') or 0):,.0f}")
    return " — ".join(p for p in parts if p)


def order_fulfillment_breakdown_df(
    items,
    *,
    ordered_key: str = "quantity",
    done_key: str = "delivered_qty",
    done_label: str = "Delivered",
):
    """Line-level ordered / done / pending qty for order edit screens."""
    import pandas as pd

    rows = []
    for it in items or []:
        ordered = float(it.get("ordered_qty") or it.get(ordered_key) or 0)
        done = float(it.get(done_key) or 0)
        pending = round(max(ordered - done, 0), 3)
        code = (it.get("product_code") or "").strip()
        name = it.get("product_name") or it.get("item_name") or ""
        rows.append({
            "Item": f"{code} — {name}" if code else name,
            "Ordered": ordered,
            done_label: done,
            "Pending": pending,
        })
    return pd.DataFrame(rows)


def sales_order_picker_label(
    order: dict,
    *,
    show_total: bool = True,
    show_pending: bool = False,
) -> str:
    """Dropdown label: SO — customer [Status] — stop / pending / amount."""
    o = order or {}
    doc = o.get("document_no") or "SO"
    cust = o.get("customer_name") or ""
    status = _picker_status_suffix(o.get("status") or "open")
    parts = [f"{doc} — {cust} [{status}]"]
    dest = sales_order_dispatch_to(o)
    if dest:
        parts.append(f"Stop: {dest}")
    if show_pending:
        parts.append(f"pending {float(o.get('pending_qty') or 0):,.0f} units")
    if show_total:
        parts.append(f"Rs. {float(o.get('total') or 0):,.0f}")
    return " — ".join(p for p in parts if p)


def prime_sale_from_order(order_id, key_prefix="sal"):
    """Load sales invoice session state from a sales order."""
    from datetime import date
    order = db.get_sales_order(order_id)
    if not order:
        raise ValueError("Sales order not found.")
    lines = db.sales_order_invoice_lines(order_id)
    if not lines:
        raise ValueError("All items on this order are already invoiced.")
    tax_rates = db.get_tax_rates()
    default_tax = order.get("tax_rate_id") or (db.default_tax_rate_id())
    st.session_state[f"{key_prefix}_header"] = {
        "invoice_no": db.peek_invoice("SAL", "sales_invoices"),
        "customer_id": order["customer_id"],
        "sale_date": str(date.today()),
        "payment_mode": "credit",
        "paid_amount": 0,
        "notes": f"From sales order {order['document_no']}",
        "tax_rate_id": default_tax,
        "discount_pct": 0,
        "order_id": order_id,
        "weighbridge_required": 1,
    }
    st.session_state[f"{key_prefix}_lines"] = lines
    st.session_state[f"{key_prefix}_order_id"] = order_id
    return order


def prime_sales_order_from_quotation(quotation_id, key_prefix="SO"):
    """Load sales order session state from a quotation."""
    from datetime import date
    lines, quote = db.quotation_to_lines(quotation_id)
    if not lines:
        raise ValueError("Quotation has no lines.")
    tax_rates = db.get_tax_rates()
    default_tax = quote.get("tax_rate_id") or (db.default_tax_rate_id())
    st.session_state[f"{key_prefix}_hdr"] = {
        "document_no": db.peek_document("SO"),
        "party_id": quote["customer_id"],
        "date": str(date.today()),
        "notes": f"From quotation {quote['document_no']}",
        "discount_pct": 0,
        "tax_rate_id": default_tax,
        "quotation_id": quotation_id,
    }
    st.session_state[f"{key_prefix}_lines"] = [
        {"product_id": l["product_id"], "quantity": l["quantity"], "rate": l["rate"], "amount": l["amount"],
         "net_weight": l.get("net_weight", 0)}
        for l in lines
    ]
    st.session_state[f"{key_prefix}_quotation_id"] = quotation_id
    return quote


def prime_purchase_from_order(order_id, key_prefix="pur"):
    """Load purchase invoice session state from a purchase order."""
    from datetime import date
    order = db.get_purchase_order(order_id)
    if not order:
        raise ValueError("Purchase order not found.")
    lines = db.purchase_order_invoice_lines(order_id)
    if not lines:
        raise ValueError("All items on this order are already received/invoiced.")
    tax_rates = db.get_tax_rates()
    default_tax = order.get("tax_rate_id") or (db.default_tax_rate_id())
    st.session_state[f"{key_prefix}_header"] = {
        "invoice_no": db.peek_invoice("PUR", "purchase_invoices"),
        "supplier_id": order["supplier_id"],
        "purchase_date": str(date.today()),
        "payment_mode": "credit",
        "paid_amount": 0,
        "notes": f"From purchase order {order['document_no']}",
        "tax_rate_id": default_tax,
        "discount_pct": 0,
        "order_id": order_id,
        "weighbridge_required": 1,
    }
    st.session_state[f"{key_prefix}_lines"] = lines
    st.session_state[f"{key_prefix}_order_id"] = order_id
    return order


def prime_purchase_order_from_requisition(requisition_id, key_prefix="PO"):
    """Load purchase order session from a requisition."""
    from datetime import date
    lines, req = db.requisition_to_po_lines(requisition_id)
    if not lines:
        raise ValueError("Requisition has no lines.")
    st.session_state[f"{key_prefix}_hdr"] = {
        "document_no": db.peek_document("PO"),
        "party_id": None,
        "date": str(date.today()),
        "notes": f"From requisition {req['document_no']}",
        "discount_pct": 0,
        "tax_rate_id": db.get_tax_rates()[0]["id"] if db.get_tax_rates() else None,
        "requisition_id": requisition_id,
    }
    st.session_state[f"{key_prefix}_lines"] = [
        {"product_id": l["product_id"], "quantity": l["quantity"], "rate": l["rate"], "amount": l["amount"],
         "net_weight": l.get("net_weight", 0)}
        for l in lines
    ]
    st.session_state[f"{key_prefix}_requisition_id"] = requisition_id
    return req


def return_lines_from_invoice(invoice_id, kind="sale"):
    """Build return line dicts from a linked sales/purchase invoice."""
    if kind == "sale":
        inv = db.get_sale(invoice_id)
    else:
        inv = db.get_purchase(invoice_id)
    if not inv:
        raise ValueError("Invoice not found.")
    lines = []
    for li in inv.get("items") or []:
        lines.append({
            "item_id": li["item_id"],
            "quantity": float(li["quantity"]),
            "rate": float(li["rate"]),
            "amount": float(li["amount"]),
            "net_weight": float(li.get("net_weight") or 0),
            "discount_pct": float(li.get("discount_pct") or 0),
            "line_discount": float(li.get("line_discount") or 0),
        })
    return lines, inv


def sale_invoice_flow_flags(no_weighbridge=False, retail=False):
    """Sales UI: no weighbridge (qty invoice) vs retail (cash + no weighbridge)."""
    no_wb = bool(no_weighbridge or retail)
    return {
        "no_weighbridge": no_wb,
        "retail": bool(retail),
        "weighbridge_required": 0 if no_wb else 1,
        "show_weight": not no_wb,
        "default_payment_mode": "cash" if retail else "credit",
    }


def sale_dispatch_fields_ui(key_prefix, header=None):
    """Optional driver / vehicle / remarks for invoices without weighbridge."""
    h = header or {}
    st.markdown("**Dispatch / transport** (optional — printed on gate pass)")
    c1, c2 = st.columns(2)
    vehicle = c1.text_input(
        "Vehicle Number",
        value=h.get("vehicle_no") or "",
        key=f"{key_prefix}_vehicle_no",
        placeholder="e.g. LES-1234",
    )
    driver = c2.text_input(
        "Driver Name",
        value=h.get("driver_name") or "",
        key=f"{key_prefix}_driver_name",
    )
    c3, c4 = st.columns(2)
    contact = c3.text_input(
        "Driver Contact Number",
        value=h.get("driver_contact") or "",
        key=f"{key_prefix}_driver_contact",
        placeholder="03XX-XXXXXXX",
    )
    remarks = c4.text_input(
        "Remarks",
        value=h.get("dispatch_remarks") or "",
        key=f"{key_prefix}_dispatch_remarks",
        placeholder="Any dispatch note…",
    )
    return {
        "vehicle_no": (vehicle or "").strip() or None,
        "driver_name": (driver or "").strip() or None,
        "driver_contact": (contact or "").strip() or None,
        "dispatch_remarks": (remarks or "").strip() or None,
    }


def prime_sale_from_quotation(
    quotation_id, key_prefix="sal", no_weighbridge=False, retail=False,
):
    """Load sales invoice session state from a quotation (direct invoice, no sales order)."""
    from datetime import date
    flags = sale_invoice_flow_flags(no_weighbridge, retail)
    lines, quote = db.quotation_to_lines(quotation_id)
    if not lines:
        raise ValueError("Quotation has no lines.")
    default_tax = quote.get("tax_rate_id") or (db.default_tax_rate_id())
    st.session_state[f"{key_prefix}_header"] = {
        "invoice_no": db.peek_invoice("SAL", "sales_invoices"),
        "customer_id": quote["customer_id"],
        "sale_date": str(date.today()),
        "payment_mode": flags["default_payment_mode"],
        "paid_amount": 0,
        "notes": f"From quotation {quote['document_no']}",
        "tax_rate_id": default_tax,
        "discount_pct": 0,
        "quotation_id": quotation_id,
        "weighbridge_required": flags["weighbridge_required"],
    }
    st.session_state[f"{key_prefix}_lines"] = lines
    st.session_state[f"{key_prefix}_quotation_id"] = quotation_id
    st.session_state[f"{key_prefix}_no_wb"] = flags["no_weighbridge"]
    st.session_state[f"{key_prefix}_retail"] = flags["retail"]
    return quote


def show_weight_variance(invoice_weight, slip_id, as_primary=True):
    if not slip_id or invoice_weight <= 0:
        return
    if not as_primary:
        slip = db.get_weight_slip_pro(slip_id)
        st.caption(
            f"Reference slip **{(slip or {}).get('document_no') or slip_id}** — "
            "variance not calculated (primary invoice holds full weighbridge weight)."
        )
        return
    slip = db.get_weight_slip_pro(slip_id)
    if not slip:
        return
    phys = float(slip.get("net_weight") or 0)
    var = round(phys - invoice_weight, 3)
    base = invoice_weight if invoice_weight > 0 else (phys if phys > 0 else 1)
    var_pct = round(abs(var) / base * 100, 2)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Invoice Weight (kg)", f"{invoice_weight:,.3f}")
    c2.metric("Physical Weight (kg)", f"{phys:,.3f}")
    c3.metric("Variance (kg)", f"{var:+,.3f}")
    c4.metric("Variance (%)", f"{var_pct:.2f}%")


def export_buttons(df, filename="report", title="Export"):
    from erp_ui.report_print import report_toolbar
    report_toolbar(df, title or filename.replace("_", " ").title(), filename, key_prefix=f"exp_{filename}")


MIN_LINE_ROWS = 5
LINE_PRODUCT_PLACEHOLDER = "— Select any product —"


def _blank_line_item():
    return {
        "item_id": None, "product_id": None,
        "quantity": 0.0, "rate": 0.0, "amount": 0.0, "net_weight": 0.0,
        "discount_pct": 0.0,
    }


def _line_discount_pct(line) -> float:
    """Resolve line discount % from stored fields only (do not invent from amount gaps)."""
    qty = float((line or {}).get("quantity") or 0)
    rate = float((line or {}).get("rate") or 0)
    disc_amt = float((line or {}).get("line_discount") or 0)
    if line is not None and line.get("discount_pct") is not None and line.get("discount_pct") != "":
        try:
            return max(0.0, min(100.0, float(line.get("discount_pct") or 0)))
        except (TypeError, ValueError):
            pass
    # Explicit discount amount only — never reverse-engineer % from amount < qty*rate
    gross = qty * rate
    if gross > 0.0001 and disc_amt > 0.0001:
        return round(min(100.0, max(0.0, disc_amt / gross * 100.0)), 4)
    return 0.0


def _line_amount_after_discount(qty, rate, discount_pct) -> float:
    gross = float(qty or 0) * float(rate or 0)
    disc = max(0.0, min(100.0, float(discount_pct or 0)))
    return round(gross * (1 - disc / 100), 2)


def _pad_line_rows(lines, min_rows=MIN_LINE_ROWS):
    """Ensure at least min_rows for tabular entry (empty rows for new lines)."""
    rows = [dict(ln) for ln in (lines or []) if ln is not None]
    if not rows:
        rows = [_blank_line_item()]
    while len(rows) < min_rows:
        rows.append(dict(_blank_line_item()))
    return rows


def _init_line_items_session(sk, default_lines=None):
    if sk not in st.session_state:
        st.session_state[sk] = _pad_line_rows(default_lines)
    elif len(st.session_state[sk]) < MIN_LINE_ROWS:
        st.session_state[sk] = _pad_line_rows(st.session_state[sk])


def _line_item_col_widths(show_weight):
    # Product … Amount | Prev Rate | ✕
    if show_weight:
        return [2.85, 0.6, 0.65, 0.7, 0.65, 0.5, 0.65, 0.95, 0.3]
    return [3.1, 0.7, 0.7, 0.55, 0.7, 1.0, 0.3]


_LINE_ITEM_NUM_COLS = frozenset({
    "Qty", "Rate", "Disc %", "Amount", "Prev Rate", "Net Wt (kg)", "Unit Wt (kg)",
})


def _line_items_table_header(show_weight):
    """Header row — same st.columns ratios as data rows (HTML table caused misalignment)."""
    from html import escape

    widths = _line_item_col_widths(show_weight)
    if show_weight:
        cols_hdr = [
            "Product", "Qty", "Net Wt (kg)", "Unit Wt (kg)",
            "Rate", "Disc %", "Amount", "Prev Rate", "",
        ]
    else:
        cols_hdr = ["Product", "Qty", "Rate", "Disc %", "Amount", "Prev Rate", ""]
    cols = st.columns(widths, gap="small")
    for label, col in zip(cols_hdr, cols):
        if not label:
            col.markdown(
                '<div class="txn-line-hdr-cell txn-line-act">&nbsp;</div>',
                unsafe_allow_html=True,
            )
            continue
        num_cls = " txn-line-hdr-num" if label in _LINE_ITEM_NUM_COLS else ""
        col.markdown(
            f'<div class="txn-line-hdr-cell{num_cls}">{escape(label)}</div>',
            unsafe_allow_html=True,
        )


def _format_party_last_rate_suffix(product, key_prefix: str, party_id=None) -> str:
    """Legacy suffix for product labels (kept for callers; line grid uses Prev Rate column)."""
    if not product or not party_id:
        return ""
    try:
        from product_rates_legacy import get_last_party_rate_info
        info = get_last_party_rate_info(
            product, kind=_rate_kind_from_prefix(key_prefix), party_id=party_id,
        )
    except Exception:
        return ""
    if not info or float(info.get("rate") or 0) <= 0:
        return ""
    rate = float(info["rate"])
    dt = (info.get("date") or "").strip()
    if dt:
        return f" — last {_fmt_rate(rate, key_prefix)} on {dt}"
    return f" — last {_fmt_rate(rate, key_prefix)}"


def _get_party_last_rate_info(product, key_prefix: str, party_id=None):
    if not product or not party_id:
        return None
    try:
        from product_rates_legacy import get_last_party_rate_info
        info = get_last_party_rate_info(
            product, kind=_rate_kind_from_prefix(key_prefix), party_id=party_id,
        )
    except Exception:
        return None
    if not info or float(info.get("rate") or 0) <= 0:
        return None
    return info


def _product_option_labels(items_dict, key_prefix: str, party_id=None):
    """
    Selectbox labels (product code — name), always in product-code sequence.
    Returns (display_labels, display_to_key) where key is original items_dict key.
    """
    labels = [LINE_PRODUCT_PLACEHOLDER]
    display_to_key = {LINE_PRODUCT_PLACEHOLDER: LINE_PRODUCT_PLACEHOLDER}

    def _code_from_key(key: str) -> str:
        return str(key or "").split(" - ", 1)[0].strip()

    keys = [k for k in (items_dict or {}) if k]
    keys = sorted(keys, key=lambda k: natural_code_sort_key(_code_from_key(k)))
    for key in keys:
        labels.append(key)
        display_to_key[key] = key
    return labels, display_to_key


def _show_party_last_rate_hint(product, key_prefix: str, party_id=None, container=None):
    """Caption under rate (optional); prefer Prev Rate column in line grid."""
    info = _get_party_last_rate_info(product, key_prefix, party_id)
    if not info:
        return
    rate = float(info["rate"])
    dt = (info.get("date") or "").strip()
    doc = (info.get("document_no") or "").strip()
    bits = [f"Last **{_fmt_rate(rate, key_prefix)}**"]
    if dt:
        bits.append(f"on **{dt}**")
    if doc:
        bits.append(f"({doc})")
    text = " ".join(bits)
    target = container if container is not None else st
    target.caption(text)


def _prev_rate_column(cols, col_idx, product, key_prefix: str, party_id=None):
    """Last column before ✕: previous party rate + date for this product."""
    info = _get_party_last_rate_info(product, key_prefix, party_id)
    if not info:
        cols[col_idx].markdown(
            "<span style='color:#999'>—</span>",
            unsafe_allow_html=True,
        )
        return
    rate = float(info["rate"])
    disc = float(info.get("discount_pct") or 0)
    dt = (info.get("date") or "").strip()
    doc = (info.get("document_no") or "").strip()
    rate_txt = f"**{_fmt_rate(rate, key_prefix)}**"
    if disc > 0.0001:
        rate_txt = f"**{_fmt_rate(rate, key_prefix)}** (−{disc:g}%)"
    sub = dt or ""
    if doc:
        sub = f"{sub} · {doc}".strip(" ·")
    if sub:
        cols[col_idx].markdown(
            f"<div class='txn-line-num txn-line-prev'>{rate_txt}  \n"
            f"<span style='font-size:0.72em;color:#666'>{sub}</span></div>",
            unsafe_allow_html=True,
        )
    else:
        cols[col_idx].markdown(f"<div class='txn-line-num txn-line-prev'>{rate_txt}</div>")


def _rate_kind_from_prefix(key_prefix: str) -> str:
    p = (key_prefix or "").lower()
    if p.startswith("pur") or p.startswith("pr"):
        return "purchase"
    return "sale"


def _rate_decimals_from_prefix(key_prefix: str) -> int:
    """Purchase rates need 4 dp for precise supplier invoices; sales stay at 2."""
    return 4 if _rate_kind_from_prefix(key_prefix) == "purchase" else 2


def _fmt_rate(rate, key_prefix: str = "pur") -> str:
    d = _rate_decimals_from_prefix(key_prefix)
    try:
        return f"{float(rate or 0):,.{d}f}"
    except (TypeError, ValueError):
        return f"{0.0:,.{d}f}"


def _line_default_rate(line, product, key_prefix: str, party_id=None) -> float:
    """Rate for invoice line: same-product stored rate, else party last invoice, else master."""
    if not product:
        return 0.0
    line_pid = line.get("item_id") or line.get("product_id") if line else None
    stored = float((line or {}).get("rate") or 0)
    if line_pid == product.get("id") and stored > 0:
        return stored
    try:
        from product_rates_legacy import resolve_product_rate
        rate, _src = resolve_product_rate(
            product, kind=_rate_kind_from_prefix(key_prefix), party_id=party_id,
            prefer_party=True,
        )
        return float(rate or 0)
    except Exception:
        kind = _rate_kind_from_prefix(key_prefix)
        field = "purchase_price" if kind == "purchase" else "sale_price"
        return float(product.get(field) or 0)


def _line_default_discount_pct(line, product, key_prefix: str, party_id=None, header_default=0.0) -> float:
    """Disc %: use this line's stored value, else header default. Never auto from last invoice."""
    header_default = max(0.0, min(100.0, float(header_default or 0)))
    if not product:
        return header_default
    line_pid = line.get("item_id") or line.get("product_id") if line else None
    if line_pid == product.get("id"):
        # Keep whatever is already on the line (including explicit 0)
        if line and (
            line.get("_disc_locked")
            or line.get("discount_pct") is not None
            or float(line.get("line_discount") or 0) > 0
        ):
            return _line_discount_pct(line)
    return header_default


def _rate_disc_number_inputs(
    cols, rate_col, disc_col, line, product, key_prefix, row_index,
    party_id=None, default_discount_pct=0.0, rate_key_suffix="ir", disc_key_suffix="d",
):
    """
    Rate + Disc % inputs. When product or party changes, re-seed rate from last invoice.
    Disc % is never auto-filled from history — only from this line or header default.
    """
    prod_id = product["id"] if product else 0
    party = int(party_id or 0)
    sig = f"{prod_id}:{party}"
    sig_key = f"{key_prefix}_psig_{row_index}"
    rate_key = f"{key_prefix}_{rate_key_suffix}_{row_index}"
    disc_key = f"{key_prefix}_{disc_key_suffix}_{row_index}"
    if st.session_state.get(sig_key) != sig:
        st.session_state[sig_key] = sig
        for k in (rate_key, f"{rate_key}__num", f"{rate_key}__seed", disc_key):
            st.session_state.pop(k, None)

    default_rate = _line_default_rate(line, product, key_prefix, party_id) if product else 0.0
    default_disc = (
        _line_default_discount_pct(line, product, key_prefix, party_id, default_discount_pct)
        if product else max(0.0, min(100.0, float(default_discount_pct or 0)))
    )
    rate_decimals = _rate_decimals_from_prefix(key_prefix)
    with cols[rate_col]:
        rate = money_input(
            "Rate",
            value=float(default_rate),
            min_value=0.0,
            key=rate_key,
            label_visibility="collapsed",
            decimals=rate_decimals,
            help=(
                "Purchase rate — up to 4 decimals"
                if rate_decimals >= 4
                else "Type rate with thousand separators if needed"
            ),
        )
    disc_pct = cols[disc_col].number_input(
        "Disc %", min_value=0.0, max_value=100.0, value=float(default_disc),
        key=disc_key, format="%.2f", label_visibility="collapsed",
    )
    return rate, disc_pct


def _calc_auto_net_weight(product, qty):
    """Net weight = quantity × product standard weight (kg per unit)."""
    sw = float(product.get("standard_weight") or 0) if product else 0
    qty = float(qty or 0)
    if sw > 0:
        return round(qty * sw, 3)
    return round(qty, 3) if qty > 0 else 0.0


def _line_unit_weight_kg(qty, net_wt, product=None):
    """Per-unit weight from line net ÷ qty, else product standard weight."""
    qty = float(qty or 0)
    net = float(net_wt or 0)
    if qty > 0 and net > 0:
        return round(net / qty, 4)
    sw = float((product or {}).get("standard_weight") or 0)
    return round(sw, 4) if sw > 0 else 0.0


def _unit_weight_display(cols, col_idx, qty, net_wt, product):
    """Read-only unit weight for verification against product standard."""
    unit = _line_unit_weight_kg(qty, net_wt, product)
    std = float((product or {}).get("standard_weight") or 0) if product else 0
    if unit <= 0:
        cols[col_idx].write("—")
        return
    hint = ""
    if std > 0 and abs(unit - std) >= 0.001:
        hint = f"  \n<span style='font-size:0.75em;color:#888'>std {std:,.3f}</span>"
    cols[col_idx].markdown(f"**{unit:,.4f}**{hint}", unsafe_allow_html=True)


def _net_weight_input(cols, col_idx, product, qty, line, key_prefix, row_index):
    """Auto-fill net weight when product or qty changes; allow manual override."""
    prod_id = product["id"] if product else 0
    qty = float(qty or 0)
    sig = f"{prod_id}:{qty}"
    sig_key = f"{key_prefix}_wtsig_{row_index}"
    wt_key = f"{key_prefix}_iw_{row_index}"
    if st.session_state.get(sig_key) != sig:
        st.session_state[sig_key] = sig
        st.session_state.pop(wt_key, None)
    default = _calc_auto_net_weight(product, qty)
    if wt_key not in st.session_state and line:
        stored = float(line.get("net_weight") or 0)
        line_pid = line.get("item_id") or line.get("product_id")
        if stored > 0 and line_pid == prod_id and float(line.get("quantity") or 0) == qty:
            default = stored
    return cols[col_idx].number_input(
        "Wt", min_value=0.0, value=default, key=wt_key, format="%.3f", label_visibility="collapsed",
    )


def _line_items_totals_footer(valid, show_weight):
    if not valid:
        return
    tqty = sum(float(l.get("quantity") or 0) for l in valid)
    tamt = sum(float(l.get("amount") or 0) for l in valid)
    if show_weight:
        tnw = sum(float(l.get("net_weight") or 0) for l in valid)
        st.markdown(
            f"**Line totals:** Qty **{tqty:,.2f}** · Unit lines **{len(valid)}** · "
            f"Net weight **{tnw:,.3f} kg** · Amount **{tamt:,.2f}**"
        )
    else:
        st.markdown(f"**Line totals:** Qty **{tqty:,.2f}** · Amount **{tamt:,.2f}**")


def _disc_pct_input(cols, col_idx, line, key_prefix, row_index, default_discount_pct=0.0):
    """Editable line Disc %. Prefers stored line %, else header default for new lines."""
    if (
        line.get("discount_pct") is not None
        or float(line.get("line_discount") or 0) > 0
    ):
        default = _line_discount_pct(line)
    else:
        default = max(0.0, min(100.0, float(default_discount_pct or 0)))
    return cols[col_idx].number_input(
        "Disc %",
        min_value=0.0,
        max_value=100.0,
        value=float(default),
        key=f"{key_prefix}_d_{row_index}",
        format="%.2f",
        label_visibility="collapsed",
    )


def line_items_editor(
    items_dict, key_prefix, default_lines=None, show_weight=False, show_tax=False,
    party_id=None, default_discount_pct=0.0,
):
    sk = f"{key_prefix}_lines"
    _init_line_items_session(sk, default_lines)
    section_header("Line Items")
    updated, to_remove = [], []
    labels, display_to_key = _product_option_labels(items_dict, key_prefix, party_id)
    widths = _line_item_col_widths(show_weight)
    with st.container(key=f"{key_prefix}_lines_blk"):
        _line_items_table_header(show_weight)
        for i, line in enumerate(st.session_state[sk]):
            cols = st.columns(widths, gap="small")
            pid = line.get("product_id") or line.get("item_id")
            default_key = (
                next((l for l in items_dict if items_dict[l]["id"] == pid), None)
                if pid else None
            )
            default_label = next(
                (d for d, k in display_to_key.items() if k == default_key), None
            ) if default_key else None
            idx = labels.index(default_label) if default_label in labels else 0
            sel = cols[0].selectbox(
                "p", labels, index=idx, key=f"{key_prefix}_p_{i}", label_visibility="collapsed",
            ) if len(labels) > 1 else None
            qty = cols[1].number_input(
                "q", min_value=0.0, value=float(line.get("quantity") or 0),
                key=f"{key_prefix}_q_{i}", label_visibility="collapsed", format="%.2f",
            )
            ci = 2
            net_wt = 0.0
            raw_key = display_to_key.get(sel) if sel else None
            prod = items_dict.get(raw_key) if raw_key and raw_key != LINE_PRODUCT_PLACEHOLDER else None
            if show_weight:
                net_wt = _net_weight_input(cols, ci, prod, qty, line, key_prefix, i)
                ci += 1
                _unit_weight_display(cols, ci, qty, net_wt, prod)
                ci += 1
            rate_ci = ci
            ci += 1
            disc_ci = ci
            ci += 1
            rate, disc_pct = _rate_disc_number_inputs(
                cols, rate_ci, disc_ci, line, prod, key_prefix, i,
                party_id=party_id, default_discount_pct=default_discount_pct,
                rate_key_suffix="r", disc_key_suffix="d",
            )
            effective_disc = disc_pct if disc_pct > 0 else float(default_discount_pct or 0)
            amount = _line_amount_after_discount(qty, rate, effective_disc)
            cols[ci].markdown(
                f'<div class="txn-line-num">{amount:,.2f}</div>',
                unsafe_allow_html=True,
            )
            ci += 1
            _prev_rate_column(cols, ci, prod, key_prefix, party_id)
            if cols[-1].button("✕", key=f"{key_prefix}_x_{i}"):
                to_remove.append(i)
            elif sel and raw_key and raw_key != LINE_PRODUCT_PLACEHOLDER and prod:
                row = {
                    "product_id": prod["id"], "item_id": prod["id"],
                    "quantity": qty, "rate": rate, "amount": amount, "net_weight": net_wt,
                    "discount_pct": disc_pct, "tax_rate_id": prod.get("tax_rate_id"),
                }
                if show_tax and prod.get("tax_rate_id"):
                    tr = db.get_tax_rate(prod["tax_rate_id"])
                    if tr:
                        from tax_engine import calc_line
                        cl = calc_line(qty, rate, effective_disc, tr)
                        row["tax_amount"] = cl["tax_amount"]
                        row["amount"] = cl["taxable"]
                        row["line_discount"] = cl["line_discount"]
                updated.append(row)
            else:
                updated.append(dict(line))
    if to_remove:
        st.session_state[sk] = _pad_line_rows([l for j, l in enumerate(updated) if j not in to_remove])
        st.rerun()
    st.session_state[sk] = _pad_line_rows(updated)
    if st.button("+ Add Line", key=f"{key_prefix}_add"):
        blank = _blank_line_item()
        blank["discount_pct"] = float(default_discount_pct or 0)
        st.session_state[sk].append(blank)
        st.rerun()
    valid = [l for l in updated if l.get("product_id") or l.get("item_id")]
    _line_items_totals_footer(valid, show_weight)
    if party_id:
        st.caption(
            "**Prev Rate** = last invoice rate + date for this customer/supplier. "
            "Rate auto-fills from that history; Disc % only if you type it (or set header Disc %)."
        )
        apply_last_invoice_discounts_button(
            key_prefix=key_prefix,
            party_id=party_id,
            party_kind=_rate_kind_from_prefix(key_prefix),
            lines_key=sk,
            disc_key_suffix="d",
        )
    return valid, sum(l["amount"] for l in valid)


def smart_line_item_editor(
    items_dict, key_prefix, default_lines=None, show_weight=False, party_id=None,
    default_discount_pct=0.0, max_product_options=500,
):
    """Tabular line editor with product filter, unit weight, and padded rows for edits."""
    # Full Product dropdown stays searchable until catalogs get very large.
    # Cap used to be 2200 — after item restores (~2.7k) codes vanished from
    # the in-dropdown typeahead ("No results").
    FULL_CATALOG_LIMIT = 12000
    sk = f"{key_prefix}_lines"
    _init_line_items_session(sk, default_lines)
    section_header("Line Items")
    id_to_label = {
        p["id"]: label
        for label, p in (items_dict or {}).items()
        if p and p.get("id") is not None
    }
    all_products = list(items_dict.values())
    total_n = len(all_products)

    filt = st.text_input(
        "Search product code or name",
        key=f"{key_prefix}_pfilt",
        placeholder="e.g. DT1060 or LASHKARA — filters the Product list below",
        help="Type a product code here to filter every Product dropdown. "
             "You can also type inside the Product box when the full list is loaded.",
    )
    typed = (filt or "").strip()

    selected_ids = {
        int(l.get("item_id") or l.get("product_id"))
        for l in st.session_state.get(sk, [])
        if l.get("item_id") or l.get("product_id")
    }
    selected_products = [p for p in all_products if p.get("id") in selected_ids]

    if typed:
        products = filter_products_for_line(
            all_products, typed, max_results=max(max_product_options, 500),
        )
        have = {p["id"] for p in products}
        for p in selected_products:
            if p["id"] not in have:
                products.append(p)
                have.add(p["id"])
        products = sorted(products, key=lambda p: natural_code_sort_key(p.get("code")))
        if not products:
            st.warning(
                f"No product matches **{typed}**. "
                "Check the code, or the item may have been removed (idle / zero stock)."
            )
            products = sorted(selected_products[:], key=lambda p: natural_code_sort_key(p.get("code")))
        else:
            q_compact = "".join(ch for ch in typed.lower() if ch.isalnum())
            exact = [
                p for p in products
                if str(p.get("code") or "").lower() == typed.lower()
                or "".join(ch for ch in str(p.get("code") or "").lower() if ch.isalnum()) == q_compact
            ]
            st.info(
                f"Searching: **{typed}** · **{len(products):,}** match(es)"
                + (f" · exact: **{exact[0]['code']} - {exact[0]['name']}**" if exact else "")
                + " — pick it in the **Product** column."
            )
    else:
        if total_n <= FULL_CATALOG_LIMIT:
            products = sorted(all_products, key=lambda p: natural_code_sort_key(p.get("code")))
            st.caption(
                f"**{total_n:,}** products loaded — type a code in the **Product** box "
                "(e.g. DT1060), or use the search field above."
            )
        else:
            products = selected_products + sorted(
                [p for p in all_products if p.get("id") not in selected_ids],
                key=lambda p: natural_code_sort_key(p.get("code")),
            )[:max_product_options]
            st.warning(
                f"Showing {len(products)} of {total_n:,} products. "
                "**Type the product code in the search box above** (e.g. DT1060), then select it."
            )
    filtered_dict = {}
    for p in products:
        label = id_to_label.get(p["id"]) or f"{p.get('code')} - {p.get('name')}"
        filtered_dict[label] = p
    labels, display_to_key = _product_option_labels(filtered_dict, key_prefix, party_id)
    updated, to_remove = [], []
    widths = _line_item_col_widths(show_weight)
    with st.container(key=f"{key_prefix}_lines_blk"):
        _line_items_table_header(show_weight)
        for i, line in enumerate(st.session_state[sk]):
            cols = st.columns(widths, gap="small")
            pid = line.get("item_id") or line.get("product_id")
            default_key = (
                next((k for k, p in filtered_dict.items() if p and p["id"] == pid), None)
                if pid else None
            )
            # If current product filtered out, still show it in options
            if pid and not default_key:
                full = id_to_label.get(int(pid)) if pid else None
                if not full:
                    full = next(
                        (f"{p['code']} - {p['name']}" for p in items_dict.values() if p["id"] == pid),
                        None,
                    )
                if full and full not in filtered_dict:
                    filtered_dict[full] = items_dict.get(full) or next(
                        p for p in items_dict.values() if p["id"] == pid
                    )
                    labels, display_to_key = _product_option_labels(
                        filtered_dict, key_prefix, party_id,
                    )
                    default_key = full
            default_label = next(
                (d for d, k in display_to_key.items() if k == default_key), None
            ) if default_key else None
            idx = labels.index(default_label) if default_label in labels else 0
            sel = cols[0].selectbox(
                "Item", labels, index=idx, key=f"{key_prefix}_ip_{i}", label_visibility="collapsed",
            ) if len(labels) > 1 else None
            qty = cols[1].number_input(
                "Qty", min_value=0.0, value=float(line.get("quantity") or 0),
                key=f"{key_prefix}_iq_{i}", label_visibility="collapsed", format="%.2f",
            )
            ci = 2
            net_wt = 0.0
            raw_key = display_to_key.get(sel) if sel else None
            prod = filtered_dict.get(raw_key) if raw_key and raw_key != LINE_PRODUCT_PLACEHOLDER else None
            if show_weight:
                net_wt = _net_weight_input(cols, ci, prod, qty, line, key_prefix, i)
                ci += 1
                _unit_weight_display(cols, ci, qty, net_wt, prod)
                ci += 1
            rate_ci = ci
            ci += 1
            disc_ci = ci
            ci += 1
            rate, disc_pct = _rate_disc_number_inputs(
                cols, rate_ci, disc_ci, line, prod, key_prefix, i,
                party_id=party_id, default_discount_pct=default_discount_pct,
                rate_key_suffix="ir", disc_key_suffix="d",
            )
            effective_disc = disc_pct if disc_pct > 0 else float(default_discount_pct or 0)
            amount = _line_amount_after_discount(qty, rate, effective_disc)
            cols[ci].markdown(
                f'<div class="txn-line-num">{amount:,.2f}</div>',
                unsafe_allow_html=True,
            )
            ci += 1
            _prev_rate_column(cols, ci, prod, key_prefix, party_id)
            if cols[-1].button("✕", key=f"{key_prefix}_id_{i}"):
                to_remove.append(i)
            elif sel and raw_key and raw_key != LINE_PRODUCT_PLACEHOLDER and prod:
                row = {
                    "item_id": prod["id"], "quantity": qty, "rate": rate,
                    "amount": amount, "discount_pct": disc_pct,
                }
                if show_weight:
                    row["net_weight"] = net_wt
                updated.append(row)
            else:
                updated.append(dict(line))
    if to_remove:
        st.session_state[sk] = _pad_line_rows([l for j, l in enumerate(updated) if j not in to_remove])
        st.rerun()
    st.session_state[sk] = _pad_line_rows(updated)
    if st.button("+ Add Line", key=f"{key_prefix}_addln"):
        blank = _blank_line_item()
        blank["discount_pct"] = float(default_discount_pct or 0)
        st.session_state[sk].append(blank)
        st.rerun()
    valid = [l for l in updated if l.get("item_id")]
    _line_items_totals_footer(valid, show_weight)
    if party_id:
        st.caption(
            "**Prev Rate** = last invoice rate + date (+ doc no) for this customer/supplier. "
            "Rate auto-fills from that history; Disc % only if you type it (or set header Disc %)."
        )
        apply_last_invoice_discounts_button(
            key_prefix=key_prefix,
            party_id=party_id,
            party_kind=_rate_kind_from_prefix(key_prefix),
            lines_key=sk,
            disc_key_suffix="d",
        )
    if valid:
        st.caption("Tip: select a line below to edit qty / rate / Disc % — totals recalculate on change.")
        edit_labels = [
            (
                f"Line {i + 1}: Qty {float(l.get('quantity') or 0):,.2f} × "
                f"Rate {_fmt_rate(l.get('rate') or 0, key_prefix)}"
                + (
                    f" (−{float(l.get('discount_pct') or 0):.2f}%)"
                    if float(l.get("discount_pct") or 0) > 0 else ""
                )
            )
            for i, l in enumerate(valid)
        ]
        edit_pick = st.selectbox(
            "Select line to edit",
            ["—"] + edit_labels,
            key=f"{key_prefix}_edit_pick",
            label_visibility="collapsed",
        )
        if edit_pick != "—":
            ei = edit_labels.index(edit_pick)
            el = valid[ei]
            ec1, ec2, ec3, ec4 = st.columns([1.1, 1.1, 1.0, 1])
            nqty = ec1.number_input(
                "Qty", min_value=0.0, value=float(el.get("quantity") or 0),
                key=f"{key_prefix}_eqty_{ei}",
            )
            with ec2:
                nrate = money_input(
                    "Rate", value=float(el.get("rate") or 0), min_value=0.0,
                    key=f"{key_prefix}_erate_{ei}",
                    decimals=_rate_decimals_from_prefix(key_prefix),
                )
            ndisc = ec3.number_input(
                "Disc %", min_value=0.0, max_value=100.0,
                value=float(el.get("discount_pct") or 0),
                key=f"{key_prefix}_edisc_{ei}", format="%.2f",
            )
            if ec4.button("Update line", key=f"{key_prefix}_eupd_{ei}"):
                for j, row in enumerate(st.session_state[sk]):
                    rid = row.get("item_id") or row.get("product_id")
                    if rid == el.get("item_id"):
                        st.session_state[sk][j]["quantity"] = nqty
                        st.session_state[sk][j]["rate"] = nrate
                        st.session_state[sk][j]["discount_pct"] = ndisc
                        st.session_state[sk][j]["amount"] = _line_amount_after_discount(
                            nqty, nrate, ndisc,
                        )
                        break
                st.rerun()
            if ec4.button("Remove line", key=f"{key_prefix}_erm_{ei}"):
                target = el.get("item_id")
                st.session_state[sk] = _pad_line_rows([
                    row for row in st.session_state[sk]
                    if (row.get("item_id") or row.get("product_id")) != target
                ])
                st.rerun()
    if show_weight and valid:
        st.caption("Unit Wt = Net Wt ÷ Qty (grey **std** = product standard weight for comparison).")
    return valid, sum(l["amount"] for l in valid)


def admin_unapprove_panel(doc_kind, invoice_id, document_no, key_prefix):
    """Admin control to unapprove a posted invoice so it can be amended and re-approved."""
    if doc_kind == "sale":
        unapprove_fn = db.unapprove_sale_invoice
        edit_hint = "Sales Invoices → Edit"
    else:
        unapprove_fn = db.unapprove_purchase_invoice
        edit_hint = "Purchase Invoices → Edit"
    if user_role() != "admin":
        st.warning(
            f"Invoice **{document_no}** is **approved** and locked. "
            "Only an administrator can unapprove it for amendment."
        )
        return
    st.markdown("#### Amendment (Administrator)")
    st.caption(
        "Unapprove reverses stock, party balance, cash/bank entries, and GL posting. "
        f"Then amend on **{edit_hint}**, submit for approval, and re-approve."
    )
    reason = st.text_input("Reason for unapprove (required)", key=f"{key_prefix}_unap_reason")
    if st.button("Unapprove for Amendment", key=f"{key_prefix}_unap", type="secondary"):
        if not (reason or "").strip():
            st.error("Enter a reason before unapproving.")
        else:
            try:
                unapprove_fn(invoice_id, uid(), reason.strip())
                ff.action_done(f"**{document_no}** unapproved — you can now edit and re-submit for approval.")
            except Exception as e:
                st.error(str(e))


def admin_cancel_panel(doc_kind, invoice_id, document_no, key_prefix):
    """Admin control to permanently cancel a posted invoice."""
    if user_role() != "admin":
        return
    cancel_fn = db.cancel_sale_invoice if doc_kind == "sale" else db.cancel_purchase_invoice
    st.markdown("#### Cancel Invoice (Administrator)")
    st.caption(
        "Cancel permanently voids the invoice and reverses stock, party balance, cash/bank, and GL. "
        "Use **Unapprove for Amendment** above if you need to edit and re-approve instead."
    )
    reason = st.text_input("Reason for cancellation (required)", key=f"{key_prefix}_cancel_reason")
    if st.button("Cancel Invoice Permanently", key=f"{key_prefix}_cancel", type="secondary"):
        if not (reason or "").strip():
            st.error("Enter a reason before cancelling.")
        else:
            try:
                cancel_fn(invoice_id, uid())
                ff.action_done(f"**{document_no}** cancelled — {reason.strip()}")
            except Exception as e:
                st.error(str(e))
