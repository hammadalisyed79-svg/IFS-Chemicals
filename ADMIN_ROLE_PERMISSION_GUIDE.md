# Admin — Roles & Permissions Guide (V15)

## Enterprise roles

| Code | Name | Typical use |
|------|------|-------------|
| SUPER_ADMIN | Super Admin | Full access |
| DIRECTOR | Director | Executive read + approve |
| GM | General Manager | Cross-module management |
| FIN_MGR / ACCOUNTANT | Finance | GL, cash, bank |
| SALES_MGR / SALES_OFF | Sales | Orders, invoices, portal orders |
| PUR_MGR / PUR_OFF | Purchase | PO, GRN, PI |
| STORE_MGR / STORE_OFF | Inventory | Stock, warehouses |
| PROD_MGR / PROD_SUP / QC_OFF | Production | BOM, orders, QC |
| HR_MGR / PAYROLL_OFF | HR | Payroll, attendance |
| AUDITOR | Auditor | Read-only internal |
| DISTRIBUTOR / DIST_STAFF | Distributor | **Portal only** |
| VIEWER | Viewer | Read-only |

## Permission actions

| Action | Description |
|--------|-------------|
| View | See module screens |
| Add | Create new records |
| Edit | Modify drafts |
| Delete Draft | Remove unposted drafts |
| Approve / Reject | Workflow actions |
| Post | GL / stock posting |
| Print / Export | Reports |
| Admin Override | Sensitive admin bypass |

Matrix stored in `role_permission_matrix` (seeded on V15 migration).

## Create a distributor user

1. **Customers** — create customer; set distributor flags (or use **Price Lists → Distributor Assignment**).
2. **User Management** — create user with:
   - `user_type` = `distributor`
   - `linked_customer_id` = customer ID
   - Role = **Distributor**
   - Strong password (8+ chars, letter + digit)
3. Assign **price list** and **credit limit** under Masters → Price Lists.

## Manage portal orders

**Sales → Distributor Orders** — review, approve/reject, update status.

**Administration → Mobile Approvals** — quick approve from phone.

## Security administration

- Reset password via User Management
- Unlock account: clear `locked_until` and `failed_login_count` on user
- Review `login_attempts` and **Audit Log**
- Set `ssl_configured=1` after HTTPS deployment

## Desktop vs portal

| User type | Application |
|-----------|-------------|
| internal | `app.py` — full ERP |
| distributor | `portal_app.py` or auto-routed portal UI |

Distributors never see Finance, HR, Production, or other distributors' data.
