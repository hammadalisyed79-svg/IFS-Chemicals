# Workflow Designer Guide — V17

## Storage

Workflows are stored in `erp_workflow_definitions` as JSON.

## Default workflow

`sales_invoice` — Standard Sales Invoice (`SALES_INVOICE_STD`):

States: `draft` → `submitted` → `approved` / `rejected` → `posted`

## JSON structure

```json
{
  "states": ["draft", "submitted", "approved", "rejected", "posted"],
  "transitions": [
    {"from": "draft", "to": "submitted", "action": "submit"},
    {"from": "submitted", "to": "approved", "action": "approve", "approver_role": "SALES_MGR"},
    {"from": "submitted", "to": "rejected", "action": "reject"},
    {"from": "approved", "to": "posted", "action": "post"}
  ],
  "notifications": {"approved": "internal", "rejected": "creator"}
}
```

## API

- `GET /api/v1/workflows` — list definitions
- Runtime: `application/workflows/designer.py` — `apply_transition()`, `can_transition()`

## Admin usage

Administrators define workflows without code by updating `definition_json` via API or future admin UI (uses existing Approval Designer patterns — no UI redesign in V17).
