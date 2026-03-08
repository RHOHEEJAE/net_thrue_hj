"""
설정 저장소 — 기존 file_repo.py(JSON 파일)를 Supabase DB 기반으로 교체.
tracker_config 테이블: key별로 JSONB 저장.
tracker_settings_latest: 배포된 최신 설정 1행.
tracker_settings_versions: 배포 이력.
"""
import json
from typing import List, Dict, Optional, Any

from db.connect import get_db_conn, release_db_conn


# ──────────────────────────────────────────────
# 내부 헬퍼
# ──────────────────────────────────────────────

def _read_config(key: str) -> List:
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT value FROM tracker_config WHERE key = %s", (key,))
        row = cur.fetchone()
        return row[0] if row else []
    finally:
        cur.close()
        release_db_conn(conn)


def _write_config(key: str, value: List):
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO tracker_config (key, value, updated_at)
            VALUES (%s, %s::jsonb, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """, (key, json.dumps(value, ensure_ascii=False)))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        release_db_conn(conn)


# ──────────────────────────────────────────────
# Variables
# ──────────────────────────────────────────────

def get_variables() -> List[str]:
    """활성화된 변수 코드 목록만 반환 (SDK 배포용)."""
    variables = _read_config("variables")
    return [v["variable_code"] for v in variables if v.get("enabled", True)]


def get_variables_full() -> List[Dict]:
    return _read_config("variables")


def upsert_variables(variables: List[Dict]):
    existing = _read_config("variables")
    existing_dict = {v["variable_code"]: v for v in existing}
    for var in variables:
        code = var.get("variable_code")
        if code:
            if code in existing_dict:
                existing_dict[code].update(var)
            else:
                existing_dict[code] = var
    _write_config("variables", list(existing_dict.values()))


def replace_variables(variables: List[Dict]):
    _write_config("variables", variables)


# ──────────────────────────────────────────────
# Variable Groups
# ──────────────────────────────────────────────

def get_variable_groups_full() -> List[Dict]:
    return _read_config("variable_groups")


def upsert_variable_groups(groups: List[Dict]):
    existing = _read_config("variable_groups")
    existing_dict = {g["group_id"]: g for g in existing if g.get("group_id")}
    for grp in groups:
        gid = grp.get("group_id")
        if gid:
            if gid in existing_dict:
                existing_dict[gid].update(grp)
            else:
                existing_dict[gid] = grp
    _write_config("variable_groups", list(existing_dict.values()))


def replace_variable_groups(groups: List[Dict]):
    _write_config("variable_groups", groups)


# ──────────────────────────────────────────────
# Triggers
# ──────────────────────────────────────────────

def get_triggers() -> List[Dict]:
    """활성화된 트리거 (배포용)."""
    triggers = _read_config("triggers")
    return [
        {
            "trigger_code": t["trigger_code"],
            "event_type": t.get("event_type", "click"),
            "event_config": t.get("event_config") or {},
            "conditions": t.get("conditions") or [],
        }
        for t in triggers
        if t.get("enabled", True)
    ]


def get_triggers_full() -> List[Dict]:
    return _read_config("triggers")


def upsert_triggers(triggers: List[Dict]):
    existing = _read_config("triggers")
    existing_dict = {t["trigger_code"]: t for t in existing}
    for trigger in triggers:
        code = trigger.get("trigger_code")
        if code:
            if code in existing_dict:
                existing_dict[code].update(trigger)
            else:
                existing_dict[code] = trigger
    _write_config("triggers", list(existing_dict.values()))


def replace_triggers(triggers: List[Dict]):
    _write_config("triggers", triggers)


# ──────────────────────────────────────────────
# Tags
# ──────────────────────────────────────────────

def get_tags() -> List[Dict]:
    """활성화된 태그 (배포용)."""
    tags = _read_config("tags")
    return [
        {
            "tag_code": t["tag_code"],
            "trigger_code": (t.get("triggers") and t["triggers"] and t["triggers"][0]) or t.get("trigger_code") or "",
            "triggers": t.get("triggers") or ([t["trigger_code"]] if t.get("trigger_code") else []),
            "exec_order": t.get("exec_order", 999),
            "tag_type": t.get("tag_type") or "script",
            "func_js": t.get("func_js") or "",
            "send_method": t.get("send_method"),
            "log_type": t.get("log_type"),
            "log_type_path": t.get("log_type_path"),
            "parameters": t.get("parameters") or [],
            "cookies": t.get("cookies") or [],
            "run_conditions": t.get("run_conditions") or [],
            "run_condition_any": t.get("run_condition_any", False),
            "except_conditions": t.get("except_conditions") or [],
        }
        for t in sorted(tags, key=lambda x: x.get("exec_order", 999))
        if t.get("enabled", True)
    ]


def get_tags_full() -> List[Dict]:
    return _read_config("tags")


def upsert_tags(tags: List[Dict]):
    existing = _read_config("tags")
    existing_dict = {t["tag_code"]: t for t in existing}
    for tag in tags:
        code = tag.get("tag_code")
        if code:
            if code in existing_dict:
                existing_dict[code].update(tag)
            else:
                existing_dict[code] = tag
    _write_config("tags", list(existing_dict.values()))


def replace_tags(tags: List[Dict]):
    _write_config("tags", tags)


# ──────────────────────────────────────────────
# Latest Settings (배포된 설정)
# ──────────────────────────────────────────────

def load_latest_settings() -> Dict:
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT settings FROM tracker_settings_latest WHERE id = 1")
        row = cur.fetchone()
        return row[0] if row else {"variables": [], "triggers": {}, "tags": []}
    finally:
        cur.close()
        release_db_conn(conn)


def save_latest_settings(settings: Dict):
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO tracker_settings_latest (id, settings, updated_at)
            VALUES (1, %s::jsonb, NOW())
            ON CONFLICT (id) DO UPDATE SET settings = EXCLUDED.settings, updated_at = NOW()
        """, (json.dumps(settings, ensure_ascii=False),))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        release_db_conn(conn)


# ──────────────────────────────────────────────
# Settings Versions (배포 이력)
# ──────────────────────────────────────────────

def save_settings_version(version: str, comment: str, deployed_at: str,
                           deployed_by_name: str, deployed_by_affiliation: str,
                           settings: Dict):
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO tracker_settings_versions
                (version, comment, deployed_at, deployed_by_name, deployed_by_affiliation, settings)
            VALUES (%s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (version) DO UPDATE SET
                comment = EXCLUDED.comment,
                deployed_at = EXCLUDED.deployed_at,
                settings = EXCLUDED.settings
        """, (version, comment, deployed_at, deployed_by_name, deployed_by_affiliation,
              json.dumps(settings, ensure_ascii=False)))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        release_db_conn(conn)


def list_settings_versions() -> List[Dict]:
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT version, comment, deployed_at, deployed_by_name, deployed_by_affiliation
            FROM tracker_settings_versions
            ORDER BY deployed_at DESC NULLS LAST
        """)
        rows = cur.fetchall()
        result = []
        for r in rows:
            result.append({
                "version": r[0],
                "comment": r[1] or "",
                "deployed_at": r[2].isoformat() + "Z" if r[2] else "",
                "deployed_by_name": r[3] or "",
                "deployed_by_affiliation": r[4] or "",
            })
        return result
    finally:
        cur.close()
        release_db_conn(conn)


def get_settings_version(version: str) -> Optional[Dict]:
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("SELECT settings FROM tracker_settings_versions WHERE version = %s", (version,))
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        cur.close()
        release_db_conn(conn)


def delete_settings_version(version: str) -> bool:
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("DELETE FROM tracker_settings_versions WHERE version = %s", (version,))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        release_db_conn(conn)
