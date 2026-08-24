# Plugin SDK Guide — V17

## Overview

Third-party extensions live in `plugins/`. Each plugin subclasses `PluginBase` from `plugins/sdk.py`.

## Quick start

```python
# plugins/my_plugin/__init__.py
from plugins.sdk import PluginBase, PluginManifest

class MyPlugin(PluginBase):
    manifest = PluginManifest(
        plugin_id="com.example.myplugin",
        name="My Plugin",
        version="1.0.0",
    )

    def register_menus(self):
        return [{"label": "My Screen", "group": "Reports", "screen": "My Screen"}]

    def register_event_handlers(self):
        return {"InvoicePosted": self.on_invoice}

    def on_invoice(self, event):
        pass
```

## Registration hooks

| Hook | Method |
|------|--------|
| Menus | `register_menus()` |
| Reports | `register_reports()` |
| Dashboards | `register_dashboards()` |
| Background jobs | `register_jobs()` |
| API routes | `register_api_routes()` |
| Workflows | `register_workflows()` |
| Validation rules | `register_validation_rules()` |
| Events | `register_event_handlers()` |
| Notifications | `register_notifications()` |
| Print templates | `register_print_templates()` |

## Discovery

Plugins are auto-loaded from `plugins/*` on API startup via `plugins/loader.discover_plugins()`.

## Sample

See `plugins/sample_plugin/` for a working example.

## API

`GET /api/v1/plugins` — list installed plugins.
