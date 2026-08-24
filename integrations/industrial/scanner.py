"""Generic barcode and QR scanner adapters."""

from integrations.industrial.base import IndustrialDeviceAdapter, DeviceReading
from datetime import datetime


class GenericBarcodeAdapter(IndustrialDeviceAdapter):
    def connect(self) -> bool:
        return True

    def disconnect(self) -> None:
        pass

    def read(self) -> DeviceReading:
        return DeviceReading(
            device_code=self.device_code,
            reading_type="barcode",
            value="",
            timestamp=datetime.now().isoformat(),
        )


class GenericQRAdapter(IndustrialDeviceAdapter):
    def connect(self) -> bool:
        return True

    def disconnect(self) -> None:
        pass

    def read(self) -> DeviceReading:
        return DeviceReading(
            device_code=self.device_code,
            reading_type="qr_code",
            value="",
            timestamp=datetime.now().isoformat(),
        )
