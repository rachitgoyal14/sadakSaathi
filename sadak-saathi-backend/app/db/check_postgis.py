import os
import psycopg2

# Get NeonDB connection string from env (set in your .env for local dev)
NEONDB_URL = os.getenv("NEONDB_URL")
if not NEONDB_URL:
    raise RuntimeError("NEONDB_URL must be set in your environment; no fallback is allowed for security.")

conn = psycopg2.connect(NEONDB_URL)
cur = conn.cursor()

try:
    cur.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    cur.execute("SELECT PostGIS_Version();")
    ver = cur.fetchone()
    print("PostGIS enabled. Version:", ver[0] if ver else "(unknown)")
except Exception as e:
    print("Error:", e)
finally:
    cur.close()
    conn.close()
