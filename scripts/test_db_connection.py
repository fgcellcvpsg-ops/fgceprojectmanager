import os
import sqlite3
from sqlalchemy import create_engine, text

# Hardcoded path based on what we know
db_path = r"D:\Google\My Drive\FGCEProjectManager\instance\data\projects.db"
print(f"Testing path: {db_path}")

if not os.path.exists(db_path):
    print("ERROR: File does not exist!")
else:
    print("File exists.")

# Test sqlite3
try:
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("SQLite3 Connection Successful!")
    print(f"Tables: {tables}")
    conn.close()
except Exception as e:
    print(f"SQLite3 Error: {e}")

# Test SQLAlchemy
try:
    # Try with original format
    uri = f"sqlite:///{db_path}"
    print(f"Testing URI: {uri}")
    engine = create_engine(uri)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        print("SQLAlchemy Connection Successful!")
except Exception as e:
    print(f"SQLAlchemy Error: {e}")
