import os, sys
from sqlalchemy import text
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from app import app, db

def run():
    with app.app_context():
        conn = db.engine.connect()
        rows = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='project_owner'")).fetchall()
        if rows:
            print("project_owner exists")
            return
        conn.execute(text("""
        CREATE TABLE project_owner (
            project_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            PRIMARY KEY (project_id, user_id),
            FOREIGN KEY(project_id) REFERENCES project (id) ON DELETE CASCADE,
            FOREIGN KEY(user_id) REFERENCES user (id) ON DELETE CASCADE
        )
        """))
        print("project_owner created")

if __name__ == "__main__":
    run()
