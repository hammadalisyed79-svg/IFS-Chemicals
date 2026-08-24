-- IFS Chemicals ERP - Professional Relational Schema (v2)
-- SQLite DDL with foreign keys and indexes

PRAGMA foreign_keys = ON;

-- ============================================================================
-- SYSTEM
-- ============================================================================

CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_sequences (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_type    TEXT UNIQUE NOT NULL,
    prefix      TEXT NOT NULL,
    last_number INTEGER NOT NULL DEFAULT 0,
    padding     INTEGER NOT NULL DEFAULT 4,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_at TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    full_name     TEXT NOT NULL,
    role          TEXT DEFAULT 'user',
    is_active     INTEGER DEFAULT 1,
    created_by    INTEGER REFERENCES users(id),
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by   INTEGER REFERENCES users(id),
    modified_at   TEXT
);

-- ============================================================================
-- MASTER DATA
-- ============================================================================

CREATE TABLE IF NOT EXISTS product_categories (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    description TEXT,
    is_active   INTEGER DEFAULT 1,
    created_by  INTEGER REFERENCES users(id),
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT
);

CREATE TABLE IF NOT EXISTS units_of_measure (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    symbol      TEXT NOT NULL,
    is_active   INTEGER DEFAULT 1,
    created_by  INTEGER REFERENCES users(id),
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT
);

CREATE TABLE IF NOT EXISTS warehouses (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    address     TEXT,
    city        TEXT,
    is_default  INTEGER DEFAULT 0,
    is_active   INTEGER DEFAULT 1,
    created_by  INTEGER REFERENCES users(id),
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT
);

CREATE TABLE IF NOT EXISTS employees (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT UNIQUE NOT NULL,
    full_name   TEXT NOT NULL,
    department  TEXT,
    designation TEXT,
    phone       TEXT,
    email       TEXT,
    user_id     INTEGER REFERENCES users(id),
    is_active   INTEGER DEFAULT 1,
    created_by  INTEGER REFERENCES users(id),
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT
);

CREATE TABLE IF NOT EXISTS account_groups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    code        TEXT UNIQUE NOT NULL,
    name        TEXT NOT NULL,
    group_type  TEXT NOT NULL CHECK(group_type IN ('asset','liability','equity','income','expense')),
    parent_id   INTEGER REFERENCES account_groups(id),
    is_active   INTEGER DEFAULT 1,
    created_by  INTEGER REFERENCES users(id),
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT
);

CREATE TABLE IF NOT EXISTS chart_of_accounts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    code             TEXT UNIQUE NOT NULL,
    name             TEXT NOT NULL,
    account_group_id INTEGER NOT NULL REFERENCES account_groups(id),
    parent_id        INTEGER REFERENCES chart_of_accounts(id),
    opening_balance  REAL DEFAULT 0,
    current_balance  REAL DEFAULT 0,
    is_active        INTEGER DEFAULT 1,
    created_by       INTEGER REFERENCES users(id),
    created_at       TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by      INTEGER REFERENCES users(id),
    modified_at      TEXT
);

CREATE TABLE IF NOT EXISTS master_groups (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type  TEXT NOT NULL CHECK(entity_type IN ('product','customer','supplier')),
    code         TEXT NOT NULL,
    name         TEXT NOT NULL,
    parent_id    INTEGER REFERENCES master_groups(id),
    notes        TEXT,
    sort_order   INTEGER DEFAULT 0,
    is_active    INTEGER DEFAULT 1,
    created_by   INTEGER REFERENCES users(id),
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by  INTEGER REFERENCES users(id),
    modified_at  TEXT,
    UNIQUE(entity_type, code)
);

CREATE TABLE IF NOT EXISTS customers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    contact_person  TEXT,
    phone           TEXT,
    email           TEXT,
    address         TEXT,
    city            TEXT,
    province        TEXT,
    credit_limit    REAL DEFAULT 0,
    opening_balance REAL DEFAULT 0,
    current_balance REAL DEFAULT 0,
    is_active       INTEGER DEFAULT 1,
    created_by      INTEGER REFERENCES users(id),
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by     INTEGER REFERENCES users(id),
    modified_at     TEXT,
    group_id        INTEGER REFERENCES master_groups(id)
);

CREATE TABLE IF NOT EXISTS suppliers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    code            TEXT UNIQUE NOT NULL,
    name            TEXT NOT NULL,
    contact_person  TEXT,
    phone           TEXT,
    email           TEXT,
    address         TEXT,
    city            TEXT,
    opening_balance REAL DEFAULT 0,
    current_balance REAL DEFAULT 0,
    is_active       INTEGER DEFAULT 1,
    created_by      INTEGER REFERENCES users(id),
    created_at      TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by     INTEGER REFERENCES users(id),
    modified_at     TEXT,
    group_id        INTEGER REFERENCES master_groups(id)
);

CREATE TABLE IF NOT EXISTS products (
    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
    code                 TEXT UNIQUE NOT NULL,
    name                 TEXT NOT NULL,
    category_id          INTEGER REFERENCES product_categories(id),
    unit_id              INTEGER REFERENCES units_of_measure(id),
    product_type         TEXT DEFAULT 'finished' CHECK(product_type IN ('raw','finished','packaging')),
    purchase_price       REAL DEFAULT 0,
    sale_price           REAL DEFAULT 0,
    reorder_level        REAL DEFAULT 0,
    default_warehouse_id INTEGER REFERENCES warehouses(id),
    is_active            INTEGER DEFAULT 1,
    created_by           INTEGER REFERENCES users(id),
    created_at           TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by          INTEGER REFERENCES users(id),
    modified_at          TEXT,
    group_id             INTEGER REFERENCES master_groups(id)
);

CREATE TABLE IF NOT EXISTS warehouse_stock (
    warehouse_id INTEGER NOT NULL REFERENCES warehouses(id),
    product_id   INTEGER NOT NULL REFERENCES products(id),
    quantity     REAL NOT NULL DEFAULT 0,
    modified_at  TEXT,
    PRIMARY KEY (warehouse_id, product_id)
);

-- ============================================================================
-- TRANSACTION HEADERS
-- ============================================================================

CREATE TABLE IF NOT EXISTS purchase_orders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no  TEXT UNIQUE NOT NULL,
    order_date   TEXT NOT NULL,
    supplier_id  INTEGER NOT NULL REFERENCES suppliers(id),
    warehouse_id INTEGER REFERENCES warehouses(id),
    expected_date TEXT,
    subtotal     REAL DEFAULT 0,
    discount     REAL DEFAULT 0,
    tax          REAL DEFAULT 0,
    total        REAL DEFAULT 0,
    status       TEXT DEFAULT 'open' CHECK(status IN ('open','partial','closed','cancelled')),
    notes        TEXT,
    created_by   INTEGER REFERENCES users(id),
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by  INTEGER REFERENCES users(id),
    modified_at  TEXT
);

CREATE TABLE IF NOT EXISTS purchase_order_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id    INTEGER NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
    product_id  INTEGER NOT NULL REFERENCES products(id),
    quantity    REAL NOT NULL,
    rate        REAL NOT NULL,
    amount      REAL NOT NULL,
    received_qty REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS purchase_invoices (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no   TEXT UNIQUE NOT NULL,
    invoice_date  TEXT NOT NULL,
    supplier_id   INTEGER NOT NULL REFERENCES suppliers(id),
    order_id      INTEGER REFERENCES purchase_orders(id),
    warehouse_id  INTEGER REFERENCES warehouses(id),
    subtotal      REAL DEFAULT 0,
    discount      REAL DEFAULT 0,
    tax           REAL DEFAULT 0,
    total         REAL DEFAULT 0,
    paid_amount   REAL DEFAULT 0,
    payment_mode  TEXT DEFAULT 'credit',
    notes         TEXT,
    created_by    INTEGER REFERENCES users(id),
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by   INTEGER REFERENCES users(id),
    modified_at   TEXT
);

CREATE TABLE IF NOT EXISTS purchase_invoice_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL REFERENCES purchase_invoices(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   REAL NOT NULL,
    rate       REAL NOT NULL,
    amount     REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS purchase_returns (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no  TEXT UNIQUE NOT NULL,
    return_date  TEXT NOT NULL,
    supplier_id  INTEGER NOT NULL REFERENCES suppliers(id),
    invoice_id   INTEGER REFERENCES purchase_invoices(id),
    warehouse_id INTEGER REFERENCES warehouses(id),
    subtotal     REAL DEFAULT 0,
    total        REAL DEFAULT 0,
    notes        TEXT,
    created_by   INTEGER REFERENCES users(id),
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by  INTEGER REFERENCES users(id),
    modified_at  TEXT
);

CREATE TABLE IF NOT EXISTS purchase_return_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    return_id  INTEGER NOT NULL REFERENCES purchase_returns(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   REAL NOT NULL,
    rate       REAL NOT NULL,
    amount     REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sales_orders (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no  TEXT UNIQUE NOT NULL,
    order_date   TEXT NOT NULL,
    customer_id  INTEGER NOT NULL REFERENCES customers(id),
    warehouse_id INTEGER REFERENCES warehouses(id),
    delivery_date TEXT,
    subtotal     REAL DEFAULT 0,
    discount     REAL DEFAULT 0,
    tax          REAL DEFAULT 0,
    total        REAL DEFAULT 0,
    status       TEXT DEFAULT 'open' CHECK(status IN ('open','partial','closed','cancelled')),
    notes        TEXT,
    created_by   INTEGER REFERENCES users(id),
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by  INTEGER REFERENCES users(id),
    modified_at  TEXT
);

CREATE TABLE IF NOT EXISTS sales_order_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id     INTEGER NOT NULL REFERENCES sales_orders(id) ON DELETE CASCADE,
    product_id   INTEGER NOT NULL REFERENCES products(id),
    quantity     REAL NOT NULL,
    rate         REAL NOT NULL,
    amount       REAL NOT NULL,
    delivered_qty REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sales_invoices (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no   TEXT UNIQUE NOT NULL,
    invoice_date  TEXT NOT NULL,
    customer_id   INTEGER NOT NULL REFERENCES customers(id),
    order_id      INTEGER REFERENCES sales_orders(id),
    warehouse_id  INTEGER REFERENCES warehouses(id),
    subtotal      REAL DEFAULT 0,
    discount      REAL DEFAULT 0,
    tax           REAL DEFAULT 0,
    total         REAL DEFAULT 0,
    paid_amount   REAL DEFAULT 0,
    payment_mode  TEXT DEFAULT 'credit',
    notes         TEXT,
    created_by    INTEGER REFERENCES users(id),
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by   INTEGER REFERENCES users(id),
    modified_at   TEXT
);

CREATE TABLE IF NOT EXISTS sales_invoice_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL REFERENCES sales_invoices(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   REAL NOT NULL,
    rate       REAL NOT NULL,
    amount     REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sales_returns (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no  TEXT UNIQUE NOT NULL,
    return_date  TEXT NOT NULL,
    customer_id  INTEGER NOT NULL REFERENCES customers(id),
    invoice_id   INTEGER REFERENCES sales_invoices(id),
    warehouse_id INTEGER REFERENCES warehouses(id),
    subtotal     REAL DEFAULT 0,
    total        REAL DEFAULT 0,
    notes        TEXT,
    created_by   INTEGER REFERENCES users(id),
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by  INTEGER REFERENCES users(id),
    modified_at  TEXT
);

CREATE TABLE IF NOT EXISTS sales_return_items (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    return_id  INTEGER NOT NULL REFERENCES sales_returns(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id),
    quantity   REAL NOT NULL,
    rate       REAL NOT NULL,
    amount     REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS inventory_movements (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    movement_date  TEXT NOT NULL,
    product_id     INTEGER NOT NULL REFERENCES products(id),
    warehouse_id   INTEGER NOT NULL REFERENCES warehouses(id),
    movement_type  TEXT NOT NULL CHECK(movement_type IN ('in','out','adjustment','transfer')),
    quantity       REAL NOT NULL,
    reference_type TEXT,
    reference_id   INTEGER,
    reference_no   TEXT,
    reason         TEXT,
    created_by     INTEGER REFERENCES users(id),
    created_at     TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by    INTEGER REFERENCES users(id),
    modified_at    TEXT
);

CREATE TABLE IF NOT EXISTS journal_vouchers (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no  TEXT UNIQUE NOT NULL,
    voucher_date TEXT NOT NULL,
    description  TEXT,
    total_debit  REAL DEFAULT 0,
    total_credit REAL DEFAULT 0,
    status       TEXT DEFAULT 'posted' CHECK(status IN ('draft','posted','cancelled')),
    created_by   INTEGER REFERENCES users(id),
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by  INTEGER REFERENCES users(id),
    modified_at  TEXT
);

CREATE TABLE IF NOT EXISTS journal_voucher_lines (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    voucher_id  INTEGER NOT NULL REFERENCES journal_vouchers(id) ON DELETE CASCADE,
    account_id  INTEGER NOT NULL REFERENCES chart_of_accounts(id),
    description TEXT,
    debit       REAL DEFAULT 0,
    credit      REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cash_receipts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no  TEXT UNIQUE NOT NULL,
    receipt_date TEXT NOT NULL,
    account_id   INTEGER REFERENCES chart_of_accounts(id),
    party_type   TEXT,
    party_id     INTEGER,
    description  TEXT NOT NULL,
    reference_no TEXT,
    amount       REAL NOT NULL,
    created_by   INTEGER REFERENCES users(id),
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by  INTEGER REFERENCES users(id),
    modified_at  TEXT
);

CREATE TABLE IF NOT EXISTS cash_payments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no  TEXT UNIQUE NOT NULL,
    payment_date TEXT NOT NULL,
    account_id   INTEGER REFERENCES chart_of_accounts(id),
    party_type   TEXT,
    party_id     INTEGER,
    description  TEXT NOT NULL,
    reference_no TEXT,
    amount       REAL NOT NULL,
    created_by   INTEGER REFERENCES users(id),
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by  INTEGER REFERENCES users(id),
    modified_at  TEXT
);

CREATE TABLE IF NOT EXISTS bank_receipts (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no  TEXT UNIQUE NOT NULL,
    receipt_date TEXT NOT NULL,
    account_id   INTEGER REFERENCES chart_of_accounts(id),
    party_type   TEXT,
    party_id     INTEGER,
    description  TEXT NOT NULL,
    reference_no TEXT,
    amount       REAL NOT NULL,
    created_by   INTEGER REFERENCES users(id),
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by  INTEGER REFERENCES users(id),
    modified_at  TEXT
);

CREATE TABLE IF NOT EXISTS bank_payments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no  TEXT UNIQUE NOT NULL,
    payment_date TEXT NOT NULL,
    account_id   INTEGER REFERENCES chart_of_accounts(id),
    party_type   TEXT,
    party_id     INTEGER,
    description  TEXT NOT NULL,
    reference_no TEXT,
    amount       REAL NOT NULL,
    created_by   INTEGER REFERENCES users(id),
    created_at   TEXT DEFAULT CURRENT_TIMESTAMP,
    modified_by  INTEGER REFERENCES users(id),
    modified_at  TEXT
);

-- ============================================================================
-- INDEXES
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);

CREATE INDEX IF NOT EXISTS idx_customers_code ON customers(code);
CREATE INDEX IF NOT EXISTS idx_customers_name ON customers(name);
CREATE INDEX IF NOT EXISTS idx_suppliers_code ON suppliers(code);
CREATE INDEX IF NOT EXISTS idx_suppliers_name ON suppliers(name);
CREATE INDEX IF NOT EXISTS idx_products_code ON products(code);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_products_unit ON products(unit_id);

CREATE INDEX IF NOT EXISTS idx_coa_code ON chart_of_accounts(code);
CREATE INDEX IF NOT EXISTS idx_coa_group ON chart_of_accounts(account_group_id);

CREATE INDEX IF NOT EXISTS idx_po_supplier ON purchase_orders(supplier_id);
CREATE INDEX IF NOT EXISTS idx_po_date ON purchase_orders(order_date);
CREATE INDEX IF NOT EXISTS idx_pi_supplier ON purchase_invoices(supplier_id);
CREATE INDEX IF NOT EXISTS idx_pi_date ON purchase_invoices(invoice_date);
CREATE INDEX IF NOT EXISTS idx_pi_doc ON purchase_invoices(document_no);
CREATE INDEX IF NOT EXISTS idx_pr_supplier ON purchase_returns(supplier_id);

CREATE INDEX IF NOT EXISTS idx_so_customer ON sales_orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_so_date ON sales_orders(order_date);
CREATE INDEX IF NOT EXISTS idx_si_customer ON sales_invoices(customer_id);
CREATE INDEX IF NOT EXISTS idx_si_date ON sales_invoices(invoice_date);
CREATE INDEX IF NOT EXISTS idx_si_doc ON sales_invoices(document_no);
CREATE INDEX IF NOT EXISTS idx_sr_customer ON sales_returns(customer_id);

CREATE INDEX IF NOT EXISTS idx_inv_mov_product ON inventory_movements(product_id);
CREATE INDEX IF NOT EXISTS idx_inv_mov_warehouse ON inventory_movements(warehouse_id);
CREATE INDEX IF NOT EXISTS idx_inv_mov_date ON inventory_movements(movement_date);

CREATE INDEX IF NOT EXISTS idx_jv_date ON journal_vouchers(voucher_date);
CREATE INDEX IF NOT EXISTS idx_cash_rcpt_date ON cash_receipts(receipt_date);
CREATE INDEX IF NOT EXISTS idx_cash_pay_date ON cash_payments(payment_date);
CREATE INDEX IF NOT EXISTS idx_bank_rcpt_date ON bank_receipts(receipt_date);
CREATE INDEX IF NOT EXISTS idx_bank_pay_date ON bank_payments(payment_date);
