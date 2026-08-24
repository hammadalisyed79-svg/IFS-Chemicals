"""Generic industrial integration interfaces — vendor-neutral."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class DeviceReading:
    device_code: str
    reading_type: str
    value: Any
    unit: str | None = None
    timestamp: str | None = None


class IndustrialDeviceAdapter(ABC):
    """Base adapter for PLC, SCADA, scales, scanners, printers, sensors."""

    def __init__(self, device_code: str, config: dict | None = None):
        self.device_code = device_code
        self.config = config or {}

    @abstractmethod
    def connect(self) -> bool:
        ...

    @abstractmethod
    def disconnect(self) -> None:
        ...

    @abstractmethod
    def read(self) -> DeviceReading:
        ...

    def write(self, payload: dict) -> bool:
        """Optional write/command — override in subclasses."""
        return False

    def persist_reading(self, batch_ticket_id: int | None = None) -> int:
        from database import get_connection
        import json
        reading = self.read()
        with get_connection() as conn:
            dev = conn.execute(
                "SELECT id FROM ifs_integration_devices WHERE device_code=?", (self.device_code,)
            ).fetchone()
            if not dev:
                raise ValueError(f"Device {self.device_code} not registered")
            cur = conn.execute(
                """INSERT INTO ifs_integration_readings(device_id, reading_type, value_json, batch_ticket_id)
                   VALUES(?,?,?,?)""",
                (dev[0], reading.reading_type, json.dumps({"value": reading.value, "unit": reading.unit}),
                 batch_ticket_id),
            )
            return cur.lastrowid


def load_adapter(device_code: str) -> IndustrialDeviceAdapter:
    """Load adapter class from registry by device_code."""
    from database import get_connection
    import importlib
    with get_connection() as conn:
        row = conn.execute(
            "SELECT adapter_class, config_json FROM ifs_integration_devices WHERE device_code=? AND is_active=1",
            (device_code,),
        ).fetchone()
        if not row:
            raise ValueError(f"Device {device_code} not found")
        import json
        config = json.loads(row[1] or "{}")
        module_path, cls_name = row[0].rsplit(".", 1)
        mod = importlib.import_module(module_path)
        cls = getattr(mod, cls_name)
        return cls(device_code, config)
