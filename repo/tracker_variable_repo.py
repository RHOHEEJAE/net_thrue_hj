from db.connect import get_db_conn

def get_enabled_variables(full: bool = False):
    conn = get_db_conn()
    cur = conn.cursor()


    for v in variables:
        cur.execute("""
            INSERT INTO tracker_variable (variable_code, enabled)
            VALUES (%s, %s)
            ON CONFLICT (variable_code)
            DO UPDATE SET enabled = EXCLUDED.enabled
        """, (v["variable_code"], v["enabled"]))

    conn.commit()
    cur.close()
    conn.close()

    if full:
        cur.execute("""
            SELECT variable_code, enabled
            FROM tracker_variable
            ORDER BY variable_code
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {"variable_code": r[0], "enabled": r[1]}
            for r in rows
        ]

    cur.execute("""
        SELECT variable_code
        FROM tracker_variable
        WHERE enabled = true
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [r[0] for r in rows]


def upsert_variables(variables: list[dict]):
    conn = get_db_conn()
    cur = conn.cursor()
