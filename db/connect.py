import os
import psycopg2

def get_db_conn():
    return psycopg2.connect(
        host=os.environ.get("POSTGRES_HOST", "localhost"),
        port=int(os.environ.get("POSTGRES_PORT", "5432")),
        dbname=os.environ.get("POSTGRES_DB", "testdb"),
        user=os.environ.get("POSTGRES_USER", "testuser"),
        password=os.environ.get("POSTGRES_PASSWORD", "testpass"),
    )
