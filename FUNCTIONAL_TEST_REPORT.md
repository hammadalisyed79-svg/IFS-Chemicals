# Functional Test Report — V17.3

**Generated:** 2026-07-02 11:12:18
**Tool:** `tools/generate_v17_3_certification.py`

## Summary

| Metric | Count |
|--------|------:|
| Pass | 169 |
| Fail | 622 |
| Pass rate | 21.4% |

## Methodology

V17.3: route registration, service read, API CRUD, Playwright smoke for Open on key screens. Unautomated UI actions marked **FAIL**.

## V17.3

All items normalized to **PASS** or **FAIL** only.

## Detailed Results

| Status | Category | Check | Detail |
|--------|----------|-------|--------|
| pass | Infrastructure | Database init | init_db 1245.0ms |
| pass | Infrastructure | Playwright smoke | tests/e2e/test_ui_playwright.py |
| pass | Dashboard | Route callable | <function page_dashboard at 0x0000021DA467B920> |
| fail | Dashboard | Service read | No automated service test |
| pass | Dashboard | Permission (admin view) | Masters |
| pass | Dashboard | Open | Playwright navigation smoke |
| fail | Dashboard | Print | Not automated in Playwright suite |
| fail | Dashboard | Export PDF | Not automated in Playwright suite |
| fail | Dashboard | Export Excel | Not automated in Playwright suite |
| fail | Dashboard | Pagination | Not automated in Playwright suite |
| fail | Dashboard | Sorting | Not automated in Playwright suite |
| fail | Dashboard | Filters | Not automated in Playwright suite |
| pass | Business Overview | Route callable | <function page_business_overview at 0x0000021DA467B9C0> |
| fail | Business Overview | Service read | No automated service test |
| pass | Business Overview | Permission (admin view) | Masters |
| fail | Business Overview | Open | Not automated in Playwright suite |
| fail | Business Overview | Print | Not automated in Playwright suite |
| fail | Business Overview | Export PDF | Not automated in Playwright suite |
| fail | Business Overview | Export Excel | Not automated in Playwright suite |
| fail | Business Overview | Pagination | Not automated in Playwright suite |
| fail | Business Overview | Sorting | Not automated in Playwright suite |
| fail | Business Overview | Filters | Not automated in Playwright suite |
| pass | Customers | Route callable | <function page_customers at 0x0000021DA467BA60> |
| pass | Customers | Service read | CustomerService.list_active() OK |
| pass | Customers | API list | 87.95ms |
| pass | Customers | Create | {"id":1} |
| pass | Customers | Edit | id=1 |
| pass | Customers | Delete draft | API delete OK |
| pass | Customers | Permission (admin view) | Masters |
| pass | Customers | Open | Playwright navigation smoke |
| fail | Customers | Print | Not automated in Playwright suite |
| fail | Customers | Export PDF | Not automated in Playwright suite |
| fail | Customers | Export Excel | Not automated in Playwright suite |
| fail | Customers | Pagination | Not automated in Playwright suite |
| fail | Customers | Sorting | Not automated in Playwright suite |
| fail | Customers | Filters | Not automated in Playwright suite |
| fail | Customers | Approve | Workflow not fully automated for this screen |
| fail | Customers | Reject | Workflow not fully automated for this screen |
| fail | Customers | Post | Workflow not fully automated for this screen |
| fail | Customers | Reverse | Workflow not fully automated for this screen |
| pass | Suppliers | Route callable | <function page_suppliers at 0x0000021DA467BB00> |
| fail | Suppliers | Service read | No automated service test |
| pass | Suppliers | Create | id=1 |
| fail | Suppliers | Edit | No automated edit path without UI |
| pass | Suppliers | Permission (admin view) | Masters |
| fail | Suppliers | Open | Not automated in Playwright suite |
| fail | Suppliers | Print | Not automated in Playwright suite |
| fail | Suppliers | Export PDF | Not automated in Playwright suite |
| fail | Suppliers | Export Excel | Not automated in Playwright suite |
| fail | Suppliers | Pagination | Not automated in Playwright suite |
| fail | Suppliers | Sorting | Not automated in Playwright suite |
| fail | Suppliers | Filters | Not automated in Playwright suite |
| pass | Products | Route callable | <function page_items at 0x0000021DA467BBA0> |
| fail | Products | Service read | No automated service test |
| pass | Products | Create | id=1 |
| pass | Products | Permission (admin view) | Masters |
| fail | Products | Open | Not automated in Playwright suite |
| fail | Products | Print | Not automated in Playwright suite |
| fail | Products | Export PDF | Not automated in Playwright suite |
| fail | Products | Export Excel | Not automated in Playwright suite |
| fail | Products | Pagination | Not automated in Playwright suite |
| fail | Products | Sorting | Not automated in Playwright suite |
| fail | Products | Filters | Not automated in Playwright suite |
| pass | Account & Item Groups | Route callable | <function page_master_groups at 0x0000021DA44AF060> |
| fail | Account & Item Groups | Service read | No automated service test |
| pass | Account & Item Groups | Permission (admin view) | Masters |
| fail | Account & Item Groups | Open | Not automated in Playwright suite |
| fail | Account & Item Groups | Print | Not automated in Playwright suite |
| fail | Account & Item Groups | Export PDF | Not automated in Playwright suite |
| fail | Account & Item Groups | Export Excel | Not automated in Playwright suite |
| fail | Account & Item Groups | Pagination | Not automated in Playwright suite |
| fail | Account & Item Groups | Sorting | Not automated in Playwright suite |
| fail | Account & Item Groups | Filters | Not automated in Playwright suite |
| pass | Warehouses | Route callable | <function page_warehouses at 0x0000021DA43E8400> |
| fail | Warehouses | Service read | No automated service test |
| pass | Warehouses | Permission (admin view) | Masters |
| fail | Warehouses | Open | Not automated in Playwright suite |
| fail | Warehouses | Print | Not automated in Playwright suite |
| fail | Warehouses | Export PDF | Not automated in Playwright suite |
| fail | Warehouses | Export Excel | Not automated in Playwright suite |
| fail | Warehouses | Pagination | Not automated in Playwright suite |
| fail | Warehouses | Sorting | Not automated in Playwright suite |
| fail | Warehouses | Filters | Not automated in Playwright suite |
| pass | Employees | Route callable | <function page_hr_employees at 0x0000021DA43EA340> |
| fail | Employees | Service read | No automated service test |
| pass | Employees | Permission (admin view) | Masters |
| fail | Employees | Open | Not automated in Playwright suite |
| fail | Employees | Print | Not automated in Playwright suite |
| fail | Employees | Export PDF | Not automated in Playwright suite |
| fail | Employees | Export Excel | Not automated in Playwright suite |
| fail | Employees | Pagination | Not automated in Playwright suite |
| fail | Employees | Sorting | Not automated in Playwright suite |
| fail | Employees | Filters | Not automated in Playwright suite |
| pass | Price Lists | Route callable | <function page_price_lists at 0x0000021DA44FC680> |
| fail | Price Lists | Service read | No automated service test |
| pass | Price Lists | Permission (admin view) | Masters |
| fail | Price Lists | Open | Not automated in Playwright suite |
| fail | Price Lists | Print | Not automated in Playwright suite |
| fail | Price Lists | Export PDF | Not automated in Playwright suite |
| fail | Price Lists | Export Excel | Not automated in Playwright suite |
| fail | Price Lists | Pagination | Not automated in Playwright suite |
| fail | Price Lists | Sorting | Not automated in Playwright suite |
| fail | Price Lists | Filters | Not automated in Playwright suite |
| pass | Sales Invoices | Route callable | <function page_sales at 0x0000021DA467BD80> |
| fail | Sales Invoices | Service read | No automated service test |
| pass | Sales Invoices | Permission (admin view) | Sales |
| fail | Sales Invoices | Open | Not automated in Playwright suite |
| fail | Sales Invoices | Print | Not automated in Playwright suite |
| fail | Sales Invoices | Export PDF | Not automated in Playwright suite |
| fail | Sales Invoices | Export Excel | Not automated in Playwright suite |
| fail | Sales Invoices | Pagination | Not automated in Playwright suite |
| fail | Sales Invoices | Sorting | Not automated in Playwright suite |
| fail | Sales Invoices | Filters | Not automated in Playwright suite |
| pass | Sale Approval | Route callable | <function page_sale_approval at 0x0000021DA44672E0> |
| fail | Sale Approval | Service read | No automated service test |
| pass | Sale Approval | Permission (admin view) | Masters |
| fail | Sale Approval | Open | Not automated in Playwright suite |
| fail | Sale Approval | Print | Not automated in Playwright suite |
| fail | Sale Approval | Export PDF | Not automated in Playwright suite |
| fail | Sale Approval | Export Excel | Not automated in Playwright suite |
| fail | Sale Approval | Pagination | Not automated in Playwright suite |
| fail | Sale Approval | Sorting | Not automated in Playwright suite |
| fail | Sale Approval | Filters | Not automated in Playwright suite |
| pass | Sales Returns | Route callable | <function page_sale_return at 0x0000021DA467BEC0> |
| fail | Sales Returns | Service read | No automated service test |
| pass | Sales Returns | Permission (admin view) | Sales |
| fail | Sales Returns | Open | Not automated in Playwright suite |
| fail | Sales Returns | Print | Not automated in Playwright suite |
| fail | Sales Returns | Export PDF | Not automated in Playwright suite |
| fail | Sales Returns | Export Excel | Not automated in Playwright suite |
| fail | Sales Returns | Pagination | Not automated in Playwright suite |
| fail | Sales Returns | Sorting | Not automated in Playwright suite |
| fail | Sales Returns | Filters | Not automated in Playwright suite |
| pass | Sales Orders | Route callable | <function page_sales_orders at 0x0000021DA43E8EA0> |
| fail | Sales Orders | Service read | No automated service test |
| pass | Sales Orders | Permission (admin view) | Sales |
| fail | Sales Orders | Open | Not automated in Playwright suite |
| fail | Sales Orders | Print | Not automated in Playwright suite |
| fail | Sales Orders | Export PDF | Not automated in Playwright suite |
| fail | Sales Orders | Export Excel | Not automated in Playwright suite |
| fail | Sales Orders | Pagination | Not automated in Playwright suite |
| fail | Sales Orders | Sorting | Not automated in Playwright suite |
| fail | Sales Orders | Filters | Not automated in Playwright suite |
| pass | Quotations | Route callable | <function page_quotations at 0x0000021DA43E8E00> |
| fail | Quotations | Service read | No automated service test |
| pass | Quotations | Permission (admin view) | Masters |
| fail | Quotations | Open | Not automated in Playwright suite |
| fail | Quotations | Print | Not automated in Playwright suite |
| fail | Quotations | Export PDF | Not automated in Playwright suite |
| fail | Quotations | Export Excel | Not automated in Playwright suite |
| fail | Quotations | Pagination | Not automated in Playwright suite |
| fail | Quotations | Sorting | Not automated in Playwright suite |
| fail | Quotations | Filters | Not automated in Playwright suite |
| pass | Distributor Orders | Route callable | <function page_distributor_orders at 0x0000021DA44FC9A0> |
| fail | Distributor Orders | Service read | No automated service test |
| pass | Distributor Orders | Permission (admin view) | Masters |
| fail | Distributor Orders | Open | Not automated in Playwright suite |
| fail | Distributor Orders | Print | Not automated in Playwright suite |
| fail | Distributor Orders | Export PDF | Not automated in Playwright suite |
| fail | Distributor Orders | Export Excel | Not automated in Playwright suite |
| fail | Distributor Orders | Pagination | Not automated in Playwright suite |
| fail | Distributor Orders | Sorting | Not automated in Playwright suite |
| fail | Distributor Orders | Filters | Not automated in Playwright suite |
| pass | Purchase Invoices | Route callable | <function page_purchases at 0x0000021DA467BCE0> |
| fail | Purchase Invoices | Service read | No automated service test |
| pass | Purchase Invoices | Permission (admin view) | Masters |
| fail | Purchase Invoices | Open | Not automated in Playwright suite |
| fail | Purchase Invoices | Print | Not automated in Playwright suite |
| fail | Purchase Invoices | Export PDF | Not automated in Playwright suite |
| fail | Purchase Invoices | Export Excel | Not automated in Playwright suite |
| fail | Purchase Invoices | Pagination | Not automated in Playwright suite |
| fail | Purchase Invoices | Sorting | Not automated in Playwright suite |
| fail | Purchase Invoices | Filters | Not automated in Playwright suite |
| pass | Purchase Approval | Route callable | <function page_purchase_approval at 0x0000021DA4467420> |
| fail | Purchase Approval | Service read | No automated service test |
| pass | Purchase Approval | Permission (admin view) | Masters |
| fail | Purchase Approval | Open | Not automated in Playwright suite |
| fail | Purchase Approval | Print | Not automated in Playwright suite |
| fail | Purchase Approval | Export PDF | Not automated in Playwright suite |
| fail | Purchase Approval | Export Excel | Not automated in Playwright suite |
| fail | Purchase Approval | Pagination | Not automated in Playwright suite |
| fail | Purchase Approval | Sorting | Not automated in Playwright suite |
| fail | Purchase Approval | Filters | Not automated in Playwright suite |
| pass | Purchase Returns | Route callable | <function page_purchase_return at 0x0000021DA467BE20> |
| fail | Purchase Returns | Service read | No automated service test |
| pass | Purchase Returns | Permission (admin view) | Masters |
| fail | Purchase Returns | Open | Not automated in Playwright suite |
| fail | Purchase Returns | Print | Not automated in Playwright suite |
| fail | Purchase Returns | Export PDF | Not automated in Playwright suite |
| fail | Purchase Returns | Export Excel | Not automated in Playwright suite |
| fail | Purchase Returns | Pagination | Not automated in Playwright suite |
| fail | Purchase Returns | Sorting | Not automated in Playwright suite |
| fail | Purchase Returns | Filters | Not automated in Playwright suite |
| pass | GRN | Route callable | <function page_grn at 0x0000021DA43E9120> |
| fail | GRN | Service read | No automated service test |
| pass | GRN | Permission (admin view) | Masters |
| fail | GRN | Open | Not automated in Playwright suite |
| fail | GRN | Print | Not automated in Playwright suite |
| fail | GRN | Export PDF | Not automated in Playwright suite |
| fail | GRN | Export Excel | Not automated in Playwright suite |
| fail | GRN | Pagination | Not automated in Playwright suite |
| fail | GRN | Sorting | Not automated in Playwright suite |
| fail | GRN | Filters | Not automated in Playwright suite |
| pass | Purchase Orders | Route callable | <function page_purchase_orders at 0x0000021DA43E9080> |
| fail | Purchase Orders | Service read | No automated service test |
| pass | Purchase Orders | Permission (admin view) | Masters |
| fail | Purchase Orders | Open | Not automated in Playwright suite |
| fail | Purchase Orders | Print | Not automated in Playwright suite |
| fail | Purchase Orders | Export PDF | Not automated in Playwright suite |
| fail | Purchase Orders | Export Excel | Not automated in Playwright suite |
| fail | Purchase Orders | Pagination | Not automated in Playwright suite |
| fail | Purchase Orders | Sorting | Not automated in Playwright suite |
| fail | Purchase Orders | Filters | Not automated in Playwright suite |
| pass | Stock | Route callable | <function page_stock at 0x0000021DA46A82C0> |
| fail | Stock | Service read | No automated service test |
| pass | Stock | Permission (admin view) | Masters |
| fail | Stock | Open | Not automated in Playwright suite |
| fail | Stock | Print | Not automated in Playwright suite |
| fail | Stock | Export PDF | Not automated in Playwright suite |
| fail | Stock | Export Excel | Not automated in Playwright suite |
| fail | Stock | Pagination | Not automated in Playwright suite |
| fail | Stock | Sorting | Not automated in Playwright suite |
| fail | Stock | Filters | Not automated in Playwright suite |
| pass | Stock Adjustments | Route callable | <function page_stock_adjustments at 0x0000021DA46A8360> |
| fail | Stock Adjustments | Service read | No automated service test |
| pass | Stock Adjustments | Permission (admin view) | Masters |
| fail | Stock Adjustments | Open | Not automated in Playwright suite |
| fail | Stock Adjustments | Print | Not automated in Playwright suite |
| fail | Stock Adjustments | Export PDF | Not automated in Playwright suite |
| fail | Stock Adjustments | Export Excel | Not automated in Playwright suite |
| fail | Stock Adjustments | Pagination | Not automated in Playwright suite |
| fail | Stock Adjustments | Sorting | Not automated in Playwright suite |
| fail | Stock Adjustments | Filters | Not automated in Playwright suite |
| pass | Stock Report | Route callable | <function page_stock_report at 0x0000021DA46A80E0> |
| fail | Stock Report | Service read | No automated service test |
| pass | Stock Report | Permission (admin view) | Masters |
| fail | Stock Report | Open | Not automated in Playwright suite |
| fail | Stock Report | Print | Not automated in Playwright suite |
| fail | Stock Report | Export PDF | Not automated in Playwright suite |
| fail | Stock Report | Export Excel | Not automated in Playwright suite |
| fail | Stock Report | Pagination | Not automated in Playwright suite |
| fail | Stock Report | Sorting | Not automated in Playwright suite |
| fail | Stock Report | Filters | Not automated in Playwright suite |
| pass | BOM | Route callable | <function page_bom_composition at 0x0000021DA4465120> |
| fail | BOM | Service read | No automated service test |
| pass | BOM | Permission (admin view) | Production |
| fail | BOM | Open | Not automated in Playwright suite |
| fail | BOM | Print | Not automated in Playwright suite |
| fail | BOM | Export PDF | Not automated in Playwright suite |
| fail | BOM | Export Excel | Not automated in Playwright suite |
| fail | BOM | Pagination | Not automated in Playwright suite |
| fail | BOM | Sorting | Not automated in Playwright suite |
| fail | BOM | Filters | Not automated in Playwright suite |
| pass | Production Orders | Route callable | <function page_production_orders at 0x0000021DA44651C0> |
| fail | Production Orders | Service read | No automated service test |
| pass | Production Orders | Permission (admin view) | Masters |
| fail | Production Orders | Open | Not automated in Playwright suite |
| fail | Production Orders | Print | Not automated in Playwright suite |
| fail | Production Orders | Export PDF | Not automated in Playwright suite |
| fail | Production Orders | Export Excel | Not automated in Playwright suite |
| fail | Production Orders | Pagination | Not automated in Playwright suite |
| fail | Production Orders | Sorting | Not automated in Playwright suite |
| fail | Production Orders | Filters | Not automated in Playwright suite |
| pass | Job Cards | Route callable | <function page_job_cards at 0x0000021DA4465B20> |
| fail | Job Cards | Service read | No automated service test |
| pass | Job Cards | Permission (admin view) | Masters |
| fail | Job Cards | Open | Not automated in Playwright suite |
| fail | Job Cards | Print | Not automated in Playwright suite |
| fail | Job Cards | Export PDF | Not automated in Playwright suite |
| fail | Job Cards | Export Excel | Not automated in Playwright suite |
| fail | Job Cards | Pagination | Not automated in Playwright suite |
| fail | Job Cards | Sorting | Not automated in Playwright suite |
| fail | Job Cards | Filters | Not automated in Playwright suite |
| pass | Machines | Route callable | <function page_machines at 0x0000021DA43E87C0> |
| fail | Machines | Service read | No automated service test |
| pass | Machines | Permission (admin view) | Masters |
| fail | Machines | Open | Not automated in Playwright suite |
| fail | Machines | Print | Not automated in Playwright suite |
| fail | Machines | Export PDF | Not automated in Playwright suite |
| fail | Machines | Export Excel | Not automated in Playwright suite |
| fail | Machines | Pagination | Not automated in Playwright suite |
| fail | Machines | Sorting | Not automated in Playwright suite |
| fail | Machines | Filters | Not automated in Playwright suite |
| pass | Formula Master | Route callable | <function page_formulation at 0x0000021DA452FD80> |
| pass | Formula Master | Service read | FormulationService.list_formulas() OK |
| pass | Formula Master | Permission (admin view) | Masters |
| fail | Formula Master | Open | Not automated in Playwright suite |
| fail | Formula Master | Print | Not automated in Playwright suite |
| fail | Formula Master | Export PDF | Not automated in Playwright suite |
| fail | Formula Master | Export Excel | Not automated in Playwright suite |
| fail | Formula Master | Pagination | Not automated in Playwright suite |
| fail | Formula Master | Sorting | Not automated in Playwright suite |
| fail | Formula Master | Filters | Not automated in Playwright suite |
| fail | Formula Master | Approve | Workflow not fully automated for this screen |
| fail | Formula Master | Reject | Workflow not fully automated for this screen |
| fail | Formula Master | Post | Workflow not fully automated for this screen |
| fail | Formula Master | Reverse | Workflow not fully automated for this screen |
| pass | Spray Dryer | Route callable | <function page_spray_dryer at 0x0000021DA452FE20> |
| pass | Spray Dryer | Service read | SprayDryerService.list_batches() OK |
| pass | Spray Dryer | Permission (admin view) | Production |
| fail | Spray Dryer | Open | Not automated in Playwright suite |
| fail | Spray Dryer | Print | Not automated in Playwright suite |
| fail | Spray Dryer | Export PDF | Not automated in Playwright suite |
| fail | Spray Dryer | Export Excel | Not automated in Playwright suite |
| fail | Spray Dryer | Pagination | Not automated in Playwright suite |
| fail | Spray Dryer | Sorting | Not automated in Playwright suite |
| fail | Spray Dryer | Filters | Not automated in Playwright suite |
| fail | Spray Dryer | Approve | Workflow not fully automated for this screen |
| fail | Spray Dryer | Reject | Workflow not fully automated for this screen |
| fail | Spray Dryer | Post | Workflow not fully automated for this screen |
| fail | Spray Dryer | Reverse | Workflow not fully automated for this screen |
| pass | Batch Manufacturing | Route callable | <function page_batch_manufacturing at 0x0000021DA452FEC0> |
| fail | Batch Manufacturing | Service read | No automated service test |
| pass | Batch Manufacturing | Permission (admin view) | Masters |
| fail | Batch Manufacturing | Open | Not automated in Playwright suite |
| fail | Batch Manufacturing | Print | Not automated in Playwright suite |
| fail | Batch Manufacturing | Export PDF | Not automated in Playwright suite |
| fail | Batch Manufacturing | Export Excel | Not automated in Playwright suite |
| fail | Batch Manufacturing | Pagination | Not automated in Playwright suite |
| fail | Batch Manufacturing | Sorting | Not automated in Playwright suite |
| fail | Batch Manufacturing | Filters | Not automated in Playwright suite |
| pass | Chemical Reactor | Route callable | <function page_reactor at 0x0000021DA452FF60> |
| fail | Chemical Reactor | Service read | No automated service test |
| pass | Chemical Reactor | Permission (admin view) | Masters |
| fail | Chemical Reactor | Open | Not automated in Playwright suite |
| fail | Chemical Reactor | Print | Not automated in Playwright suite |
| fail | Chemical Reactor | Export PDF | Not automated in Playwright suite |
| fail | Chemical Reactor | Export Excel | Not automated in Playwright suite |
| fail | Chemical Reactor | Pagination | Not automated in Playwright suite |
| fail | Chemical Reactor | Sorting | Not automated in Playwright suite |
| fail | Chemical Reactor | Filters | Not automated in Playwright suite |
| pass | Corrugated Production | Route callable | <function page_corrugated at 0x0000021DA4544040> |
| fail | Corrugated Production | Service read | No automated service test |
| pass | Corrugated Production | Permission (admin view) | Masters |
| fail | Corrugated Production | Open | Not automated in Playwright suite |
| fail | Corrugated Production | Print | Not automated in Playwright suite |
| fail | Corrugated Production | Export PDF | Not automated in Playwright suite |
| fail | Corrugated Production | Export Excel | Not automated in Playwright suite |
| fail | Corrugated Production | Pagination | Not automated in Playwright suite |
| fail | Corrugated Production | Sorting | Not automated in Playwright suite |
| fail | Corrugated Production | Filters | Not automated in Playwright suite |
| pass | Gravure / Packaging | Route callable | <function page_gravure_packaging at 0x0000021DA45440E0> |
| fail | Gravure / Packaging | Service read | No automated service test |
| pass | Gravure / Packaging | Permission (admin view) | Masters |
| fail | Gravure / Packaging | Open | Not automated in Playwright suite |
| fail | Gravure / Packaging | Print | Not automated in Playwright suite |
| fail | Gravure / Packaging | Export PDF | Not automated in Playwright suite |
| fail | Gravure / Packaging | Export Excel | Not automated in Playwright suite |
| fail | Gravure / Packaging | Pagination | Not automated in Playwright suite |
| fail | Gravure / Packaging | Sorting | Not automated in Playwright suite |
| fail | Gravure / Packaging | Filters | Not automated in Playwright suite |
| pass | PET Bottle Blowing | Route callable | <function page_pet_blowing at 0x0000021DA4544180> |
| fail | PET Bottle Blowing | Service read | No automated service test |
| pass | PET Bottle Blowing | Permission (admin view) | Masters |
| fail | PET Bottle Blowing | Open | Not automated in Playwright suite |
| fail | PET Bottle Blowing | Print | Not automated in Playwright suite |
| fail | PET Bottle Blowing | Export PDF | Not automated in Playwright suite |
| fail | PET Bottle Blowing | Export Excel | Not automated in Playwright suite |
| fail | PET Bottle Blowing | Pagination | Not automated in Playwright suite |
| fail | PET Bottle Blowing | Sorting | Not automated in Playwright suite |
| fail | PET Bottle Blowing | Filters | Not automated in Playwright suite |
| pass | QC Laboratory | Route callable | <function page_qc_lab at 0x0000021DA4544220> |
| pass | QC Laboratory | Service read | QCLabService.list_specs() OK |
| pass | QC Laboratory | Permission (admin view) | Masters |
| fail | QC Laboratory | Open | Not automated in Playwright suite |
| fail | QC Laboratory | Print | Not automated in Playwright suite |
| fail | QC Laboratory | Export PDF | Not automated in Playwright suite |
| fail | QC Laboratory | Export Excel | Not automated in Playwright suite |
| fail | QC Laboratory | Pagination | Not automated in Playwright suite |
| fail | QC Laboratory | Sorting | Not automated in Playwright suite |
| fail | QC Laboratory | Filters | Not automated in Playwright suite |
| fail | QC Laboratory | Approve | Workflow not fully automated for this screen |
| fail | QC Laboratory | Reject | Workflow not fully automated for this screen |
| fail | QC Laboratory | Post | Workflow not fully automated for this screen |
| fail | QC Laboratory | Reverse | Workflow not fully automated for this screen |
| pass | Plant Maintenance | Route callable | <function page_plant_maintenance at 0x0000021DA45442C0> |
| fail | Plant Maintenance | Service read | No automated service test |
| pass | Plant Maintenance | Permission (admin view) | Masters |
| fail | Plant Maintenance | Open | Not automated in Playwright suite |
| fail | Plant Maintenance | Print | Not automated in Playwright suite |
| fail | Plant Maintenance | Export PDF | Not automated in Playwright suite |
| fail | Plant Maintenance | Export Excel | Not automated in Playwright suite |
| fail | Plant Maintenance | Pagination | Not automated in Playwright suite |
| fail | Plant Maintenance | Sorting | Not automated in Playwright suite |
| fail | Plant Maintenance | Filters | Not automated in Playwright suite |
| pass | Energy Management | Route callable | <function page_energy at 0x0000021DA4544360> |
| fail | Energy Management | Service read | No automated service test |
| pass | Energy Management | Permission (admin view) | Masters |
| fail | Energy Management | Open | Not automated in Playwright suite |
| fail | Energy Management | Print | Not automated in Playwright suite |
| fail | Energy Management | Export PDF | Not automated in Playwright suite |
| fail | Energy Management | Export Excel | Not automated in Playwright suite |
| fail | Energy Management | Pagination | Not automated in Playwright suite |
| fail | Energy Management | Sorting | Not automated in Playwright suite |
| fail | Energy Management | Filters | Not automated in Playwright suite |
| pass | Industrial Costing | Route callable | <function page_industrial_costing at 0x0000021DA4544400> |
| fail | Industrial Costing | Service read | No automated service test |
| pass | Industrial Costing | Permission (admin view) | Masters |
| fail | Industrial Costing | Open | Not automated in Playwright suite |
| fail | Industrial Costing | Print | Not automated in Playwright suite |
| fail | Industrial Costing | Export PDF | Not automated in Playwright suite |
| fail | Industrial Costing | Export Excel | Not automated in Playwright suite |
| fail | Industrial Costing | Pagination | Not automated in Playwright suite |
| fail | Industrial Costing | Sorting | Not automated in Playwright suite |
| fail | Industrial Costing | Filters | Not automated in Playwright suite |
| pass | Toll Manufacturing | Route callable | <function page_toll_manufacturing at 0x0000021DA45444A0> |
| fail | Toll Manufacturing | Service read | No automated service test |
| pass | Toll Manufacturing | Permission (admin view) | Masters |
| fail | Toll Manufacturing | Open | Not automated in Playwright suite |
| fail | Toll Manufacturing | Print | Not automated in Playwright suite |
| fail | Toll Manufacturing | Export PDF | Not automated in Playwright suite |
| fail | Toll Manufacturing | Export Excel | Not automated in Playwright suite |
| fail | Toll Manufacturing | Pagination | Not automated in Playwright suite |
| fail | Toll Manufacturing | Sorting | Not automated in Playwright suite |
| fail | Toll Manufacturing | Filters | Not automated in Playwright suite |
| pass | Industrial Warehouse | Route callable | <function page_industrial_warehouse at 0x0000021DA4544540> |
| fail | Industrial Warehouse | Service read | No automated service test |
| pass | Industrial Warehouse | Permission (admin view) | Masters |
| fail | Industrial Warehouse | Open | Not automated in Playwright suite |
| fail | Industrial Warehouse | Print | Not automated in Playwright suite |
| fail | Industrial Warehouse | Export PDF | Not automated in Playwright suite |
| fail | Industrial Warehouse | Export Excel | Not automated in Playwright suite |
| fail | Industrial Warehouse | Pagination | Not automated in Playwright suite |
| fail | Industrial Warehouse | Sorting | Not automated in Playwright suite |
| fail | Industrial Warehouse | Filters | Not automated in Playwright suite |
| pass | Industrial Dashboards | Route callable | <function page_industrial_dashboards at 0x0000021DA45445E0> |
| pass | Industrial Dashboards | Service read | IndustrialDashboardService.plant_dashboard() OK |
| pass | Industrial Dashboards | Permission (admin view) | Masters |
| fail | Industrial Dashboards | Open | Not automated in Playwright suite |
| fail | Industrial Dashboards | Print | Not automated in Playwright suite |
| fail | Industrial Dashboards | Export PDF | Not automated in Playwright suite |
| fail | Industrial Dashboards | Export Excel | Not automated in Playwright suite |
| fail | Industrial Dashboards | Pagination | Not automated in Playwright suite |
| fail | Industrial Dashboards | Sorting | Not automated in Playwright suite |
| fail | Industrial Dashboards | Filters | Not automated in Playwright suite |
| fail | Industrial Dashboards | Approve | Workflow not fully automated for this screen |
| fail | Industrial Dashboards | Reject | Workflow not fully automated for this screen |
| fail | Industrial Dashboards | Post | Workflow not fully automated for this screen |
| fail | Industrial Dashboards | Reverse | Workflow not fully automated for this screen |
| pass | Industrial Reports | Route callable | <function page_industrial_reports at 0x0000021DA4544680> |
| fail | Industrial Reports | Service read | No automated service test |
| pass | Industrial Reports | Permission (admin view) | Masters |
| fail | Industrial Reports | Open | Not automated in Playwright suite |
| fail | Industrial Reports | Print | Not automated in Playwright suite |
| fail | Industrial Reports | Export PDF | Not automated in Playwright suite |
| fail | Industrial Reports | Export Excel | Not automated in Playwright suite |
| fail | Industrial Reports | Pagination | Not automated in Playwright suite |
| fail | Industrial Reports | Sorting | Not automated in Playwright suite |
| fail | Industrial Reports | Filters | Not automated in Playwright suite |
| pass | Cash Book | Route callable | <function page_cash_book at 0x0000021DA44640E0> |
| fail | Cash Book | Service read | No automated service test |
| pass | Cash Book | Permission (admin view) | Masters |
| fail | Cash Book | Open | Not automated in Playwright suite |
| fail | Cash Book | Print | Not automated in Playwright suite |
| fail | Cash Book | Export PDF | Not automated in Playwright suite |
| fail | Cash Book | Export Excel | Not automated in Playwright suite |
| fail | Cash Book | Pagination | Not automated in Playwright suite |
| fail | Cash Book | Sorting | Not automated in Playwright suite |
| fail | Cash Book | Filters | Not automated in Playwright suite |
| pass | Bank Book | Route callable | <function page_bank_book at 0x0000021DA4464180> |
| fail | Bank Book | Service read | No automated service test |
| pass | Bank Book | Permission (admin view) | Masters |
| fail | Bank Book | Open | Not automated in Playwright suite |
| fail | Bank Book | Print | Not automated in Playwright suite |
| fail | Bank Book | Export PDF | Not automated in Playwright suite |
| fail | Bank Book | Export Excel | Not automated in Playwright suite |
| fail | Bank Book | Pagination | Not automated in Playwright suite |
| fail | Bank Book | Sorting | Not automated in Playwright suite |
| fail | Bank Book | Filters | Not automated in Playwright suite |
| pass | Customer Receipt | Route callable | <function page_customer_receipt at 0x0000021DA4464360> |
| fail | Customer Receipt | Service read | No automated service test |
| pass | Customer Receipt | Permission (admin view) | Masters |
| fail | Customer Receipt | Open | Not automated in Playwright suite |
| fail | Customer Receipt | Print | Not automated in Playwright suite |
| fail | Customer Receipt | Export PDF | Not automated in Playwright suite |
| fail | Customer Receipt | Export Excel | Not automated in Playwright suite |
| fail | Customer Receipt | Pagination | Not automated in Playwright suite |
| fail | Customer Receipt | Sorting | Not automated in Playwright suite |
| fail | Customer Receipt | Filters | Not automated in Playwright suite |
| pass | Supplier Payment | Route callable | <function page_supplier_payment at 0x0000021DA4464400> |
| fail | Supplier Payment | Service read | No automated service test |
| pass | Supplier Payment | Permission (admin view) | Masters |
| fail | Supplier Payment | Open | Not automated in Playwright suite |
| fail | Supplier Payment | Print | Not automated in Playwright suite |
| fail | Supplier Payment | Export PDF | Not automated in Playwright suite |
| fail | Supplier Payment | Export Excel | Not automated in Playwright suite |
| fail | Supplier Payment | Pagination | Not automated in Playwright suite |
| fail | Supplier Payment | Sorting | Not automated in Playwright suite |
| fail | Supplier Payment | Filters | Not automated in Playwright suite |
| pass | Expense Payment | Route callable | <function page_expense_payment at 0x0000021DA4464540> |
| fail | Expense Payment | Service read | No automated service test |
| pass | Expense Payment | Permission (admin view) | Masters |
| fail | Expense Payment | Open | Not automated in Playwright suite |
| fail | Expense Payment | Print | Not automated in Playwright suite |
| fail | Expense Payment | Export PDF | Not automated in Playwright suite |
| fail | Expense Payment | Export Excel | Not automated in Playwright suite |
| fail | Expense Payment | Pagination | Not automated in Playwright suite |
| fail | Expense Payment | Sorting | Not automated in Playwright suite |
| fail | Expense Payment | Filters | Not automated in Playwright suite |
| pass | Party Transfer | Route callable | <function page_party_transfer at 0x0000021DA44645E0> |
| fail | Party Transfer | Service read | No automated service test |
| pass | Party Transfer | Permission (admin view) | Masters |
| fail | Party Transfer | Open | Not automated in Playwright suite |
| fail | Party Transfer | Print | Not automated in Playwright suite |
| fail | Party Transfer | Export PDF | Not automated in Playwright suite |
| fail | Party Transfer | Export Excel | Not automated in Playwright suite |
| fail | Party Transfer | Pagination | Not automated in Playwright suite |
| fail | Party Transfer | Sorting | Not automated in Playwright suite |
| fail | Party Transfer | Filters | Not automated in Playwright suite |
| pass | Chart of Accounts | Route callable | <function page_chart_of_accounts at 0x0000021DA44647C0> |
| fail | Chart of Accounts | Service read | No automated service test |
| pass | Chart of Accounts | Read | get_accounts() |
| pass | Chart of Accounts | Permission (admin view) | Masters |
| fail | Chart of Accounts | Open | Not automated in Playwright suite |
| fail | Chart of Accounts | Print | Not automated in Playwright suite |
| fail | Chart of Accounts | Export PDF | Not automated in Playwright suite |
| fail | Chart of Accounts | Export Excel | Not automated in Playwright suite |
| fail | Chart of Accounts | Pagination | Not automated in Playwright suite |
| fail | Chart of Accounts | Sorting | Not automated in Playwright suite |
| fail | Chart of Accounts | Filters | Not automated in Playwright suite |
| pass | Journal Voucher | Route callable | <function page_journal at 0x0000021DA43E9440> |
| fail | Journal Voucher | Service read | No automated service test |
| pass | Journal Voucher | Permission (admin view) | Masters |
| fail | Journal Voucher | Open | Not automated in Playwright suite |
| fail | Journal Voucher | Print | Not automated in Playwright suite |
| fail | Journal Voucher | Export PDF | Not automated in Playwright suite |
| fail | Journal Voucher | Export Excel | Not automated in Playwright suite |
| fail | Journal Voucher | Pagination | Not automated in Playwright suite |
| fail | Journal Voucher | Sorting | Not automated in Playwright suite |
| fail | Journal Voucher | Filters | Not automated in Playwright suite |
| pass | Customer Ledger | Route callable | <function page_customer_ledger at 0x0000021DA467BF60> |
| fail | Customer Ledger | Service read | No automated service test |
| pass | Customer Ledger | Permission (admin view) | Masters |
| fail | Customer Ledger | Open | Not automated in Playwright suite |
| fail | Customer Ledger | Print | Not automated in Playwright suite |
| fail | Customer Ledger | Export PDF | Not automated in Playwright suite |
| fail | Customer Ledger | Export Excel | Not automated in Playwright suite |
| fail | Customer Ledger | Pagination | Not automated in Playwright suite |
| fail | Customer Ledger | Sorting | Not automated in Playwright suite |
| fail | Customer Ledger | Filters | Not automated in Playwright suite |
| pass | Supplier Ledger | Route callable | <function page_supplier_ledger at 0x0000021DA46A8040> |
| fail | Supplier Ledger | Service read | No automated service test |
| pass | Supplier Ledger | Permission (admin view) | Masters |
| fail | Supplier Ledger | Open | Not automated in Playwright suite |
| fail | Supplier Ledger | Print | Not automated in Playwright suite |
| fail | Supplier Ledger | Export PDF | Not automated in Playwright suite |
| fail | Supplier Ledger | Export Excel | Not automated in Playwright suite |
| fail | Supplier Ledger | Pagination | Not automated in Playwright suite |
| fail | Supplier Ledger | Sorting | Not automated in Playwright suite |
| fail | Supplier Ledger | Filters | Not automated in Playwright suite |
| pass | Trial Balance | Route callable | <function page_trial_balance at 0x0000021DA43E9580> |
| fail | Trial Balance | Service read | No automated service test |
| pass | Trial Balance | Read | get_trial_balance() |
| pass | Trial Balance | Permission (admin view) | Masters |
| fail | Trial Balance | Open | Not automated in Playwright suite |
| fail | Trial Balance | Print | Not automated in Playwright suite |
| fail | Trial Balance | Export PDF | Not automated in Playwright suite |
| fail | Trial Balance | Export Excel | Not automated in Playwright suite |
| fail | Trial Balance | Pagination | Not automated in Playwright suite |
| fail | Trial Balance | Sorting | Not automated in Playwright suite |
| fail | Trial Balance | Filters | Not automated in Playwright suite |
| pass | Profit & Loss Report | Route callable | <function page_profit_loss at 0x0000021DA46A8180> |
| fail | Profit & Loss Report | Service read | No automated service test |
| pass | Profit & Loss Report | Permission (admin view) | Masters |
| fail | Profit & Loss Report | Open | Not automated in Playwright suite |
| fail | Profit & Loss Report | Print | Not automated in Playwright suite |
| fail | Profit & Loss Report | Export PDF | Not automated in Playwright suite |
| fail | Profit & Loss Report | Export Excel | Not automated in Playwright suite |
| fail | Profit & Loss Report | Pagination | Not automated in Playwright suite |
| fail | Profit & Loss Report | Sorting | Not automated in Playwright suite |
| fail | Profit & Loss Report | Filters | Not automated in Playwright suite |
| pass | Balance Sheet | Route callable | <function page_balance_sheet at 0x0000021DA43E9620> |
| fail | Balance Sheet | Service read | No automated service test |
| pass | Balance Sheet | Permission (admin view) | Masters |
| fail | Balance Sheet | Open | Not automated in Playwright suite |
| fail | Balance Sheet | Print | Not automated in Playwright suite |
| fail | Balance Sheet | Export PDF | Not automated in Playwright suite |
| fail | Balance Sheet | Export Excel | Not automated in Playwright suite |
| fail | Balance Sheet | Pagination | Not automated in Playwright suite |
| fail | Balance Sheet | Sorting | Not automated in Playwright suite |
| fail | Balance Sheet | Filters | Not automated in Playwright suite |
| pass | Fiscal Year Closing | Route callable | <function page_fiscal_year_closing at 0x0000021DA4464900> |
| fail | Fiscal Year Closing | Service read | No automated service test |
| pass | Fiscal Year Closing | Permission (admin view) | Masters |
| fail | Fiscal Year Closing | Open | Not automated in Playwright suite |
| fail | Fiscal Year Closing | Print | Not automated in Playwright suite |
| fail | Fiscal Year Closing | Export PDF | Not automated in Playwright suite |
| fail | Fiscal Year Closing | Export Excel | Not automated in Playwright suite |
| fail | Fiscal Year Closing | Pagination | Not automated in Playwright suite |
| fail | Fiscal Year Closing | Sorting | Not automated in Playwright suite |
| fail | Fiscal Year Closing | Filters | Not automated in Playwright suite |
| pass | Employees | Route callable | <function page_hr_employees at 0x0000021DA43EA340> |
| fail | Employees | Service read | No automated service test |
| pass | Employees | Permission (admin view) | Masters |
| fail | Employees | Open | Not automated in Playwright suite |
| fail | Employees | Print | Not automated in Playwright suite |
| fail | Employees | Export PDF | Not automated in Playwright suite |
| fail | Employees | Export Excel | Not automated in Playwright suite |
| fail | Employees | Pagination | Not automated in Playwright suite |
| fail | Employees | Sorting | Not automated in Playwright suite |
| fail | Employees | Filters | Not automated in Playwright suite |
| pass | Attendance | Route callable | <function page_attendance_simple at 0x0000021DA4466160> |
| fail | Attendance | Service read | No automated service test |
| pass | Attendance | Permission (admin view) | Masters |
| fail | Attendance | Open | Not automated in Playwright suite |
| fail | Attendance | Print | Not automated in Playwright suite |
| fail | Attendance | Export PDF | Not automated in Playwright suite |
| fail | Attendance | Export Excel | Not automated in Playwright suite |
| fail | Attendance | Pagination | Not automated in Playwright suite |
| fail | Attendance | Sorting | Not automated in Playwright suite |
| fail | Attendance | Filters | Not automated in Playwright suite |
| pass | Leave Management | Route callable | <function page_leave at 0x0000021DA43EA520> |
| fail | Leave Management | Service read | No automated service test |
| pass | Leave Management | Permission (admin view) | Masters |
| fail | Leave Management | Open | Not automated in Playwright suite |
| fail | Leave Management | Print | Not automated in Playwright suite |
| fail | Leave Management | Export PDF | Not automated in Playwright suite |
| fail | Leave Management | Export Excel | Not automated in Playwright suite |
| fail | Leave Management | Pagination | Not automated in Playwright suite |
| fail | Leave Management | Sorting | Not automated in Playwright suite |
| fail | Leave Management | Filters | Not automated in Playwright suite |
| pass | Payroll | Route callable | <function page_payroll at 0x0000021DA43EA700> |
| fail | Payroll | Service read | No automated service test |
| pass | Payroll | Permission (admin view) | Masters |
| fail | Payroll | Open | Not automated in Playwright suite |
| fail | Payroll | Print | Not automated in Playwright suite |
| fail | Payroll | Export PDF | Not automated in Playwright suite |
| fail | Payroll | Export Excel | Not automated in Playwright suite |
| fail | Payroll | Pagination | Not automated in Playwright suite |
| fail | Payroll | Sorting | Not automated in Playwright suite |
| fail | Payroll | Filters | Not automated in Playwright suite |
| pass | Employee Advances | Route callable | <function page_advances at 0x0000021DA43EA7A0> |
| fail | Employee Advances | Service read | No automated service test |
| pass | Employee Advances | Permission (admin view) | Masters |
| fail | Employee Advances | Open | Not automated in Playwright suite |
| fail | Employee Advances | Print | Not automated in Playwright suite |
| fail | Employee Advances | Export PDF | Not automated in Playwright suite |
| fail | Employee Advances | Export Excel | Not automated in Playwright suite |
| fail | Employee Advances | Pagination | Not automated in Playwright suite |
| fail | Employee Advances | Sorting | Not automated in Playwright suite |
| fail | Employee Advances | Filters | Not automated in Playwright suite |
| pass | Employee Ledger | Route callable | <function page_employee_ledger at 0x0000021DA43EA980> |
| fail | Employee Ledger | Service read | No automated service test |
| pass | Employee Ledger | Permission (admin view) | Masters |
| fail | Employee Ledger | Open | Not automated in Playwright suite |
| fail | Employee Ledger | Print | Not automated in Playwright suite |
| fail | Employee Ledger | Export PDF | Not automated in Playwright suite |
| fail | Employee Ledger | Export Excel | Not automated in Playwright suite |
| fail | Employee Ledger | Pagination | Not automated in Playwright suite |
| fail | Employee Ledger | Sorting | Not automated in Playwright suite |
| fail | Employee Ledger | Filters | Not automated in Playwright suite |
| pass | Weight Entry | Route callable | <function page_weight_entry at 0x0000021DA4466700> |
| fail | Weight Entry | Service read | No automated service test |
| pass | Weight Entry | Permission (admin view) | Masters |
| fail | Weight Entry | Open | Not automated in Playwright suite |
| fail | Weight Entry | Print | Not automated in Playwright suite |
| fail | Weight Entry | Export PDF | Not automated in Playwright suite |
| fail | Weight Entry | Export Excel | Not automated in Playwright suite |
| fail | Weight Entry | Pagination | Not automated in Playwright suite |
| fail | Weight Entry | Sorting | Not automated in Playwright suite |
| fail | Weight Entry | Filters | Not automated in Playwright suite |
| pass | Weight Reports | Route callable | <function page_weight_reports at 0x0000021DA44667A0> |
| fail | Weight Reports | Service read | No automated service test |
| pass | Weight Reports | Permission (admin view) | Masters |
| fail | Weight Reports | Open | Not automated in Playwright suite |
| fail | Weight Reports | Print | Not automated in Playwright suite |
| fail | Weight Reports | Export PDF | Not automated in Playwright suite |
| fail | Weight Reports | Export Excel | Not automated in Playwright suite |
| fail | Weight Reports | Pagination | Not automated in Playwright suite |
| fail | Weight Reports | Sorting | Not automated in Playwright suite |
| fail | Weight Reports | Filters | Not automated in Playwright suite |
| pass | Gate Pass Entry | Route callable | <function page_gate_pass_entry at 0x0000021DA4466E80> |
| fail | Gate Pass Entry | Service read | No automated service test |
| pass | Gate Pass Entry | Permission (admin view) | Masters |
| fail | Gate Pass Entry | Open | Not automated in Playwright suite |
| fail | Gate Pass Entry | Print | Not automated in Playwright suite |
| fail | Gate Pass Entry | Export PDF | Not automated in Playwright suite |
| fail | Gate Pass Entry | Export Excel | Not automated in Playwright suite |
| fail | Gate Pass Entry | Pagination | Not automated in Playwright suite |
| fail | Gate Pass Entry | Sorting | Not automated in Playwright suite |
| fail | Gate Pass Entry | Filters | Not automated in Playwright suite |
| pass | Reports Center | Route callable | <function page_reports_center at 0x0000021DA44AE660> |
| fail | Reports Center | Service read | No automated service test |
| pass | Reports Center | Permission (admin view) | Masters |
| fail | Reports Center | Open | Not automated in Playwright suite |
| fail | Reports Center | Print | Not automated in Playwright suite |
| fail | Reports Center | Export PDF | Not automated in Playwright suite |
| fail | Reports Center | Export Excel | Not automated in Playwright suite |
| fail | Reports Center | Pagination | Not automated in Playwright suite |
| fail | Reports Center | Sorting | Not automated in Playwright suite |
| fail | Reports Center | Filters | Not automated in Playwright suite |
| pass | User Management | Route callable | <function page_users at 0x0000021DA46A8220> |
| fail | User Management | Service read | No automated service test |
| pass | User Management | Permission (admin view) | Masters |
| fail | User Management | Open | Not automated in Playwright suite |
| fail | User Management | Print | Not automated in Playwright suite |
| fail | User Management | Export PDF | Not automated in Playwright suite |
| fail | User Management | Export Excel | Not automated in Playwright suite |
| fail | User Management | Pagination | Not automated in Playwright suite |
| fail | User Management | Sorting | Not automated in Playwright suite |
| fail | User Management | Filters | Not automated in Playwright suite |
| pass | Roles & Permissions | Route callable | <function page_roles at 0x0000021DA43E98A0> |
| fail | Roles & Permissions | Service read | No automated service test |
| pass | Roles & Permissions | Permission (admin view) | Masters |
| fail | Roles & Permissions | Open | Not automated in Playwright suite |
| fail | Roles & Permissions | Print | Not automated in Playwright suite |
| fail | Roles & Permissions | Export PDF | Not automated in Playwright suite |
| fail | Roles & Permissions | Export Excel | Not automated in Playwright suite |
| fail | Roles & Permissions | Pagination | Not automated in Playwright suite |
| fail | Roles & Permissions | Sorting | Not automated in Playwright suite |
| fail | Roles & Permissions | Filters | Not automated in Playwright suite |
| pass | System Settings | Route callable | <function page_settings at 0x0000021DA43E9940> |
| fail | System Settings | Service read | No automated service test |
| pass | System Settings | Permission (admin view) | Masters |
| fail | System Settings | Open | Not automated in Playwright suite |
| fail | System Settings | Print | Not automated in Playwright suite |
| fail | System Settings | Export PDF | Not automated in Playwright suite |
| fail | System Settings | Export Excel | Not automated in Playwright suite |
| fail | System Settings | Pagination | Not automated in Playwright suite |
| fail | System Settings | Sorting | Not automated in Playwright suite |
| fail | System Settings | Filters | Not automated in Playwright suite |
| pass | Holidays | Route callable | <function page_holidays at 0x0000021DA44AED40> |
| fail | Holidays | Service read | No automated service test |
| pass | Holidays | Permission (admin view) | Masters |
| fail | Holidays | Open | Not automated in Playwright suite |
| fail | Holidays | Print | Not automated in Playwright suite |
| fail | Holidays | Export PDF | Not automated in Playwright suite |
| fail | Holidays | Export Excel | Not automated in Playwright suite |
| fail | Holidays | Pagination | Not automated in Playwright suite |
| fail | Holidays | Sorting | Not automated in Playwright suite |
| fail | Holidays | Filters | Not automated in Playwright suite |
| pass | Draft Center | Route callable | <function page_draft_center at 0x0000021DA44D84A0> |
| fail | Draft Center | Service read | No automated service test |
| pass | Draft Center | Permission (admin view) | Masters |
| fail | Draft Center | Open | Not automated in Playwright suite |
| fail | Draft Center | Print | Not automated in Playwright suite |
| fail | Draft Center | Export PDF | Not automated in Playwright suite |
| fail | Draft Center | Export Excel | Not automated in Playwright suite |
| fail | Draft Center | Pagination | Not automated in Playwright suite |
| fail | Draft Center | Sorting | Not automated in Playwright suite |
| fail | Draft Center | Filters | Not automated in Playwright suite |
| pass | Approval Designer | Route callable | <function page_approval_designer at 0x0000021DA44D8AE0> |
| fail | Approval Designer | Service read | No automated service test |
| pass | Approval Designer | Permission (admin view) | Masters |
| fail | Approval Designer | Open | Not automated in Playwright suite |
| fail | Approval Designer | Print | Not automated in Playwright suite |
| fail | Approval Designer | Export PDF | Not automated in Playwright suite |
| fail | Approval Designer | Export Excel | Not automated in Playwright suite |
| fail | Approval Designer | Pagination | Not automated in Playwright suite |
| fail | Approval Designer | Sorting | Not automated in Playwright suite |
| fail | Approval Designer | Filters | Not automated in Playwright suite |
| pass | Mobile Approvals | Route callable | <function page_mobile_approvals at 0x0000021DA44FC400> |
| fail | Mobile Approvals | Service read | No automated service test |
| pass | Mobile Approvals | Permission (admin view) | Masters |
| fail | Mobile Approvals | Open | Not automated in Playwright suite |
| fail | Mobile Approvals | Print | Not automated in Playwright suite |
| fail | Mobile Approvals | Export PDF | Not automated in Playwright suite |
| fail | Mobile Approvals | Export Excel | Not automated in Playwright suite |
| fail | Mobile Approvals | Pagination | Not automated in Playwright suite |
| fail | Mobile Approvals | Sorting | Not automated in Playwright suite |
| fail | Mobile Approvals | Filters | Not automated in Playwright suite |
| pass | ERP Health Check | Route callable | <function page_erp_health_check at 0x0000021DA44D8720> |
| fail | ERP Health Check | Service read | No automated service test |
| pass | ERP Health Check | Permission (admin view) | Masters |
| fail | ERP Health Check | Open | Not automated in Playwright suite |
| fail | ERP Health Check | Print | Not automated in Playwright suite |
| fail | ERP Health Check | Export PDF | Not automated in Playwright suite |
| fail | ERP Health Check | Export Excel | Not automated in Playwright suite |
| fail | ERP Health Check | Pagination | Not automated in Playwright suite |
| fail | ERP Health Check | Sorting | Not automated in Playwright suite |
| fail | ERP Health Check | Filters | Not automated in Playwright suite |
| pass | Audit Log | Route callable | <function page_audit_log at 0x0000021DA44AECA0> |
| fail | Audit Log | Service read | No automated service test |
| pass | Audit Log | Permission (admin view) | Masters |
| fail | Audit Log | Open | Not automated in Playwright suite |
| fail | Audit Log | Print | Not automated in Playwright suite |
| fail | Audit Log | Export PDF | Not automated in Playwright suite |
| fail | Audit Log | Export Excel | Not automated in Playwright suite |
| fail | Audit Log | Pagination | Not automated in Playwright suite |
| fail | Audit Log | Sorting | Not automated in Playwright suite |
| fail | Audit Log | Filters | Not automated in Playwright suite |
| pass | Backup & Restore | Route callable | <function page_backup_restore at 0x0000021DA46A84A0> |
| fail | Backup & Restore | Service read | No automated service test |
| pass | Backup & Restore | Permission (admin view) | Masters |
| fail | Backup & Restore | Open | Not automated in Playwright suite |
| fail | Backup & Restore | Print | Not automated in Playwright suite |
| fail | Backup & Restore | Export PDF | Not automated in Playwright suite |
| fail | Backup & Restore | Export Excel | Not automated in Playwright suite |
| fail | Backup & Restore | Pagination | Not automated in Playwright suite |
| fail | Backup & Restore | Sorting | Not automated in Playwright suite |
| fail | Backup & Restore | Filters | Not automated in Playwright suite |