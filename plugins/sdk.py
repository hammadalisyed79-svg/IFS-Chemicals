"""IFS ERP Plugin SDK — third-party extension interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class PluginManifest:
    plugin_id: str
    name: str
    version: str = "1.0.0"
    author: str = ""
    description: str = ""
    requires_erp: str = "V17.0"


class PluginBase(ABC):
    """Base class for all IFS ERP plugins."""

    manifest: PluginManifest

    def on_load(self) -> None:
        """Called when plugin is discovered and activated."""

    def on_unload(self) -> None:
        """Called on shutdown."""

    # Registration hooks — override to register capabilities
    def register_menus(self) -> list[dict]:
        return []

    def register_reports(self) -> list[dict]:
        return []

    def register_dashboards(self) -> list[dict]:
        return []

    def register_jobs(self) -> dict[str, Callable]:
        return {}

    def register_api_routes(self) -> list[dict]:
        return []

    def register_workflows(self) -> list[dict]:
        return []

    def register_validation_rules(self) -> list[dict]:
        return []

    def register_event_handlers(self) -> dict[str, Callable]:
        return {}

    def register_notifications(self) -> list[dict]:
        return []

    def register_print_templates(self) -> list[dict]:
        return []


@dataclass
class PluginRegistry:
    plugins: dict[str, PluginBase] = field(default_factory=dict)
    menus: list[dict] = field(default_factory=list)
    reports: list[dict] = field(default_factory=list)
    dashboards: list[dict] = field(default_factory=list)
    jobs: dict[str, Callable] = field(default_factory=dict)
    api_routes: list[dict] = field(default_factory=list)
    workflows: list[dict] = field(default_factory=list)
    validation_rules: list[dict] = field(default_factory=list)
    event_handlers: dict[str, list[Callable]] = field(default_factory=dict)
    notifications: list[dict] = field(default_factory=list)
    print_templates: list[dict] = field(default_factory=list)


REGISTRY = PluginRegistry()


def register_plugin(plugin: PluginBase) -> None:
    pid = plugin.manifest.plugin_id
    REGISTRY.plugins[pid] = plugin
    plugin.on_load()
    REGISTRY.menus.extend(plugin.register_menus())
    REGISTRY.reports.extend(plugin.register_reports())
    REGISTRY.dashboards.extend(plugin.register_dashboards())
    REGISTRY.jobs.update(plugin.register_jobs())
    REGISTRY.api_routes.extend(plugin.register_api_routes())
    REGISTRY.workflows.extend(plugin.register_workflows())
    REGISTRY.validation_rules.extend(plugin.register_validation_rules())
    for evt, handler in plugin.register_event_handlers().items():
        REGISTRY.event_handlers.setdefault(evt, []).append(handler)
    REGISTRY.notifications.extend(plugin.register_notifications())
    REGISTRY.print_templates.extend(plugin.register_print_templates())
    _persist_plugin(plugin)


def _persist_plugin(plugin: PluginBase) -> None:
    import json
    from database import get_connection
    m = plugin.manifest
    with get_connection() as conn:
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='erp_plugins'").fetchone():
            conn.execute(
                """INSERT INTO erp_plugins(plugin_id,name,version,manifest_json,is_active)
                   VALUES(?,?,?,?,1)
                   ON CONFLICT(plugin_id) DO UPDATE SET version=excluded.version""",
                (m.plugin_id, m.name, m.version, json.dumps(m.__dict__)),
            )
