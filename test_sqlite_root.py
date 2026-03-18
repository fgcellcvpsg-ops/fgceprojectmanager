import sqlite3
import os

db_path = os.path.join(os.getcwd(), 'new_root.db')
if os.path.exists(db_path):
    os.remove(db_path)

print(f"Creating DB at {db_path}")
try:
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('CREATE TABLE test (id int)')
    conn.commit()
    conn.close()
    print("Success")
except Exception as e:
    print(f"Failed: {e}")
