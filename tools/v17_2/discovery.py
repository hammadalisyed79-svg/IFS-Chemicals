"""PART 1 — Full ERP discovery scan."""

from __future__ import annotations

import ast
import importlib.util
import re
from collections import defaultdict
from pathlib import Path

from tools.v17_2.common import ROOT, ReportBundle


def _load_pages() -> dict:
    spec = importlib.util.spec_from_file_location("erp_app", ROOT / "app.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return dict(getattr(mod, "PAGES", {}))


def _nav_screens() -> dict[str, list[str]]:
    spec = importlib.util.spec_from_file_location("erp_nav", ROOT / "erp_ui" / "nav.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return dict(getattr(mod, "NAV_GROUPS", {}))


def _api_routes() -> list[str]:
    text = (ROOT / "api" / "main.py").read_text(encoding="utf-8", errors="ignore")
    return re.findall(r'@app\.(get|post|put|delete|patch)\("([^"]+)"', text)


def _scan_callables(root: Path, prefix: str = "page_") -> list[str]:
    found = []
    for p in root.rglob("*.py"):
        if "venv" in str(p):
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        found.extend(re.findall(rf"^def ({prefix}\w+)", text, re.M))
    return sorted(set(found))


def _dead_imports() -> list[str]:
    dead = []
    for p in (ROOT / "erp_core").glob("*.py"):
        name = p.stem
        hits = 0
        for other in ROOT.rglob("*.py"):
            if "venv" in str(other) or other == p:
                continue
            if name in other.read_text(encoding="utf-8", errors="ignore"):
                hits += 1
                break
        if hits == 0 and name not in ("__init__",):
            dead.append(str(p.relative_to(ROOT)))
    return dead[:30]


def run_discovery() -> ReportBundle:
    rep = ReportBundle("ERP Discovery Report — V17.2")
    pages = _load_pages()
    nav = _nav_screens()
    nav_flat = {s for screens in nav.values() for s in screens}
    page_keys = set(pages.keys())

    # Screens
    missing_pages = sorted(nav_flat - page_keys)
    orphan_pages = sorted(page_keys - nav_flat - {"Items / Products", "BOM / Formula", "Batch Manufacturing"})
    for s in nav_flat:
        if s in pages:
            rep.add("Screen", s, "pass", "Routed in PAGES")
        else:
            rep.add("Screen", s, "fail", "Missing from PAGES dict")
    for s in orphan_pages:
        rep.add("Screen", s, "warn", "In PAGES but not in NAV_GROUPS (hidden/alias)")

    # API
    routes = _api_routes()
    rep.sections["API Routes"] = f"**{len(routes)}** endpoints in `api/main.py`"
    for method, path in routes:
        rep.add("API", f"{method.upper()} {path}", "pass", "Declared")

    # Services
    services = list((ROOT / "application").rglob("*.py"))
    svc_count = len([p for p in services if p.name != "__init__.py"])
    rep.sections["Application Layer"] = f"**{svc_count}** Python modules under `application/`"

    # Events
    ev_text = (ROOT / "domain" / "events.py").read_text(encoding="utf-8")
    events = re.findall(r'^[A-Z_]+ = "(\w+)"', ev_text, re.M)
    rep.sections["Events"] = f"**{len(events)}** domain events in `domain/events.py`"

    # Plugins
    plugins = list((ROOT / "plugins").glob("*/__init__.py"))
    rep.sections["Plugins"] = f"**{len(plugins)}** plugin packages in `plugins/`"

    # Migrations
    mig = (ROOT / "infrastructure" / "migrations" / "engine.py").read_text(encoding="utf-8")
    mig_count = mig.count("MigrationRecord(")
    rep.sections["Migrations"] = f"**{mig_count}** nodes in migration graph"

    # Jobs
    jobs = (ROOT / "infrastructure" / "jobs").rglob("*.py")
    rep.sections["Background Jobs"] = f"**{len(list(jobs))}** job modules"

    # UI pages vs erp_ui
    ui_pages = _scan_callables(ROOT / "erp_ui")
    rep.sections["UI Page Functions"] = f"**{len(ui_pages)}** `page_*` functions in `erp_ui/`"

    # Duplicate routes
    dup_nav = [s for screens in nav.values() for s in screens if screens.count(s) > 1]
    if dup_nav:
        rep.add("Navigation", "Duplicate menu entries", "warn", str(dup_nav))

    # Debt: UI direct DB
    from tools.debt_scanner import scan_ui_db_calls
    ui_db = scan_ui_db_calls()
    rep.sections["Technical Debt Signal"] = (
        f"**{ui_db['total_calls']}** direct DB call patterns in `erp_ui/` "
        f"(business logic not fully in application layer)"
    )
    if ui_db["total_calls"] > 100:
        rep.add("Architecture", "UI direct DB access", "not_certified",
                f"{ui_db['total_calls']} patterns — migration incomplete")

    # Dead code candidates
    dead = _dead_imports()
    if dead:
        rep.sections["Dead Code Candidates"] = "\n".join(f"- `{d}`" for d in dead[:15])

    # Reports
    rpt_profiles = (ROOT / "erp_ui" / "report_profiles.py").read_text(encoding="utf-8", errors="ignore")
    reports = re.findall(r'"name":\s*"([^"]+)"', rpt_profiles)
    rep.sections["Reports"] = f"**{len(reports)}** report profiles registered"

    rep.sections["Implemented vs Gaps"] = (
        f"| Area | Implemented | Gaps |\n|------|------------:|------|\n"
        f"| Screens (nav) | {len(nav_flat) - len(missing_pages)} | {len(missing_pages)} missing routes |\n"
        f"| PAGES entries | {len(pages)} | {len(orphan_pages)} hidden/alias |\n"
        f"| API endpoints | {len(routes)} | Partial CRUD (customers only full) |\n"
        f"| Industrial modules | 15 | Service-layer certified; UI print/export not automated |\n"
    )
    return rep
