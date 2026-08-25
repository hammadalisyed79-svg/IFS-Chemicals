# Integration Guide — V16.0

## Connector framework

Location: `integrations/connectors.py`

Each connector implements:
- `test_connection()` → `(bool, message)`
- `sync(direction)` → result dict
- Type-specific methods (e.g. `send_message` for messaging)

## Supported connector types (registry)

| Type slug | Class | Use case |
|-----------|-------|----------|
| shopify | ECommerceConnector | E-commerce orders/products |
| woocommerce | ECommerceConnector | WooCommerce store |
| amazon | ECommerceConnector | Marketplace |
| daraz | ECommerceConnector | Regional marketplace |
| whatsapp | MessagingConnector | WhatsApp Business |
| sms | MessagingConnector | SMS gateway |
| email | MessagingConnector | SMTP notifications |
| bank_api | BankingConnector | Bank statement sync |
| powerbi | BIConnector | Power BI datasets |
| excel | BIConnector | Excel export feeds |
| barcode_scanner | HardwareConnector | Warehouse scanning |
| label_printer | HardwareConnector | Label printing |
| biometric | HardwareConnector | Attendance devices |

## Register a connector

```python
from integrations.connectors import register_connector
cid = register_connector("shopify", "Main Store", {
    "api_url": "https://...",
    "api_key": "...",
})
```

Configs stored in `erp_integration_connectors` (inactive until `is_active=1`).

## Sync via jobs

```python
from infrastructure.jobs.worker import enqueue
enqueue("integration_sync", {"connector_id": cid})
```

Implement handler in worker for production sync pipelines.

## Design principles

- No vendor SDKs in core — connectors load config JSON only
- Credentials in `erp_config` or environment variables
- All sync results logged to `erp_domain_events`
