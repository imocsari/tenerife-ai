# inspect_db.py
# Lists the tables and columns in your Supabase database (read-only).

import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    rows = conn.execute("""
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
    """).fetchall()

current = None
for table, column, dtype in rows:
    if table != current:
        print(f"\n{table}")
        current = table
    print(f"   {column}: {dtype}")
