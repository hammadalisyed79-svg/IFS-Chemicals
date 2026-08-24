"""Generic SCADA adapter."""

from integrations.industrial.base import IndustrialDeviceAdapter, DeviceReading
from datetime import datetime


class GenericSCADAAdapter(IndustrialDeviceAdapter):
    def connect(self) -> bool:
        return True

    def disconnect(self) -> None:
        pass

    def read(self) -> DeviceReading:
        return DeviceReading(
            device_code=self.device_code,
            reading_type="scada_tags",
            value={"tags": {}, "alarms": []},
            timestamp=datetime.now().isoformat(),
        )
