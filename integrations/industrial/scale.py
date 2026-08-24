"""Generic weighing scale adapter."""

from integrations.industrial.base import IndustrialDeviceAdapter, DeviceReading
from datetime import datetime


class GenericScaleAdapter(IndustrialDeviceAdapter):
    def connect(self) -> bool:
        return True

    def disconnect(self) -> None:
        pass

    def read(self) -> DeviceReading:
        return DeviceReading(
            device_code=self.device_code,
            reading_type="weight",
            value=0.0,
            unit=self.config.get("unit", "kg"),
            timestamp=datetime.now().isoformat(),
        )
