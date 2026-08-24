"""Search-first slip attachments — find voucher, then view/upload slips full-size on click."""

import base64
import streamlit as st
from erp_ui import form_flow as ff
import streamlit.components.v1 as components
from application import data_gateway as db
from erp_ui.helpers import uid, fmt_money


ALLOWED_UPLOAD_TYPES = ["pdf", "png", "jpg", "jpeg", "webp"]


def _st_image(image):
    """Compatible with Streamlit 1.28 (use_column_width) and 1.39+ (use_container_width)."""
    try:
        st.image(image, use_container_width=True)
    except TypeError:
        st.image(image, use_column_width=True)


def _format_size(n):
    n = int(n or 0)
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"


def _is_image(att, data=None):
    ctype = (att.get("content_type") or "").lower()
    if ctype.startswith("image/"):
        return True
    return att["file_name"].lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif"))


def _is_pdf(att):
    ctype = (att.get("content_type") or "").lower()
    return ctype == "application/pdf" or att["file_name"].lower().endswith(".pdf")


def _doc_summary(doc):
    amt = doc.get("amount")
    amt_s = fmt_money(amt) if amt is not None else ""
    parts = [doc.get("document_no", ""), doc.get("doc_label", ""), doc.get("txn_date", ""), amt_s]
    if doc.get("reference_no"):
        parts.append(f"Ref: {doc['reference_no']}")
    return " · ".join(p for p in parts if p)


def _render_full_slip(att, key_prefix):
    """Full-size viewer (shown when user clicks Open)."""
    att_id = att["id"]
    path = db.get_finance_attachment_path(att_id)
    if not path:
        st.error("File not found on disk.")
        return
    data = path.read_bytes()
    st.markdown(f"### {att['file_name']}")
    if att.get("notes"):
        st.caption(att["notes"])
    meta = _format_size(att.get("file_size"))
    if att.get("uploaded_at"):
        meta += f" · {att['uploaded_at'][:16]}"
    st.caption(meta)

    if _is_image(att):
        _st_image(data)
    elif _is_pdf(att):
        b64 = base64.b64encode(data).decode()
        components.html(
            f'<iframe src="data:application/pdf;base64,{b64}" '
            f'style="width:100%;height:82vh;border:none;border-radius:8px;"></iframe>',
            height=720,
            scrolling=True,
        )
    else:
        st.info("Preview not available for this file type — use Download.")

    c1, c2 = st.columns(2)
    c1.download_button(
        "Download",
        data,
        file_name=att["file_name"],
        mime=att.get("content_type") or "application/octet-stream",
        key=f"{key_prefix}_full_dl_{att_id}",
        use_container_width=True,
    )
    if c2.button("Close viewer", key=f"{key_prefix}_full_close_{att_id}", use_container_width=True):
        st.session_state.pop(f"{key_prefix}_full_slip", None)
        st.rerun()


def _slip_gallery(source_type, source_id, key_prefix):
    attachments = db.get_finance_attachments(source_type, int(source_id))
    full_id = st.session_state.get(f"{key_prefix}_full_slip")

    if full_id:
        att = db.get_finance_attachment(full_id)
        if att:
            _render_full_slip(att, key_prefix)
            st.divider()

    if not attachments:
        st.caption("No slips attached to this voucher yet.")
        return

    st.markdown(f"**{len(attachments)} slip(s)** — click **Open full** to view")
    cols = st.columns(min(4, len(attachments)) or 1)
    for i, att in enumerate(attachments):
        att_id = att["id"]
        path = db.get_finance_attachment_path(att_id)
        with cols[i % len(cols)]:
            st.markdown(f"**{att['file_name']}**")
            st.caption(_format_size(att.get("file_size")))
            if path and _is_image(att):
                _st_image(path.read_bytes())
            elif path and _is_pdf(att):
                st.markdown("📄 PDF document")
            if st.button("Open full", key=f"{key_prefix}_open_{att_id}", use_container_width=True, type="primary"):
                st.session_state[f"{key_prefix}_full_slip"] = att_id
                st.rerun()
            if st.button("Delete", key=f"{key_prefix}_del_{att_id}", use_container_width=True):
                db.delete_finance_attachment(att_id)
                if st.session_state.get(f"{key_prefix}_full_slip") == att_id:
                    st.session_state.pop(f"{key_prefix}_full_slip", None)
                st.rerun()


def _slip_upload(source_type, source_id, key_prefix):
    with st.expander("Upload new slip", expanded=False):
        uploaded = st.file_uploader(
            "PDF or image (max 5 MB)",
            type=ALLOWED_UPLOAD_TYPES,
            key=f"{key_prefix}_up",
        )
        notes = st.text_input("Notes", key=f"{key_prefix}_notes", placeholder="Cheque no, bank ref…")
        if uploaded and st.button("Save slip", type="primary", key=f"{key_prefix}_save"):
            try:
                db.save_finance_attachment(
                    source_type, int(source_id), uploaded.getvalue(),
                    uploaded.name, uploaded.type, uid(), notes or None,
                )
                ff.action_done(f"Saved **{uploaded.name}**")
            except Exception as exc:
                st.error(str(exc))


def slip_attachment_workspace(source_types, key_prefix, preset=None, title="Slip attachments"):
    """
    Search voucher by no / id / reference → show slips only for selected document.
    preset: {source_type, id, document_no, ...} to auto-select after posting.
    """
    doc_key = f"{key_prefix}_slip_doc"
    hits_key = f"{key_prefix}_slip_hits"
    q_key = f"{key_prefix}_slip_q"

    if preset and doc_key not in st.session_state:
        st.session_state[doc_key] = preset
        if preset.get("document_no"):
            st.session_state[q_key] = preset["document_no"]

    if title:
        st.markdown(f"**{title}**")
    st.caption("Search by voucher **no**, **ID**, or **cheque/reference** — slips show only after you select a match.")

    q = st.text_input(
        "Search voucher",
        key=q_key,
        placeholder="JV-0001, BR-0042, PT-0003, cheque no…",
    )
    bc1, bc2 = st.columns([1, 5])
    do_search = bc1.button("Search", type="primary", key=f"{key_prefix}_slip_go")

    if do_search and q.strip():
        hits = db.search_finance_documents_for_attachment(q.strip(), source_types)
        st.session_state[hits_key] = hits
        if len(hits) == 1:
            st.session_state[doc_key] = hits[0]
            st.session_state.pop(f"{key_prefix}_full_slip", None)
        elif not hits:
            st.session_state.pop(doc_key, None)

    hits = st.session_state.get(hits_key) or []
    if do_search and q.strip() and not hits:
        st.warning("No voucher found.")

    if hits and len(hits) > 1 and not st.session_state.get(doc_key):
        st.markdown("**Select a voucher:**")
        for h in hits:
            label = _doc_summary(h)
            n = db.count_finance_attachments(h["source_type"], h["id"])
            badge = f" ({n} slip{'s' if n != 1 else ''})" if n else ""
            if st.button(f"{label}{badge}", key=f"{key_prefix}_pick_{h['source_type']}_{h['id']}", use_container_width=True):
                st.session_state[doc_key] = h
                st.session_state.pop(f"{key_prefix}_full_slip", None)
                st.rerun()

    doc = st.session_state.get(doc_key)
    if not doc:
        return

    n = db.count_finance_attachments(doc["source_type"], doc["id"])
    head, clear = st.columns([5, 1])
    head.success(f"**{doc['document_no']}** — {doc.get('doc_label', '')} · {_doc_summary(doc)} · {n} slip(s)")
    if clear.button("Clear", key=f"{key_prefix}_slip_clear"):
        st.session_state.pop(doc_key, None)
        st.session_state.pop(hits_key, None)
        st.session_state.pop(f"{key_prefix}_full_slip", None)
        st.rerun()

    _slip_upload(doc["source_type"], doc["id"], key_prefix)
    _slip_gallery(doc["source_type"], doc["id"], key_prefix)


def finance_attachment_panel(source_type, source_id, key_prefix, title="Slip attachments"):
    """Open workspace for one known voucher (e.g. right after posting)."""
    preset = db.get_finance_document_meta(source_type, int(source_id))
    if not preset:
        st.warning("Voucher not found.")
        return
    slip_attachment_workspace([source_type], key_prefix, preset=preset, title=title)


def attachment_picker_and_panel(rows, label_fn, key_prefix, title="Slip attachments"):
    """Legacy helper — prefer slip_attachment_workspace with search."""
    source_types = []
    for r in rows:
        stype = r.get("source_type") or db.vch_source_to_attachment_type(r.get("vch_source"))
        if stype and stype not in source_types:
            source_types.append(stype)
    if not source_types:
        source_types = list(db.FINANCE_ATTACHMENT_TYPES)
    slip_attachment_workspace(source_types, key_prefix, title=title)


def preset_from_voucher(source_type, source_id, document_no=None):
    """Build preset dict after posting."""
    return db.get_finance_document_meta(source_type, int(source_id))
