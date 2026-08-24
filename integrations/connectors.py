"""Integration connector framework — vendor-agnostic interfaces."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any


class Connector(ABC):
    connector_type: str = "base"

    def __init__(self, connector_id: int, name: str, config: dict[str, Any]):
        self.connector_id = connector_id
        self.name = name
        self.config = config

    @abstractmethod
    def test_connection(self) -> tuple[bool, str]:
        ...

    @abstractmethod
    def sync(self, direction: str = "pull") -> dict:
        ...


class ECommerceConnector(Connector):
    connector_type = "ecommerce"

    def test_connection(self) -> tuple[bool, str]:
        return bool(self.config.get("api_url")), "API URL required"

    def sync(self, direction: str = "pull") -> dict:
        return {"status": "not_configured", "direction": direction}


class MessagingConnector(Connector):
    connector_type = "messaging"

    def test_connection(self) -> tuple[bool, str]:
        return True, "OK"

    def send_message(self, to: str, body: str) -> dict:
        raise NotImplementedError

    def sync(self, direction: str = "pull") -> dict:
        return {"sent": 0}


class BankingConnector(Connector):
    connector_type = "banking"

    def test_connection(self) -> tuple[bool, str]:
        return bool(self.config.get("account_id")), "account_id required"

    def sync(self, direction: str = "pull") -> dict:
        return {"transactions": []}


class BIConnector(Connector):
    connector_type = "bi"

    def test_connection(self) -> tuple[bool, str]:
        return True, "OK"

    def export_dataset(self, dataset: str) -> dict:
        return {"dataset": dataset, "rows": 0}

    def sync(self, direction: str = "pull") -> dict:
        return self.export_dataset(self.config.get("dataset", "default"))


class HardwareConnector(Connector):
    connector_type = "hardware"

    def test_connection(self) -> tuple[bool, str]:
        return bool(self.config.get("device_path") or self.config.get("ip")), "device required"

    def sync(self, direction: str = "pull") -> dict:
        return {"device": self.name, "status": "ready"}


# Registry maps connector_type slug → implementation class
CONNECTOR_REGISTRY: dict[str, type[Connector]] = {
    "shopify": ECommerceConnector,
    "woocommerce": ECommerceConnector,
    "amazon": ECommerceConnector,
    "daraz": ECommerceConnector,
    "whatsapp": MessagingConnector,
    "sms": MessagingConnector,
    "email": MessagingConnector,
    "bank_api": BankingConnector,
    "powerbi": BIConnector,
    "excel": BIConnector,
    "barcode_scanner": HardwareConnector,
    "label_printer": HardwareConnector,
    "biometric": HardwareConnector,
}


def load_connector(connector_id: int) -> Connector | None:
    from database import get_connection, row_to_dict
    with get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM erp_integration_connectors WHERE id=? AND is_active=1", (connector_id,)
        ).fetchone()
        if not row:
            return None
        rec = row_to_dict(row)
    cfg = json.loads(rec.get("config_json") or "{}")
    cls = CONNECTOR_REGISTRY.get(rec["connector_type"], ECommerceConnector)
    return cls(connector_id, rec["name"], cfg)


def register_connector(connector_type: str, name: str, config: dict, company_id: int = 1) -> int:
    from database import get_connection
    with get_connection() as conn:
        cur = conn.execute(
            """INSERT INTO erp_integration_connectors(connector_type,name,config_json,company_id,is_active)
               VALUES(?,?,?,?,0)""",
            (connector_type, name, json.dumps(config), company_id),
        )
        return cur.lastrowid
