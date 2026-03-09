"""
기존 파일 기반 설정 → Supabase DB 마이그레이션 스크립트
실행: py -3 migrate_to_supabase.py

이관 대상:
  - data/variables.json        → tracker_config (key='variables')
  - data/variable_groups.json  → tracker_config (key='variable_groups')
  - data/triggers.json         → tracker_config (key='triggers')
  - data/tags.json             → tracker_config (key='tags')
  - settings/latest.json       → tracker_settings_latest
  - settings/versions/*.json   → tracker_settings_versions
"""
import json
import os
import sys
from dotenv import load_dotenv

load_dotenv()

from db.connect import get_db_conn, release_db_conn

DATA_DIR = "data"
SETTINGS_DIR = "settings"
SETTINGS_LATEST = os.path.join(SETTINGS_DIR, "latest.json")
SETTINGS_VERSIONS_DIR = os.path.join(SETTINGS_DIR, "versions")


def load_json(path, default=None):
    if not os.path.exists(path):
        print(f"  [SKIP] 파일 없음: {path}")
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def migrate_config(conn, key, filepath, default=None):
    data = load_json(filepath, default or [])
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO tracker_config (key, value, updated_at)
            VALUES (%s, %s::jsonb, NOW())
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """, (key, json.dumps(data, ensure_ascii=False)))
        conn.commit()
        count = len(data) if isinstance(data, list) else 1
        print(f"  [OK] {key}: {count}건 이관 완료")
    except Exception as e:
        conn.rollback()
        print(f"  [ERROR] {key} 이관 실패: {e}")
    finally:
        cur.close()


def migrate_latest_settings(conn):
    data = load_json(SETTINGS_LATEST)
    if data is None:
        print("  [SKIP] settings/latest.json 없음")
        return
    cur = conn.cursor()
    try:
        cur.execute("""
            INSERT INTO tracker_settings_latest (id, settings, updated_at)
            VALUES (1, %s::jsonb, NOW())
            ON CONFLICT (id) DO UPDATE SET settings = EXCLUDED.settings, updated_at = NOW()
        """, (json.dumps(data, ensure_ascii=False),))
        conn.commit()
        print(f"  [OK] latest settings: version={data.get('version', '?')} 이관 완료")
    except Exception as e:
        conn.rollback()
        print(f"  [ERROR] latest settings 이관 실패: {e}")
    finally:
        cur.close()


def migrate_versions(conn):
    if not os.path.isdir(SETTINGS_VERSIONS_DIR):
        print("  [SKIP] settings/versions/ 디렉토리 없음")
        return

    files = [f for f in os.listdir(SETTINGS_VERSIONS_DIR) if f.endswith(".json")]
    if not files:
        print("  [SKIP] 버전 파일 없음")
        return

    ok = 0
    fail = 0
    for fname in sorted(files):
        version = fname[:-5]
        path = os.path.join(SETTINGS_VERSIONS_DIR, fname)
        data = load_json(path)
        if data is None:
            continue
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
            """, (
                data.get("version", version),
                data.get("comment", ""),
                data.get("deployed_at"),
                data.get("deployed_by_name", ""),
                data.get("deployed_by_affiliation", ""),
                json.dumps(data, ensure_ascii=False),
            ))
            conn.commit()
            ok += 1
        except Exception as e:
            conn.rollback()
            print(f"  [ERROR] 버전 {version} 이관 실패: {e}")
            fail += 1
        finally:
            cur.close()

    print(f"  [OK] 버전 이력: {ok}건 성공 / {fail}건 실패")


def main():
    print("=" * 50)
    print("Supabase 마이그레이션 시작")
    print("=" * 50)

    conn = get_db_conn()
    try:
        print("\n[1/3] data/*.json → tracker_config")
        migrate_config(conn, "variables",       os.path.join(DATA_DIR, "variables.json"))
        migrate_config(conn, "variable_groups", os.path.join(DATA_DIR, "variable_groups.json"))
        migrate_config(conn, "triggers",        os.path.join(DATA_DIR, "triggers.json"))
        migrate_config(conn, "tags",            os.path.join(DATA_DIR, "tags.json"))

        print("\n[2/3] settings/latest.json → tracker_settings_latest")
        migrate_latest_settings(conn)

        print("\n[3/3] settings/versions/*.json → tracker_settings_versions")
        migrate_versions(conn)

    finally:
        release_db_conn(conn)

    print("\n" + "=" * 50)
    print("마이그레이션 완료!")
    print("=" * 50)


if __name__ == "__main__":
    main()
