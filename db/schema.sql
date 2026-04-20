CREATE TABLE IF NOT EXISTS app_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS mapping_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    platform TEXT NOT NULL,
    match_key TEXT NOT NULL,
    remark_norm TEXT NOT NULL DEFAULT '[空]',
    biz_desc TEXT NOT NULL DEFAULT '[空]',
    detail_category TEXT NOT NULL,
    major_category TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    source_version TEXT,
    sync_time TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS mapping_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS run_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_time TEXT NOT NULL,
    input_dir TEXT NOT NULL,
    file_count INTEGER NOT NULL,
    success_count INTEGER NOT NULL,
    failed_count INTEGER NOT NULL,
    export_path TEXT,
    status TEXT NOT NULL,
    message TEXT
);
