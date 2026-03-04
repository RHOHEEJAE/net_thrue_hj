from db.connect import get_db_conn

def get_enabled_triggers(full: bool = False):
    conn = get_db_conn()
    cur = conn.cursor()


    for t in triggers:
        cur.execute("""
            INSERT INTO tracker_trigger (trigger_code, event_type, enabled)
            VALUES (%s, %s, %s)
            ON CONFLICT (trigger_code)
            DO UPDATE SET
                event_type = EXCLUDED.event_type,
                enabled = EXCLUDED.enabled
        """, (
            t["trigger_code"],
            t["event_type"],
            t["enabled"]
        ))

    conn.commit()
    cur.close()
    conn.close()

    if full:
        cur.execute("""
            SELECT trigger_code, event_type, enabled
            FROM tracker_trigger
            ORDER BY trigger_code
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [
            {
                "trigger_code": r[0],
                "event_type": r[1],
                "enabled": r[2]
            }
            for r in rows
        ]

    cur.execute("""
        SELECT trigger_code, event_type
        FROM tracker_trigger
        WHERE enabled = true
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {"trigger_code": r[0], "event_type": r[1]}
        for r in rows
    ]


def upsert_triggers(triggers: list[dict]):
    conn = get_db_conn()
    cur = conn.cursor()
