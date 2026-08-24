# API Documentation — IFS ERP V16

**Base URL:** `http://127.0.0.1:8600/api/v1/`  
**Interactive docs:** `/api/v1/docs` (Swagger UI)  
**OpenAPI JSON:** `/api/v1/openapi.json`  

---

## Authentication

OAuth2 password flow (JWT bearer tokens).

```http
POST /api/v1/auth/token
Content-Type: application/x-www-form-urlencoded

username=admin&password=admin123
```

Response:

```json
{
  "access_token": "<jwt>",
  "token_type": "bearer"
}
```

Use header: `Authorization: Bearer <jwt>`

Token lifetime: `security.jwt_expire_minutes` (default 60) in `erp_config`.

---

## Endpoints

| Method | Path | Tag | Description |
|--------|------|-----|-------------|
| POST | `/auth/token` | Auth | Login → JWT |
| GET | `/health` | Health | Service health |
| GET | `/customers` | Customers | List customers |
| GET | `/customers/{id}` | Customers | Get customer |
| GET | `/suppliers` | Suppliers | List suppliers |
| GET | `/products` | Products | List products |
| GET | `/inventory` | Inventory | Stock report |
| GET | `/sales/invoices` | Sales | Paginated sales invoices |
| GET | `/purchase/invoices` | Purchase | Paginated purchase invoices |
| GET | `/finance/trial-balance` | Finance | Trial balance |
| GET | `/production/orders` | Production | Production orders |
| GET | `/hr/employees` | HR | Employee list |
| GET | `/notifications` | Notifications | User notifications |
| GET | `/companies` | Multi-Company | Companies |
| GET | `/companies/{id}/branches` | Multi-Company | Branches |
| GET | `/reports/designs` | Reports | Saved report designs |
| GET | `/integrations/connectors` | Integrations | Connector registry |
| POST | `/jobs/process` | Jobs | Process job queue (admin) |

---

## Running the API

```bash
RUN_API.bat
# or
uvicorn api.main:app --host 127.0.0.1 --port 8600
```

Production: bind localhost only; expose via Nginx HTTPS reverse proxy.

---

## Error codes

| Code | Meaning |
|------|---------|
| 401 | Invalid/expired token |
| 403 | Insufficient permission |
| 404 | Resource not found |

---

## Versioning

Current: **v1**. Breaking changes will use `/api/v2/`.
