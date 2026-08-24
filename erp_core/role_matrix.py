"""V15 enterprise role → permission matrix defaults."""

from __future__ import annotations

_ALL = {
    "view": 1, "add": 1, "edit": 1, "delete_draft": 1,
    "approve": 1, "reject": 1, "post": 1, "print": 1, "export": 1, "admin_override": 1,
}
_READ = {"view": 1, "print": 1, "export": 1}
_SALES_OPS = {
    "view": 1, "add": 1, "edit": 1, "delete_draft": 1,
    "approve": 0, "reject": 0, "post": 0, "print": 1, "export": 1,
}
_SALES_MGR = {**_SALES_OPS, "approve": 1, "reject": 1, "post": 1}
_FIN_OPS = {
    "view": 1, "add": 1, "edit": 1, "delete_draft": 1,
    "post": 1, "print": 1, "export": 1,
}
_FIN_MGR = {**_FIN_OPS, "approve": 1, "reject": 1, "admin_override": 1}
_PORTAL_ONLY = {"view": 1, "add": 1, "edit": 1, "print": 1}

_MODULES = [
    "Dashboard", "Masters", "Sales", "Purchase", "Inventory", "Production",
    "Finance", "HR", "Reports", "Admin", "Portal", "PriceLists",
]


def _blank() -> dict[str, dict]:
    return {m: {k: 0 for k in _ALL} for m in _MODULES}


def default_matrix_for_role(role_code: str) -> dict[str, dict]:
    m = _blank()
    code = (role_code or "").upper()

    if code in ("ADMIN", "SUPER_ADMIN"):
        for mod in _MODULES:
            m[mod] = dict(_ALL)
        return m

    if code == "DIRECTOR":
        for mod in _MODULES:
            if mod != "Admin":
                m[mod] = dict(_READ)
                m[mod]["approve"] = 1
        m["Admin"]["view"] = 1
        return m

    if code == "GM":
        for mod in ("Dashboard", "Masters", "Sales", "Purchase", "Inventory", "Production", "Finance", "HR", "Reports", "Portal", "PriceLists"):
            m[mod] = dict(_SALES_MGR)
        m["Admin"]["view"] = 1
        return m

    if code in ("FIN_MGR",):
        for mod in ("Dashboard", "Finance", "Reports"):
            m[mod] = dict(_FIN_MGR)
        m["Masters"]["view"] = 1
        m["Sales"]["view"] = 1
        m["Purchase"]["view"] = 1
        return m

    if code in ("ACCOUNTANT",):
        for mod in ("Dashboard", "Finance", "Reports"):
            m[mod] = dict(_FIN_OPS)
        m["Masters"]["view"] = 1
        return m

    if code in ("SALES_MGR",):
        for mod in ("Dashboard", "Sales", "Masters", "Reports", "Portal", "PriceLists"):
            m[mod] = dict(_SALES_MGR)
        m["Inventory"]["view"] = 1
        return m

    if code in ("SALES_OFF",):
        for mod in ("Dashboard", "Sales", "Masters", "Portal"):
            m[mod] = dict(_SALES_OPS)
        return m

    if code in ("PUR_MGR",):
        for mod in ("Dashboard", "Purchase", "Masters", "Reports", "Inventory"):
            m[mod] = dict(_SALES_MGR)
        return m

    if code in ("PUR_OFF",):
        for mod in ("Dashboard", "Purchase", "Masters", "Inventory"):
            m[mod] = dict(_SALES_OPS)
        return m

    if code in ("STORE_MGR", "STORE_OFF"):
        for mod in ("Dashboard", "Inventory", "Masters", "Reports"):
            m[mod] = dict(_SALES_MGR if code == "STORE_MGR" else _SALES_OPS)
        return m

    if code in ("PROD_MGR", "PROD_SUP", "QC_OFF"):
        for mod in ("Dashboard", "Production", "Inventory", "Masters"):
            lvl = _SALES_MGR if code == "PROD_MGR" else _SALES_OPS
            m[mod] = dict(lvl)
        return m

    if code in ("HR_MGR", "PAYROLL_OFF"):
        for mod in ("Dashboard", "HR", "Reports"):
            m[mod] = dict(_SALES_MGR if code == "HR_MGR" else _SALES_OPS)
        m["Masters"]["view"] = 1
        return m

    if code == "AUDITOR":
        for mod in _MODULES:
            if mod not in ("Admin", "Portal"):
                m[mod] = dict(_READ)
        return m

    if code in ("DISTRIBUTOR", "DIST_STAFF"):
        m["Portal"] = dict(_PORTAL_ONLY)
        return m

    if code == "VIEWER":
        for mod in _MODULES:
            if mod not in ("Admin", "Portal"):
                m[mod] = dict(_READ)
        return m

    if code == "USER":
        for mod in ("Dashboard", "Masters", "Sales", "Purchase", "Inventory", "Reports"):
            m[mod] = dict(_SALES_OPS)
        return m

    return m


MATRIX_ACTIONS = (
    "view", "add", "edit", "delete_draft", "approve", "reject",
    "post", "print", "export", "admin_override",
)
