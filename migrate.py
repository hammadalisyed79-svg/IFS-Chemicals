"""Run safe database migration to schema v3."""
import database as db

if __name__ == "__main__":
    db.init_db()
    info = db.get_schema_info()
    print(f"Schema version: {info['schema_version']}")
    print(f"Tables: {len(info['tables'])}")
    print("Migration complete.")
