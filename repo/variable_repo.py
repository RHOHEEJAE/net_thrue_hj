from db.connect import get_db_conn


def get_enabled_variables():
    conn = get_db_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT variable_code
        FROM tracker_variable
        WHERE enabled = true
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()

    return [r[0] for r in rows]
