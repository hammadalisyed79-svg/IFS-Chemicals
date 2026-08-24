"""Generic PLC adapter — protocol-agnostic stub for future vendor drivers."""

from integrations.industrial.base import IndustrialDeviceAdapter, DeviceReading
from datetime import datetime


class GenericPLCAdapter(IndustrialDeviceAdapter):
    def connect(self) -> bool:
        return True

    def disconnect(self) -> None:
        pass

    def read(self) -> DeviceReading:
        return DeviceReading(
            device_code=self.device_code,
            reading_type="plc_register",
            value={"status": "idle", "registers": {}},
            timestamp=datetime.now().isoformat(),
        )

    def write(self, payload: dict) -> bool:
        return True
