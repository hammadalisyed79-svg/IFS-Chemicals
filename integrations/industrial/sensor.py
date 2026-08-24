"""Generic industrial sensor adapter."""

from integrations.industrial.base import IndustrialDeviceAdapter, DeviceReading
from datetime import datetime


class GenericSensorAdapter(IndustrialDeviceAdapter):
    def connect(self) -> bool:
        return True

    def disconnect(self) -> None:
        pass

    def read(self) -> DeviceReading:
        sensor_type = self.config.get("sensor_type", "temperature")
        return DeviceReading(
            device_code=self.device_code,
            reading_type=sensor_type,
            value=0.0,
            unit=self.config.get("unit"),
            timestamp=datetime.now().isoformat(),
        )
