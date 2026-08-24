-- Job cards: gravure / corrugated — actual consumption & production posting

CREATE TABLE IF NOT EXISTS job_cards (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_no TEXT UNIQUE NOT NULL,
    job_type TEXT NOT NULL CHECK(job_type IN ('gravure', 'corrugated')),
    job_date TEXT NOT NULL,
    job_name TEXT NOT NULL,
    finished_product_id INTEGER REFERENCES products(id),
    warehouse_id INTEGER REFERENCES warehouses(id),
    status TEXT DEFAULT 'draft' CHECK(status IN ('draft', 'posted', 'cancelled')),
    weight_after_printing REAL DEFAULT 0,
    weight_after_lamination REAL DEFAULT 0,
    weight_after_slitting REAL DEFAULT 0,
    total_reels_qty REAL DEFAULT 0,
    bag_making_qty REAL DEFAULT 0,
    production_sheets REAL DEFAULT 0,
    production_cartons REAL DEFAULT 0,
    production_time_hrs REAL DEFAULT 0,
    finished_qty REAL DEFAULT 0,
    total_reel_cost REAL DEFAULT 0,
    total_consumable_cost REAL DEFAULT 0,
    total_material_cost REAL DEFAULT 0,
    cost_per_unit REAL DEFAULT 0,
    remarks TEXT,
    final_remarks TEXT,
    supervisor TEXT,
    manager TEXT,
    accounts_ref TEXT,
    posting_number TEXT,
    created_by INTEGER REFERENCES users(id),
    created_at TEXT DEFAULT (datetime('now')),
    posted_by INTEGER REFERENCES users(id),
    posted_at TEXT,
    modified_by INTEGER REFERENCES users(id),
    modified_at TEXT
);

CREATE TABLE IF NOT EXISTS job_card_reel_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_card_id INTEGER NOT NULL REFERENCES job_cards(id) ON DELETE CASCADE,
    line_no INTEGER DEFAULT 0,
    product_id INTEGER REFERENCES products(id),
    reel_label TEXT,
    paper_type TEXT,
    grammage REAL DEFAULT 0,
    size_spec TEXT,
    ups REAL DEFAULT 0,
    weight_kg REAL DEFAULT 0,
    rate REAL DEFAULT 0,
    amount REAL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS job_card_consumable_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_card_id INTEGER NOT NULL REFERENCES job_cards(id) ON DELETE CASCADE,
    line_no INTEGER DEFAULT 0,
    section TEXT DEFAULT 'chemical',
    product_id INTEGER REFERENCES products(id),
    item_name TEXT,
    issued_qty REAL DEFAULT 0,
    returned_qty REAL DEFAULT 0,
    qty_used REAL DEFAULT 0,
    rate REAL DEFAULT 0,
    amount REAL DEFAULT 0,
    remarks TEXT
);

CREATE INDEX IF NOT EXISTS idx_job_cards_date ON job_cards(job_date);
CREATE INDEX IF NOT EXISTS idx_job_cards_type ON job_cards(job_type);
CREATE INDEX IF NOT EXISTS idx_job_cards_status ON job_cards(status);
