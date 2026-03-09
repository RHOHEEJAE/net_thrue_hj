"""
집계 테이블(raw_events, agg_page_events, agg_heatmap) INSERT/UPDATE
"""
import json
from datetime import datetime, date
from typing import Any, Optional

from db.connect import get_db_conn, release_db_conn


def _parse_server_ts(server_ts: Any) -> date:
    if isinstance(server_ts, date):
        return server_ts if isinstance(server_ts, date) else server_ts.date()
    if isinstance(server_ts, datetime):
        return server_ts.date()
    s = str(server_ts) if server_ts else ""
    if not s:
        return date.today()
    try:
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).date()
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except Exception:
        return date.today()


def insert_raw_event(event: dict) -> Optional[int]:
    """Kafka 이벤트 1건을 raw_events에 삽입. 반환: id."""
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        server_ts = event.get("server_ts")
        if isinstance(server_ts, str):
            try:
                server_ts = datetime.fromisoformat(server_ts.replace("Z", "+00:00"))
            except Exception:
                server_ts = datetime.utcnow()

        cur.execute("""
            INSERT INTO raw_events (
                tag_code, act_type, event_trigger, channel, page_url, page_id,
                referer_url, context, payload, client_ts, server_ts, ip, user_agent
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            event.get("tag_code"),
            event.get("act_type") or "unknown",
            event.get("event_trigger"),
            event.get("channel") or "Rround",
            event.get("page_url"),
            event.get("page_id") or "",
            event.get("referer_url"),
            json.dumps(event.get("context") or {}) if isinstance(event.get("context"), dict) else event.get("context"),
            json.dumps(event.get("payload") or {}) if isinstance(event.get("payload"), dict) else event.get("payload"),
            event.get("client_ts"),
            server_ts,
            event.get("ip"),
            event.get("user_agent"),
        ))
        row_id = cur.fetchone()[0]
        conn.commit()
        return row_id
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        release_db_conn(conn)


def upsert_agg_page_events(stat_date: date, page_id: str, channel: str, act_type: str, event_trigger: str):
    """페이지별 이벤트 집계 1건 증가."""
    if not page_id and not act_type:
        return
    page_id = page_id or ""
    channel = channel or "Rround"
    act_type = act_type or "unknown"
    event_trigger = event_trigger or ""
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO agg_page_events (stat_date, page_id, channel, act_type, event_trigger, event_count, updated_at)
            VALUES (%s, %s, %s, %s, %s, 1, NOW())
            ON CONFLICT (stat_date, page_id, channel, act_type, event_trigger)
            DO UPDATE SET event_count = agg_page_events.event_count + 1, updated_at = NOW()
        """, (stat_date, page_id, channel, act_type, event_trigger))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        release_db_conn(conn)


def upsert_agg_heatmap(stat_date: date, page_id: str, channel: str, heatmap_type: str, segment_key: str):
    """히트맵 집계 1건 증가 (scroll: segment_key=25|50|75|99, click: segment_key=click_text 또는 class 요약)."""
    if not segment_key or not page_id:
        return
    page_id = page_id or ""
    channel = channel or "Rround"
    # segment_key 길이 제한
    segment_key = (segment_key or "")[:500]
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO agg_heatmap (stat_date, page_id, channel, heatmap_type, segment_key, event_count, updated_at)
            VALUES (%s, %s, %s, %s, %s, 1, NOW())
            ON CONFLICT (stat_date, page_id, channel, heatmap_type, segment_key)
            DO UPDATE SET event_count = agg_heatmap.event_count + 1, updated_at = NOW()
        """, (stat_date, page_id, channel, heatmap_type, segment_key))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        release_db_conn(conn)


def process_event_aggregations(event: dict, stat_date: date):
    """한 이벤트에 대해 agg_page_events, agg_heatmap 갱신."""
    page_id = event.get("page_id") or ""
    channel = event.get("channel") or "Rround"
    act_type = event.get("act_type") or "unknown"
    event_trigger = event.get("event_trigger") or ""
    payload = event.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except Exception:
            payload = {}

    upsert_agg_page_events(stat_date, page_id, channel, act_type, event_trigger)

    if act_type == "scroll" and isinstance(payload.get("scroll_rate"), (int, float)):
        bucket = int(payload.get("scroll_rate", 0))
        if bucket in (25, 50, 75, 99):
            upsert_agg_heatmap(stat_date, page_id, channel, "scroll", str(bucket))

    if act_type == "click":
        click_text = (payload.get("click_text") or payload.get("clickText") or "")[:200]
        class_name = (payload.get("class_name") or payload.get("clickClass") or "")[:200]
        if click_text:
            upsert_agg_heatmap(stat_date, page_id, channel, "click", "text:" + click_text)
        if class_name:
            upsert_agg_heatmap(stat_date, page_id, channel, "click", "class:" + class_name)


def run_funnel_daily_aggregation(stat_date: date):
    """raw_events를 기반으로 퍼널 단계별 진입/이탈 집계. visitor = (ip, stat_date) 기준."""
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, funnel_code, funnel_name, steps FROM funnel_definition WHERE enabled = true")
        funnels = cur.fetchall()
        for funnel_id, funnel_code, funnel_name, steps in funnels:
            if steps is None:
                continue
            if isinstance(steps, dict):
                steps = [steps]
            if not isinstance(steps, list):
                continue
            steps_sorted = sorted(steps, key=lambda s: (s or {}).get("step", 0))
            patterns = [s.get("page_id_pattern", "") for s in steps_sorted]
            names = [s.get("name", f"Step{s.get('step')}") for s in steps_sorted]

            cur.execute("""
                SELECT id, ip, client_ts, page_id, act_type
                FROM raw_events
                WHERE server_ts::date = %s AND (act_type = 'pageview' OR act_type = 'click')
                ORDER BY COALESCE(ip, '') || '-' || COALESCE(client_ts::text, '0'), client_ts NULLS LAST
            """, (stat_date,))
            rows = cur.fetchall()
            visitor_max_step = {}
            for row in rows:
                rid, ip, client_ts, page_id, act_type = row
                key = (ip or "", stat_date.isoformat())
                pid = (page_id or "")[:500]
                for i, pat in enumerate(patterns):
                    if pat and pat in pid:
                        step = i + 1
                        visitor_max_step[key] = max(visitor_max_step.get(key, 0), step)
                        break

            step_entered = [0] * len(patterns)
            step_completed = [0] * len(patterns)
            for key, max_step in visitor_max_step.items():
                for step in range(1, max_step + 1):
                    step_entered[step - 1] += 1
                for step in range(1, max_step):
                    step_completed[step - 1] += 1
                if max_step == len(patterns):
                    step_completed[max_step - 1] += 1

            for i, (name, entered, completed) in enumerate(zip(names, step_entered, step_completed)):
                dropped = max(0, entered - completed)
                rate = (dropped / entered * 100) if entered else None
                cur.execute("""
                    INSERT INTO agg_funnel_daily (funnel_id, stat_date, step_order, step_name, users_entered, users_completed, users_dropped, drop_off_rate, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (funnel_id, stat_date, step_order)
                    DO UPDATE SET users_entered = EXCLUDED.users_entered, users_completed = EXCLUDED.users_completed,
                                  users_dropped = EXCLUDED.users_dropped, drop_off_rate = EXCLUDED.drop_off_rate, updated_at = NOW()
                """, (funnel_id, stat_date, i + 1, name, entered, completed, dropped, rate))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        release_db_conn(conn)


# ---------- 대시보드 조회 ----------

def get_agg_page_events(date_from: date, date_to: date, group_by: str, page_id_filter: Optional[str] = None, channel_filter: Optional[str] = None, act_type_filter: Optional[str] = None, limit: int = 500):
    """페이지별 이벤트 집계 조회. group_by: stat_date | page_id | act_type | event_trigger | channel"""
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        where = ["stat_date >= %s", "stat_date <= %s"]
        params = [date_from, date_to]
        if page_id_filter:
            where.append("page_id LIKE %s")
            params.append(f"%{page_id_filter}%")
        if channel_filter:
            where.append("channel = %s")
            params.append(channel_filter)
        if act_type_filter:
            where.append("act_type = %s")
            params.append(act_type_filter)
        w = " AND ".join(where)
        group_col = group_by if group_by in ("stat_date", "page_id", "act_type", "event_trigger", "channel") else "stat_date"
        params.append(limit)
        cur.execute(f"""
            SELECT {group_col}, SUM(event_count) AS total
            FROM agg_page_events
            WHERE {w}
            GROUP BY {group_col}
            ORDER BY total DESC
            LIMIT %s
        """, params)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        out = []
        for row in rows:
            d = dict(zip(cols, row))
            for k, v in d.items():
                if hasattr(v, "isoformat"):
                    d[k] = v.isoformat()
            out.append(d)
        return out
    finally:
        cur.close()
        release_db_conn(conn)


def get_distinct_channels(date_from: date, date_to: date) -> list:
    """기간 내 agg_page_events에 존재하는 channel 목록 (정렬)."""
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT DISTINCT channel
            FROM agg_page_events
            WHERE stat_date >= %s AND stat_date <= %s AND channel IS NOT NULL AND channel != ''
            ORDER BY channel
        """, (date_from, date_to))
        return [r[0] for r in cur.fetchall()]
    finally:
        cur.close()
        release_db_conn(conn)


def get_overview_metrics(
    date_from: date,
    date_to: date,
    page_id_filter: Optional[str] = None,
    channel_filter: Optional[str] = None,
) -> dict:
    """
    개요 대시보드용 핵심 지표 조회.

    - 방문자수: (ip, stat_date) 기준 유니크 카운트
    - 총방문 횟수: (ip, stat_date) 조합 수 (방문 = 하루 기준 세션으로 단순화)
    - 총페이지 조회수: act_type = 'pageview' 수
    - 방문당 조회수: 총페이지 조회수 / 총방문 횟수
    - 이탈률: 페이지뷰가 1건인 방문 수 / 총방문 횟수
    - 평균 방문 기간(ms): 방문별 (max(client_ts) - min(client_ts)) 평균
    """
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        where = ["server_ts::date >= %s", "server_ts::date <= %s"]
        params = [date_from, date_to]
        if page_id_filter:
            where.append("page_id LIKE %s")
            params.append(f"%{page_id_filter}%")
        if channel_filter:
            where.append("channel = %s")
            params.append(channel_filter)
        w = " AND ".join(where)

        # 방문(visit)을 (ip, stat_date) 단위로 단순 정의
        # client_ts는 밀리초 타임스탬프로 가정
        sql = f"""
            WITH visit_base AS (
                SELECT
                    server_ts::date AS stat_date,
                    COALESCE(ip, '') AS ip,
                    MIN(client_ts) AS first_ts,
                    MAX(client_ts) AS last_ts,
                    SUM(CASE WHEN act_type = 'pageview' THEN 1 ELSE 0 END) AS pageviews,
                    COUNT(*) AS events
                FROM raw_events
                WHERE {w}
                GROUP BY server_ts::date, COALESCE(ip, '')
            ),
            agg AS (
                SELECT
                    COUNT(DISTINCT ip) AS visitors,
                    COUNT(*) AS visits,
                    COALESCE(SUM(pageviews), 0) AS total_pageviews,
                    COALESCE(SUM(events), 0) AS total_events,
                    COALESCE(SUM(CASE WHEN pageviews = 1 THEN 1 ELSE 0 END), 0) AS bounces,
                    COALESCE(SUM(
                        GREATEST(
                            0,
                            COALESCE(last_ts::bigint, first_ts::bigint) - COALESCE(first_ts::bigint, last_ts::bigint)
                        )
                    ), 0) AS total_duration_ms
                FROM visit_base
            )
            SELECT
                visitors,
                visits,
                total_pageviews,
                total_events,
                CASE WHEN visits > 0
                     THEN (bounces::decimal / visits::decimal) * 100.0
                     ELSE NULL END AS bounce_rate,
                CASE WHEN visits > 0
                     THEN (total_pageviews::decimal / visits::decimal)
                     ELSE NULL END AS pages_per_visit,
                CASE WHEN visits > 0
                     THEN (total_duration_ms::decimal / visits::decimal)
                     ELSE NULL END AS avg_duration_ms
            FROM agg
        """
        cur.execute(sql, params)
        row = cur.fetchone()
        if not row:
            return {
                "visitors": 0,
                "visits": 0,
                "total_pageviews": 0,
                "total_events": 0,
                "bounce_rate": None,
                "pages_per_visit": None,
                "avg_duration_ms": None,
            }
        cols = [d[0] for d in cur.description]
        result = dict(zip(cols, row))
        return result
    finally:
        cur.close()
        release_db_conn(conn)


def get_funnel_definitions():
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT id, funnel_code, funnel_name, steps, enabled FROM funnel_definition ORDER BY id")
        return [{"id": r[0], "funnel_code": r[1], "funnel_name": r[2], "steps": r[3], "enabled": r[4]} for r in cur.fetchall()]
    finally:
        cur.close()
        release_db_conn(conn)


def get_agg_funnel_daily(date_from: date, date_to: date, funnel_id: Optional[int] = None):
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        where = ["stat_date >= %s", "stat_date <= %s"]
        params = [date_from, date_to]
        if funnel_id:
            where.append("funnel_id = %s")
            params.append(funnel_id)
        w = " AND ".join(where)
        cur.execute(f"""
            SELECT funnel_id, stat_date, step_order, step_name, users_entered, users_completed, users_dropped, drop_off_rate
            FROM agg_funnel_daily
            WHERE {w}
            ORDER BY funnel_id, stat_date, step_order
        """, params)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        out = []
        for row in rows:
            d = dict(zip(cols, row))
            for k, v in d.items():
                if hasattr(v, "isoformat"):
                    d[k] = v.isoformat()
            out.append(d)
        return out
    finally:
        cur.close()
        release_db_conn(conn)


def get_agg_heatmap(date_from: date, date_to: date, page_id_filter: Optional[str] = None, heatmap_type: Optional[str] = None, channel_filter: Optional[str] = None, limit: int = 500):
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        where = ["stat_date >= %s", "stat_date <= %s"]
        params = [date_from, date_to]
        if page_id_filter:
            where.append("page_id LIKE %s")
            params.append(f"%{page_id_filter}%")
        if heatmap_type:
            where.append("heatmap_type = %s")
            params.append(heatmap_type)
        if channel_filter:
            where.append("channel = %s")
            params.append(channel_filter)
        w = " AND ".join(where)
        params.append(limit)
        cur.execute(f"""
            SELECT stat_date, page_id, channel, heatmap_type, segment_key, SUM(event_count) AS event_count
            FROM agg_heatmap
            WHERE {w}
            GROUP BY stat_date, page_id, channel, heatmap_type, segment_key
            ORDER BY event_count DESC
            LIMIT %s
        """, params)
        cols = [d[0] for d in cur.description]
        rows = cur.fetchall()
        out = []
        for row in rows:
            d = dict(zip(cols, row))
            for k, v in d.items():
                if hasattr(v, "isoformat"):
                    d[k] = v.isoformat()
            out.append(d)
        return out
    finally:
        cur.close()
        release_db_conn(conn)
