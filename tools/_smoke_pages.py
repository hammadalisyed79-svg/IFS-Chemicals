"""NameError/ImportError smoke for all app.PAGES entries.

Run:  venv\\Scripts\\python.exe tools\\_smoke_pages.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class _StopPage(Exception):
    pass


def _install_mocks():
    import streamlit as st

    st.session_state["user"] = {
        "id": 1, "username": "smoke", "role": "admin",
        "full_name": "Smoke", "is_active": 1,
    }

    def _select(label=None, options=None, index=0, **_k):
        opts = list(options or [])
        if not opts:
            return None
        i = index if isinstance(index, int) and 0 <= index < len(opts) else 0
        return opts[i]

    st.selectbox = _select
    st.radio = _select
    st.multiselect = MagicMock(return_value=[])
    st.button = MagicMock(return_value=False)
    st.checkbox = MagicMock(return_value=False)
    st.toggle = MagicMock(return_value=False)
    st.text_input = MagicMock(return_value="")
    st.text_area = MagicMock(return_value="")
    st.number_input = MagicMock(return_value=0.0)
    st.date_input = MagicMock(return_value=None)
    st.time_input = MagicMock(return_value=None)
    st.slider = MagicMock(return_value=0)
    st.file_uploader = MagicMock(return_value=None)
    st.form_submit_button = MagicMock(return_value=False)
    st.download_button = MagicMock(return_value=False)
    st.columns = lambda n, **k: [MagicMock() for _ in range(n if isinstance(n, int) else len(n))]
    st.tabs = lambda labels, **k: [MagicMock() for _ in labels]
    st.expander = MagicMock(return_value=MagicMock())
    st.container = MagicMock(return_value=MagicMock())
    st.form = MagicMock(return_value=MagicMock())
    st.spinner = MagicMock(return_value=MagicMock())
    st.empty = MagicMock(return_value=MagicMock())
    st.markdown = st.write = st.caption = st.info = st.success = st.warning = st.error = MagicMock()
    st.metric = st.dataframe = st.table = st.divider = st.toast = st.progress = MagicMock()
    st.stop = lambda: (_ for _ in ()).throw(_StopPage("stop"))
    st.rerun = lambda: (_ for _ in ()).throw(_StopPage("rerun"))
    st.set_page_config = MagicMock()
    # Avoid cache serialization path in smoke
    st.cache_data = lambda **_kw: (lambda f: f)
    st.cache_resource = lambda **_kw: (lambda f: f)
    return st


def main() -> int:
    st = _install_mocks()
    import app

    fails = []
    for name, fn in sorted(app.PAGES.items()):
        if not callable(fn):
            fails.append((name, "not callable"))
            continue
        try:
            fn()
        except _StopPage:
            pass
        except NameError as e:
            fails.append((name, f"NameError: {e}"))
        except ImportError as e:
            fails.append((name, f"ImportError: {e}"))
        except SyntaxError as e:
            fails.append((name, f"SyntaxError: {e}"))
        except Exception:
            # Widget/data noise — ignore for this smoke
            pass

    # Critical extracted tabs
    for key, tab_key, tab, page_fn in (
        ("Sales New", "sal_inv_tab", "New", app.PAGES.get("Sales")),
        ("Purchase New", "pur_inv_tab", "New", app.PAGES.get("Purchases")),
        ("Sales Register", "sal_inv_tab", "Register", app.PAGES.get("Sales")),
        ("Purchase Register", "pur_inv_tab", "Register", app.PAGES.get("Purchases")),
    ):
        if not page_fn:
            continue
        st.session_state[tab_key] = tab
        try:
            page_fn()
        except _StopPage:
            pass
        except NameError as e:
            fails.append((key, f"NameError: {e}"))
        except Exception as e:
            if "is not defined" in str(e):
                fails.append((key, str(e)))

    print(f"PAGES={len(app.PAGES)} name_fails={len(fails)}")
    for name, detail in fails:
        print(f"FAIL  {name}: {detail}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
