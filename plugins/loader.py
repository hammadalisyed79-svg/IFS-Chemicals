"""Plugin discovery — scans plugins/ folder."""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path

from plugins.sdk import REGISTRY, PluginBase, register_plugin

_LOADED = False


def discover_plugins() -> int:
    global _LOADED
    if _LOADED:
        return len(REGISTRY.plugins)
    plugins_dir = Path(__file__).parent
    for finder, name, ispkg in pkgutil.iter_modules([str(plugins_dir)]):
        if name in ("sdk", "loader", "__pycache__") or name.startswith("_"):
            continue
        try:
            mod = importlib.import_module(f"plugins.{name}")
            for attr in dir(mod):
                obj = getattr(mod, attr)
                if isinstance(obj, type) and issubclass(obj, PluginBase) and obj is not PluginBase:
                    register_plugin(obj())
        except Exception as exc:
            import logging
            logging.getLogger("ifs.plugins").warning("Plugin %s failed: %s", name, exc)
    _LOADED = True
    return len(REGISTRY.plugins)


def dispatch_event(event) -> None:
    discover_plugins()
    for handler in REGISTRY.event_handlers.get(event.event_type, []):
        try:
            handler(event)
        except Exception:
            pass
    for handler in REGISTRY.event_handlers.get("*", []):
        try:
            handler(event)
        except Exception:
            pass


def get_plugin_menus() -> list[dict]:
    discover_plugins()
    return list(REGISTRY.menus)
