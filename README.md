# IFS Chemicals ERP

Complete offline ERP for **IFS Chemicals** — chemical, detergent, and raw material manufacturing & trading.

## Quick Start

```bash
cd "e:\MY ERPS"
pip install -r requirements.txt
python migrate.py          # safe schema upgrade (optional, runs on app start too)
streamlit run app.py
```

**Login:** username `admin` — password is **not** `admin123` (removed in V17.3).

After install or upgrade, run **`reset_admin_password.bat`** and open **`ADMIN_BOOTSTRAP.txt`** for credentials. Delete that file after signing in.

## Technology

- Python 3.9+
- Streamlit UI
- SQLite (`ifs_erp.db`) — fully offline
- Schema v3 with safe migration from v1/v2 (no data loss)

## Module Groups

| Group | Modules |
|-------|---------|
| **Overview** | Dashboard |
| **Master Data** | Customers, Suppliers, Products, Categories, UOM, Warehouses, Employees, Departments, Tax Rates, Payment Terms, Vehicles, Machines |
| **Sales** | Quotation → Sales Order → Delivery Note → Sales Invoice, Sale Return, Customer Outstanding |
| **Purchase** | Purchase Requisition → PO → GRN → Purchase Invoice, Purchase Return, Supplier Outstanding |
| **Inventory** | Stock, Adjustments, Weight Slips, Batch Stock, Stock Report |
| **Production** | BOM/Formula, Production Orders (issue → complete → QC) |
| **Finance** | Journal Voucher, Cash/Bank Books, Chart of Accounts, Ledgers, Trial Balance, P&L, Balance Sheet, Tax Report |
| **Admin** | Users, Roles & Permissions, System Settings |

## Key Features

### Products
- Item types: Raw Material, Packing, Finished Goods, Trading, Service
- Weight units: kg, gram, liter, ml, ton, piece, carton, bag, drum
- Standard weight, packing size, tax category, min/reorder stock

### Weight System
- Weight slips with first/second/tare/net weight
- Line-level net weight on sales/purchase documents
- Auto calc: qty × standard weight

### Taxation
- Sales tax, further tax, extra tax, WHT, exempt flag
- NTN/STRN on customers & suppliers
- Tax report

### Production & BOM
- Multi-line formulas with wastage %
- Approve / copy version
- Production order: material requirement, issue, FG receipt, costing, QC

### Accounting
- Double-entry GL postings on production steps
- Journal vouchers (balanced debit/credit)
- Extended chart of accounts (WIP, FG, ST payable/receivable, etc.)

### Security
- Login + roles with module permissions
- Audit columns: created/modified/posted by & date
- Posted document protection via status field
- `allow_negative_stock` system setting

### Export / Print
- CSV export on list/report screens
- HTML download for printing

## Files

| File | Purpose |
|------|---------|
| `app.py` | Main Streamlit application |
| `database.py` | Core DB layer (v2 + compat API) |
| `db_v3.py` | Schema v3 migration & extended logic |
| `schema.sql` | Base relational schema |
| `schema_v3.sql` | v3 additive tables |
| `migrate.py` | Standalone migration runner |
| `erp_ui/v3_pages.py` | New module UI pages |
| `ifs_erp.db` | SQLite database (auto-created) |

## Document Numbering

Auto-generated via `document_sequences`: CUS, SUP, ITM, PO, GRN, PUR, SO, DN, SAL, QT, JV, CR, CP, BOM, PRO, BAT, WS, etc.

## Migration Safety

- Existing data is **never deleted**
- v1 → v2: legacy tables renamed, data copied, legacy dropped after success
- v2 → v3: additive columns & tables only (`ALTER TABLE`, `CREATE IF NOT EXISTS`)
- Run `python migrate.py` before deploy or let `init_db()` run on app start

## Business Setup Order

1. Chart of Accounts (pre-seeded)
2. Tax Rates, UOM, Categories, Warehouses
3. Products / Items
4. Customers & Suppliers
5. BOM → Production (if manufacturing)
6. Purchase flow: PR → PO → GRN → Invoice
7. Sales flow: Quotation → SO → DN → Invoice

## License

Internal use — IFS Chemicals.
