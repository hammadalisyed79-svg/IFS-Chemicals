"""Client download page — IFS_Chemicals_ERP.exe for staff PCs."""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from erp_deploy import PUBLIC_URL_HTTPS, public_base_url
from erp_ui.helpers import std_page_header

CLIENT_DIST = Path(__file__).resolve().parent.parent / "client_dist"
CLIENT_EXE = CLIENT_DIST / "IFS_Chemicals_ERP.exe"
CLIENT_README = CLIENT_DIST / "README.txt"
CLIENT_URL_FILE = CLIENT_DIST / "IFS_Chemicals_ERP.url"


def page_download_app():
    std_page_header("Download App")

    site = public_base_url() or PUBLIC_URL_HTTPS
    st.markdown(
        f"""
**Open ERP in the browser:**  
[{site}/]({site}/)

The Windows app opens this same address — **https://erp.ifschemicals.com/**
"""
    )

    st.divider()
    st.subheader("Windows desktop shortcut")

    if CLIENT_EXE.exists():
        data = CLIENT_EXE.read_bytes()
        st.download_button(
            label="Download IFS_Chemicals_ERP.exe",
            data=data,
            file_name="IFS_Chemicals_ERP.exe",
            mime="application/vnd.microsoft.portable-executable",
            type="primary",
            use_container_width=True,
            key="dl_client_exe",
        )
        st.caption(
            f"File size: {len(data) / 1024:.0f} KB · "
            "Double-click after download — no install required."
        )
    else:
        st.warning(
            "Client EXE not built yet on this server. "
            "Administrator: run `packaging\\build_client_exe.bat`."
        )

    if CLIENT_URL_FILE.exists():
        st.download_button(
            label="Download browser shortcut (.url)",
            data=CLIENT_URL_FILE.read_bytes(),
            file_name="IFS_Chemicals_ERP.url",
            mime="application/internet-shortcut",
            use_container_width=True,
            key="dl_client_url",
        )

    if CLIENT_README.exists():
        with st.expander("Setup instructions"):
            st.code(CLIENT_README.read_text(encoding="utf-8", errors="replace"))

    st.info(
        "Clients only need this shortcut + a browser. "
        "The ERP runs on the company server — nothing heavy installs on their PC."
    )
