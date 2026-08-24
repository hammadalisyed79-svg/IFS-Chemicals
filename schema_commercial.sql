-- Commercial readiness: gate pass, weighbridge extensions

CREATE TABLE IF NOT EXISTS gate_passes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no TEXT UNIQUE NOT NULL,
    pass_type TEXT NOT NULL DEFAULT 'material_inward',
    pass_date TEXT NOT NULL,
    pass_time TEXT,
    vehicle_no TEXT,
    driver_name TEXT,
    party_name TEXT,
    customer_id INTEGER REFERENCES customers(id),
    supplier_id INTEGER REFERENCES suppliers(id),
    product_id INTEGER REFERENCES products(id),
    material_desc TEXT,
    quantity REAL DEFAULT 0,
    weight REAL DEFAULT 0,
    weight_slip_id INTEGER REFERENCES weight_slips(id),
    sales_invoice_id INTEGER REFERENCES sales_invoices(id),
    purchase_invoice_id INTEGER REFERENCES purchase_invoices(id),
    delivery_note_id INTEGER REFERENCES delivery_notes(id),
    grn_id INTEGER REFERENCES goods_receipt_notes(id),
    status TEXT DEFAULT 'open',
    approved_by INTEGER REFERENCES users(id),
    approved_at TEXT,
    remarks TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now')),
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_gate_pass_date ON gate_passes(pass_date);
CREATE INDEX IF NOT EXISTS idx_gate_pass_type ON gate_passes(pass_type);
