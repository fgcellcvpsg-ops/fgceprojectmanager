import os, sys
from sqlalchemy import text
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app import app, db

def run():
    with app.app_context():
        conn = db.engine.connect()
        rows = conn.execute(text("PRAGMA table_info(project)")).mappings().all()
        has_col = any(r.get('name') == 'is_archived' for r in rows)
        if not has_col:
            print("is_archived not present")
            return
        try:
            conn.execute(text("ALTER TABLE project DROP COLUMN is_archived"))
            print("Dropped is_archived")
        except Exception as e:
            print("Drop failed:", e)

if __name__ == "__main__":
    run()
