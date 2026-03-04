from db.connect import get_db_conn

def get_enabled_funcs(full: bool = False):
    conn = get_db_conn()
    cur = conn.cursor()


    for t in tags:
        cur.execute("""
            INSERT INTO tracker_func
            (tag_code, trigger_code, exec_order, func_js, enabled)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (tag_code)
            DO UPDATE SET
                trigger_code = EXCLUDED.trigger_code,
                exec_order = EXCLUDED.exec_order,
                func_js = EXCLUDED.func_js,
                enabled = EXCLUDED.enabled
        """, (
            t["tag_code"],
            t["trigger_code"],
            t["exec_order"],
            t["func_js"],
            t["enabled"]
        ))

    conn.commit()
    cur.close()
    conn.close()

    if full:
        cur.execute("""
            SELECT tag_code, trigger_code, exec_order, func_js, enabled
            FROM tracker_func
            ORDER BY exec_order
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {
                "tag_code": r[0],
                "trigger_code": r[1],
                "exec_order": r[2],
                "func_js": r[3],
                "enabled": r[4]
            }
            for r in rows
        ]

    cur.execute("""
        SELECT tag_code, trigger_code, exec_order, func_js
        FROM tracker_func
        WHERE enabled = true
        ORDER BY exec_order
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "tag_code": r[0],
            "trigger_code": r[1],
            "exec_order": r[2],
            "func_js": r[3]
        }
        for r in rows
    ]


def upsert_funcs(tags: list[dict]):
    conn = get_db_conn()
    cur = conn.cursor()
