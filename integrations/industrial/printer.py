"""Generic label and thermal printer adapters."""

from integrations.industrial.base import IndustrialDeviceAdapter, DeviceReading
from datetime import datetime


class GenericLabelPrinterAdapter(IndustrialDeviceAdapter):
    def connect(self) -> bool:
        return True

    def disconnect(self) -> None:
        pass

    def read(self) -> DeviceReading:
        return DeviceReading(device_code=self.device_code, reading_type="printer_status",
                               value={"ready": True}, timestamp=datetime.now().isoformat())

    def write(self, payload: dict) -> bool:
        """Print label — payload: {template, data}."""
        return True


class GenericThermalPrinterAdapter(IndustrialDeviceAdapter):
    def connect(self) -> bool:
        return True

    def disconnect(self) -> None:
        pass

    def read(self) -> DeviceReading:
        return DeviceReading(device_code=self.device_code, reading_type="printer_status",
                               value={"ready": True}, timestamp=datetime.now().isoformat())

    def write(self, payload: dict) -> bool:
        return True
