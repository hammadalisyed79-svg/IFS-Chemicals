"""PART 10 — Industrial device validation."""

from __future__ import annotations

from tools.v17_2.common import ReportBundle, temp_database

DEVICE_CODES = (
    "PLC-01", "SCADA-01", "SCALE-01", "BARCODE-01", "QR-01", "LABEL-01", "THERMAL-01", "SENSOR-01",
)


def run_device_validation() -> ReportBundle:
    rep = ReportBundle("Industrial Device Validation — V17.2 (embedded)")
    db, path, _ = temp_database()
    try:
        from integrations.industrial.base import load_adapter, IndustrialDeviceAdapter
        with db.get_connection() as conn:
            rows = conn.execute("SELECT device_code, adapter_class FROM ifs_integration_devices").fetchall()
        rep.add("Registry", "Device count", "pass", f"{len(rows)} devices")

        for code in DEVICE_CODES:
            try:
                adapter = load_adapter(code)
                assert isinstance(adapter, IndustrialDeviceAdapter)
                adapter.connect()
                reading = adapter.read()
                rid = adapter.persist_reading()
                rep.add(code, "Adapter load/read/persist", "pass",
                        f"type={reading.reading_type} id={rid}")
            except Exception as exc:
                rep.add(code, "Adapter", "fail", str(exc)[:100])

        # Vendor neutrality
        classes = {r[1] for r in rows}
        vendor_locked = any("siemens" in c.lower() or "allen" in c.lower() for c in classes)
        rep.add("Vendor lock-in", "Generic adapters only", "pass" if not vendor_locked else "fail",
                str(classes))

    finally:
        import os
        os.unlink(path)

    rep.sections["Verdict"] = f"**{'DEVICE INTERFACES CERTIFIED' if rep.failed == 0 else 'NOT CERTIFIED'}** — generic adapter pattern."
    return rep
