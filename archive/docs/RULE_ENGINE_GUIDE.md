# Rule Engine Guide — V17

## Overview

Business rules are stored in `erp_business_rules` and evaluated by `application/rules/engine.py`.

## Seeded rules (company 1)

| Code | Category | Purpose |
|------|----------|---------|
| CREDIT_LIMIT | credit_limit | Block when total exceeds limit |
| DISCOUNT_APPROVAL | discount | Require approval if discount > 10% |
| TAX_REQUIRED | tax | Tax rate required |
| NEGATIVE_STOCK | inventory | Stock guard |
| PRICE_MIN | price | Rate must be > 0 |

## Condition JSON

```json
{"field": "discount_pct", "op": "gt", "value": 10}
```

Operators: `eq`, `gt`, `gte`, `lt`, `lte`, `required`

Reference fields: `{"field": "total", "op": "lte", "ref": "customer.credit_limit"}`

## Action JSON

```json
{"action": "block", "message": "Credit limit exceeded"}
```

Actions: `block`, `require_approval` (with `level`)

## Usage in code

```python
from application.rules.engine import assert_rules, evaluate_rules

assert_rules("price", {"rate": line_rate}, company_id=1)
results = evaluate_rules("credit_limit", context, company_id=1)
```

## API

`GET /api/v1/rules?category=price`
