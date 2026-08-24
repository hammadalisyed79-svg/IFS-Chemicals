"""Sample plugin — demonstrates SDK registration."""

from plugins.sdk import PluginBase, PluginManifest
from domain import events as E


class SamplePlugin(PluginBase):
    manifest = PluginManifest(
        plugin_id="com.ifs.sample",
        name="Sample Extension",
        version="1.0.0",
        description="Example plugin for IFS ERP V17 SDK",
    )

    def register_menus(self) -> list[dict]:
        return [{"label": "Sample Report", "group": "Reports", "screen": "Sample Plugin Report"}]

    def register_reports(self) -> list[dict]:
        return [{"code": "SAMPLE_RPT", "name": "Sample Plugin Report", "base": "customers"}]

    def register_event_handlers(self) -> dict:
        return {E.CUSTOMER_CREATED: self._on_customer}

    def _on_customer(self, event) -> None:
        pass  # Plugin logic here

    def register_jobs(self) -> dict:
        return {"sample_cleanup": lambda p, j: None}
