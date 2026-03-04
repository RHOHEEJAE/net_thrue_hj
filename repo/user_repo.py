from db.connect import get_db_conn
import hashlib
from typing import Optional, Tuple, List, Dict, Any


def hash_password(password: str) -> str:
    """비밀번호 해시화"""
    return hashlib.sha256(password.encode()).hexdigest()


def create_user(username: str, password: str) -> bool:
    """회원가입 신청: status=pending, role=user 로 생성. 승인 전까지 로그인 불가."""
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        hashed_password = hash_password(password)
        cur.execute("""
            INSERT INTO tracker_user (username, password_hash, role, status)
            VALUES (%s, %s, 'user', 'pending')
            ON CONFLICT (username) DO NOTHING
        """, (username, hashed_password))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()


def verify_user(username: str, password: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """
    인증 및 승인 여부 확인.
    반환: (성공여부, role, status)
    - 비밀번호 틀림: (False, None, None)
    - 승인 대기: (False, None, 'pending')
    - 승인됨: (True, role, 'approved')
    """
    conn = None
    cur = None
    try:
        conn = get_db_conn()
        cur = conn.cursor()
        hashed_password = hash_password(password)
        cur.execute("""
            SELECT username, role, status FROM tracker_user
            WHERE username = %s AND password_hash = %s
        """, (username, hashed_password))
        result = cur.fetchone()
        if result is None:
            return (False, None, None)
        _user, role, status = result
        role = role or "user"
        status = (status or "").strip() or "pending"
        if status != "approved":
            return (False, role, status)
        return (True, role, status)
    except Exception as e:
        print(f"[ERROR] verify_user 실패: {e}")
        return (False, None, None)
    finally:
        if cur:
            cur.close()
        if conn:
            conn.close()


def get_user(username: str) -> Optional[Dict[str, Any]]:
    """사용자 정보 조회 (role, status 포함)"""
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT username, created_at, role, status, approved_at, approved_by
            FROM tracker_user WHERE username = %s
        """, (username,))
        result = cur.fetchone()
        if result:
            return {
                "username": result[0],
                "created_at": result[1],
                "role": result[2] or "user",
                "status": result[3] or "pending",
                "approved_at": result[4],
                "approved_by": result[5],
            }
        return None
    except Exception:
        try:
            cur.execute("SELECT username, created_at FROM tracker_user WHERE username = %s", (username,))
            result = cur.fetchone()
            if result:
                return {"username": result[0], "created_at": result[1], "role": "admin", "status": "approved", "approved_at": None, "approved_by": None}
        except Exception:
            pass
        return None
    finally:
        cur.close()
        conn.close()


def list_all_users() -> List[Dict[str, Any]]:
    """전체 계정 목록 (관리자용)"""
    conn = get_db_conn()
    cur = conn.cursor()
    out = []
    try:
        cur.execute("""
            SELECT username, created_at, role, status, approved_at, approved_by
            FROM tracker_user ORDER BY created_at DESC
        """)
        rows = cur.fetchall()
        for r in rows:
            out.append({
                "username": r[0],
                "created_at": r[1].isoformat() if hasattr(r[1], "isoformat") else str(r[1]),
                "role": r[2] or "user",
                "status": (r[3] or "pending").strip() or "pending",
                "approved_at": r[4].isoformat() if r[4] and hasattr(r[4], "isoformat") else (str(r[4]) if r[4] else None),
                "approved_by": r[5],
            })
        return out
    except Exception:
        try:
            cur.execute("SELECT username, created_at FROM tracker_user ORDER BY created_at DESC")
            for r in cur.fetchall():
                out.append({"username": r[0], "created_at": str(r[1]), "role": "admin", "status": "approved", "approved_at": None, "approved_by": None})
        except Exception:
            pass
        return out
    finally:
        cur.close()
        conn.close()


def approve_user(username: str, role: str, approved_by: str) -> bool:
    """가입 승인 및 권한 지정. role: admin | user"""
    if role not in ("admin", "user"):
        role = "user"
    conn = get_db_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE tracker_user SET status = 'approved', role = %s, approved_at = NOW(), approved_by = %s
            WHERE username = %s
        """, (role, approved_by, username))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()
