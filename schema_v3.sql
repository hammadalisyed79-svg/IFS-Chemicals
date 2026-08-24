-- IFS Chemicals ERP Schema v3 extensions (additive, safe migration)

PRAGMA foreign_keys = ON;

-- Settings & audit
CREATE TABLE IF NOT EXISTS system_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name  TEXT NOT NULL,
    record_id   INTEGER,
    action      TEXT NOT NULL,
    details     TEXT,
    user_id     INTEGER REFERENCES users(id),
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Organization
CREATE TABLE IF NOT EXISTS departments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    is_active INTEGER DEFAULT 1,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT
);

CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    is_active INTEGER DEFAULT 1,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT
);

CREATE TABLE IF NOT EXISTS role_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER NOT NULL REFERENCES roles(id) ON DELETE CASCADE,
    module_name TEXT NOT NULL,
    can_view INTEGER DEFAULT 1,
    can_add INTEGER DEFAULT 0,
    can_edit INTEGER DEFAULT 0,
    can_delete INTEGER DEFAULT 0,
    can_post INTEGER DEFAULT 0,
    can_approve INTEGER DEFAULT 0,
    UNIQUE(role_id, module_name)
);

CREATE TABLE IF NOT EXISTS tax_rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    sales_tax_pct REAL DEFAULT 0,
    further_tax_pct REAL DEFAULT 0,
    extra_tax_pct REAL DEFAULT 0,
    wht_pct REAL DEFAULT 0,
    fed_pct REAL DEFAULT 0,
    is_exempt INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT
);

CREATE TABLE IF NOT EXISTS payment_terms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    days INTEGER DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT
);

CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    registration_no TEXT NOT NULL,
    driver_name TEXT,
    vehicle_type TEXT,
    is_active INTEGER DEFAULT 1,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT
);

CREATE TABLE IF NOT EXISTS machines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    production_line TEXT,
    capacity REAL DEFAULT 0,
    is_active INTEGER DEFAULT 1,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT
);

CREATE TABLE IF NOT EXISTS unit_conversions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_unit_id INTEGER NOT NULL REFERENCES units_of_measure(id),
    to_unit_id INTEGER NOT NULL REFERENCES units_of_measure(id),
    factor REAL NOT NULL,
    UNIQUE(from_unit_id, to_unit_id)
);

CREATE TABLE IF NOT EXISTS product_batches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_no TEXT NOT NULL,
    product_id INTEGER NOT NULL REFERENCES products(id),
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    quantity REAL DEFAULT 0,
    mfg_date TEXT,
    expiry_date TEXT,
    is_active INTEGER DEFAULT 1,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(batch_no, product_id, warehouse_id)
);

CREATE TABLE IF NOT EXISTS weight_slips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no TEXT UNIQUE NOT NULL,
    slip_date TEXT NOT NULL,
    vehicle_id INTEGER REFERENCES vehicles(id),
    driver_name TEXT,
    reference_type TEXT,
    reference_id INTEGER,
    first_weight REAL DEFAULT 0,
    second_weight REAL DEFAULT 0,
    tare_weight REAL DEFAULT 0,
    gross_weight REAL DEFAULT 0,
    net_weight REAL DEFAULT 0,
    remarks TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT
);

-- Sales workflow
CREATE TABLE IF NOT EXISTS quotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no TEXT UNIQUE NOT NULL,
    quote_date TEXT NOT NULL,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    valid_until TEXT,
    subtotal REAL DEFAULT 0,
    discount REAL DEFAULT 0,
    tax_total REAL DEFAULT 0,
    total REAL DEFAULT 0,
    status TEXT DEFAULT 'draft',
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT,
    posted_by INTEGER REFERENCES users(id),
    posted_at TEXT
);

CREATE TABLE IF NOT EXISTS quotation_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    quotation_id INTEGER NOT NULL REFERENCES quotations(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity REAL NOT NULL,
    unit_id INTEGER REFERENCES units_of_measure(id),
    net_weight REAL DEFAULT 0,
    rate REAL NOT NULL,
    discount REAL DEFAULT 0,
    tax_amount REAL DEFAULT 0,
    amount REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS delivery_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no TEXT UNIQUE NOT NULL,
    dn_date TEXT NOT NULL,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    sales_order_id INTEGER REFERENCES sales_orders(id),
    warehouse_id INTEGER REFERENCES warehouses(id),
    vehicle_id INTEGER REFERENCES vehicles(id),
    driver_name TEXT,
    subtotal REAL DEFAULT 0,
    total REAL DEFAULT 0,
    status TEXT DEFAULT 'draft',
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT,
    posted_by INTEGER REFERENCES users(id),
    posted_at TEXT
);

CREATE TABLE IF NOT EXISTS delivery_note_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dn_id INTEGER NOT NULL REFERENCES delivery_notes(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    batch_id INTEGER REFERENCES product_batches(id),
    quantity REAL NOT NULL,
    unit_id INTEGER REFERENCES units_of_measure(id),
    gross_weight REAL DEFAULT 0,
    tare_weight REAL DEFAULT 0,
    net_weight REAL DEFAULT 0,
    rate REAL NOT NULL,
    amount REAL NOT NULL
);

-- Purchase workflow
CREATE TABLE IF NOT EXISTS purchase_requisitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no TEXT UNIQUE NOT NULL,
    req_date TEXT NOT NULL,
    department_id INTEGER REFERENCES departments(id),
    subtotal REAL DEFAULT 0,
    status TEXT DEFAULT 'draft',
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT,
    approved_by INTEGER REFERENCES users(id),
    approved_at TEXT
);

CREATE TABLE IF NOT EXISTS purchase_requisition_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    requisition_id INTEGER NOT NULL REFERENCES purchase_requisitions(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity REAL NOT NULL,
    unit_id INTEGER REFERENCES units_of_measure(id),
    estimated_rate REAL DEFAULT 0,
    amount REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS goods_receipt_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no TEXT UNIQUE NOT NULL,
    grn_date TEXT NOT NULL,
    supplier_id INTEGER NOT NULL REFERENCES suppliers(id),
    purchase_order_id INTEGER REFERENCES purchase_orders(id),
    warehouse_id INTEGER REFERENCES warehouses(id),
    weight_slip_id INTEGER REFERENCES weight_slips(id),
    subtotal REAL DEFAULT 0,
    tax_total REAL DEFAULT 0,
    total REAL DEFAULT 0,
    status TEXT DEFAULT 'draft',
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT,
    posted_by INTEGER REFERENCES users(id),
    posted_at TEXT
);

CREATE TABLE IF NOT EXISTS grn_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    grn_id INTEGER NOT NULL REFERENCES goods_receipt_notes(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    batch_no TEXT,
    expiry_date TEXT,
    quantity REAL NOT NULL,
    unit_id INTEGER REFERENCES units_of_measure(id),
    gross_weight REAL DEFAULT 0,
    tare_weight REAL DEFAULT 0,
    net_weight REAL DEFAULT 0,
    rate REAL NOT NULL,
    tax_amount REAL DEFAULT 0,
    amount REAL NOT NULL
);

-- BOM / Production
CREATE TABLE IF NOT EXISTS bom_formulas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no TEXT UNIQUE NOT NULL,
    finished_product_id INTEGER NOT NULL REFERENCES products(id),
    version_no TEXT NOT NULL DEFAULT '1.0',
    standard_output_qty REAL DEFAULT 1,
    output_unit_id INTEGER REFERENCES units_of_measure(id),
    standard_cost REAL DEFAULT 0,
    status TEXT DEFAULT 'draft' CHECK(status IN ('draft','approved','inactive')),
    is_active INTEGER DEFAULT 1,
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT,
    approved_by INTEGER REFERENCES users(id),
    approved_at TEXT,
    UNIQUE(finished_product_id, version_no)
);

CREATE TABLE IF NOT EXISTS bom_formula_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bom_id INTEGER NOT NULL REFERENCES bom_formulas(id) ON DELETE CASCADE,
    raw_product_id INTEGER NOT NULL REFERENCES products(id),
    quantity REAL NOT NULL,
    unit_id INTEGER REFERENCES units_of_measure(id),
    weight_required REAL DEFAULT 0,
    wastage_pct REAL DEFAULT 0,
    standard_cost REAL DEFAULT 0,
    line_cost REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS production_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no TEXT UNIQUE NOT NULL,
    batch_no TEXT UNIQUE NOT NULL,
    order_date TEXT NOT NULL,
    bom_id INTEGER NOT NULL REFERENCES bom_formulas(id),
    finished_product_id INTEGER NOT NULL REFERENCES products(id),
    warehouse_id INTEGER REFERENCES warehouses(id),
    machine_id INTEGER REFERENCES machines(id),
    planned_qty REAL NOT NULL,
    actual_qty REAL DEFAULT 0,
    wastage_qty REAL DEFAULT 0,
    labour_cost REAL DEFAULT 0,
    utility_cost REAL DEFAULT 0,
    packing_cost REAL DEFAULT 0,
    overhead_cost REAL DEFAULT 0,
    actual_cost REAL DEFAULT 0,
    cost_per_unit REAL DEFAULT 0,
    qc_status TEXT DEFAULT 'Pending' CHECK(qc_status IN ('Pending','Passed','Failed')),
    status TEXT DEFAULT 'draft' CHECK(status IN ('draft','issued','completed','cancelled')),
    supervisor_id INTEGER REFERENCES employees(id),
    notes TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT,
    approved_by INTEGER REFERENCES users(id),
    approved_at TEXT
);

CREATE TABLE IF NOT EXISTS production_material_issues (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    production_order_id INTEGER NOT NULL REFERENCES production_orders(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    batch_id INTEGER REFERENCES product_batches(id),
    quantity REAL NOT NULL,
    unit_id INTEGER REFERENCES units_of_measure(id),
    weight REAL DEFAULT 0,
    rate REAL DEFAULT 0,
    amount REAL DEFAULT 0,
    issued_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS production_finished_receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    production_order_id INTEGER NOT NULL REFERENCES production_orders(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    batch_no TEXT,
    quantity REAL NOT NULL,
    unit_id INTEGER REFERENCES units_of_measure(id),
    received_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- General ledger postings
CREATE TABLE IF NOT EXISTS general_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_date TEXT NOT NULL,
    account_id INTEGER NOT NULL REFERENCES chart_of_accounts(id),
    debit REAL DEFAULT 0,
    credit REAL DEFAULT 0,
    description TEXT,
    reference_type TEXT,
    reference_id INTEGER,
    reference_no TEXT,
    voucher_id INTEGER REFERENCES journal_vouchers(id),
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_gl_account ON general_ledger(account_id);
CREATE INDEX IF NOT EXISTS idx_gl_date ON general_ledger(entry_date);
CREATE INDEX IF NOT EXISTS idx_gl_ref ON general_ledger(reference_type, reference_id);
CREATE INDEX IF NOT EXISTS idx_batches_product ON product_batches(product_id);
CREATE INDEX IF NOT EXISTS idx_quotations_customer ON quotations(customer_id);
CREATE INDEX IF NOT EXISTS idx_grn_supplier ON goods_receipt_notes(supplier_id);
CREATE INDEX IF NOT EXISTS idx_prod_orders_status ON production_orders(status);

-- Multi-expense bill (one party, many expense heads)
CREATE TABLE IF NOT EXISTS expense_bills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no TEXT UNIQUE NOT NULL,
    bill_date TEXT NOT NULL,
    party_type TEXT NOT NULL,
    party_id INTEGER NOT NULL,
    settlement TEXT NOT NULL,
    bank_account_id INTEGER REFERENCES chart_of_accounts(id),
    reference_no TEXT,
    description TEXT,
    total_amount REAL NOT NULL DEFAULT 0,
    status TEXT DEFAULT 'posted',
    cash_entry_id INTEGER,
    cash_entry_source TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    posted_by INTEGER REFERENCES users(id),
    posted_at TEXT
);

CREATE TABLE IF NOT EXISTS expense_bill_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bill_id INTEGER NOT NULL REFERENCES expense_bills(id) ON DELETE CASCADE,
    line_no INTEGER NOT NULL DEFAULT 1,
    expense_account_id INTEGER NOT NULL REFERENCES chart_of_accounts(id),
    narration TEXT,
    amount REAL NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_expense_bills_date ON expense_bills(bill_date);
CREATE INDEX IF NOT EXISTS idx_expense_bills_party ON expense_bills(party_type, party_id);
CREATE INDEX IF NOT EXISTS idx_expense_bill_lines_bill ON expense_bill_lines(bill_id);
