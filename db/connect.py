import os
import psycopg2
from psycopg2.pool import ThreadedConnectionPool
from urllib.parse import urlparse, unquote

_pool = None


def _parse_db_url(url: str) -> dict:
    """postgresql:// URI를 psycopg2 연결 파라미터 dict로 변환"""
    parsed = urlparse(url)
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "dbname": parsed.path.lstrip("/"),
        "user": unquote(parsed.username or ""),
        "password": unquote(parsed.password or ""),
    }


def _get_pool():
    global _pool
    if _pool is not None:
        return _pool

    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        # URI를 직접 파싱해 개별 파라미터로 전달 (psycopg2 URI 파싱 호환성 문제 우회)
        params = _parse_db_url(database_url)
        _pool = ThreadedConnectionPool(minconn=1, maxconn=10, **params)
    else:
        # 로컬 개발용 개별 파라미터
        _pool = ThreadedConnectionPool(
            minconn=1,
            maxconn=10,
            host=os.environ.get("POSTGRES_HOST", "localhost"),
            port=int(os.environ.get("POSTGRES_PORT", "5432")),
            dbname=os.environ.get("POSTGRES_DB", "testdb"),
            user=os.environ.get("POSTGRES_USER", "testuser"),
            password=os.environ.get("POSTGRES_PASSWORD", "testpass"),
        )
    return _pool


def get_db_conn():
    """커넥션 풀에서 연결 반환. 사용 후 반드시 conn.close() 호출 (풀에 반납)."""
    return _get_pool().getconn()


def release_db_conn(conn):
    """커넥션을 풀에 명시적으로 반납. get_db_conn() 사용 후 finally에서 호출."""
    try:
        _get_pool().putconn(conn)
    except Exception:
        pass
