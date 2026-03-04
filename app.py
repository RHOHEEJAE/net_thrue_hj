from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse
from datetime import datetime, date, timedelta
import json, os
import secrets
from typing import Optional

from repo.file_repo import (
    get_variables, get_variables_full, upsert_variables, replace_variables,
    get_variable_groups_full, upsert_variable_groups, replace_variable_groups,
    get_triggers, get_triggers_full, upsert_triggers, replace_triggers,
    get_tags, get_tags_full, upsert_tags, replace_tags
)
from repo.user_repo import verify_user, create_user, list_all_users, approve_user, get_user
from repo.analytics_repo import (
    get_agg_page_events,
    get_distinct_channels,
    get_funnel_definitions,
    get_agg_funnel_daily,
    get_agg_heatmap,
    get_overview_metrics,
    run_funnel_daily_aggregation,
)
from kafka_client.connect import get_kafka_producer

SETTINGS_DIR = "settings"
SETTINGS_VERSIONS_DIR = f"{SETTINGS_DIR}/versions"
LATEST_SETTINGS = f"{SETTINGS_DIR}/latest.json"

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "test")

# 간단한 세션 저장소 (실제 운영 환경에서는 Redis 등을 사용 권장)
sessions = {}


def get_session_token(request: Request) -> Optional[str]:
    """쿠키에서 세션 토큰 가져오기"""
    return request.cookies.get("session_token")


def get_session_user(request: Request) -> Optional[dict]:
    """현재 세션 사용자 정보. 없으면 None. 반환: { username, role }"""
    token = get_session_token(request)
    if token is None or token not in sessions:
        return None
    return sessions.get(token)


def check_login(request: Request) -> bool:
    """로그인 상태 확인"""
    return get_session_user(request) is not None


def require_login(request: Request):
    """로그인이 필요한 엔드포인트용 의존성"""
    if not check_login(request):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    return True


def require_admin(request: Request):
    """관리자만 접근 가능한 엔드포인트용 의존성"""
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="관리자만 접근할 수 있습니다")
    return True


def load_settings():
    if not os.path.exists(LATEST_SETTINGS):
        return {"variables": [], "triggers": {}, "tags": []}
    with open(LATEST_SETTINGS, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data


def _event_type_to_dom_event(event_type: str, event_config: dict) -> str:
    """설정의 event_type + event_config를 실제 DOM 이벤트명으로 변환"""
    if event_type in ("dom_ready", "DOMContentLoaded"):
        return "DOMContentLoaded"
    if event_type in ("element_click", "click"):
        return "click"
    if event_type == "custom":
        return (event_config or {}).get("event_name") or "custom"
    return event_type or "click"


def _build_trigger_map(triggers: list) -> dict:
    trigger_map = {}
    for t in triggers:
        trigger_code = t["trigger_code"]
        event_type = t.get("event_type", "click")
        event_config = t.get("event_config") or {}
        conditions = t.get("conditions") or []
        dom_event = _event_type_to_dom_event(event_type, event_config)
        base = {"conditions": conditions, "event_config": event_config}
        if trigger_code == "DOM_READY":
            trigger_map[trigger_code] = {**base, "type": "immediate"}
        else:
            trigger_map[trigger_code] = {
                **base,
                "type": "dom_event",
                "event": dom_event,
                "capture": True,
                "css_selector": event_config.get("css_selector") or "",
            }
    return trigger_map


# ======================
# SDK 설정 제공
# ======================
@app.get("/")
def root():
    """루트 접근 시 로그인 페이지로 리다이렉트"""
    return RedirectResponse(url="/static/login.html")


@app.get("/settings/latest")
def get_latest_settings():
    return load_settings()


# ======================
# 이벤트 수집 → Kafka 프로듀스
# ======================
def _make_json_safe(obj):
    """Kafka 직렬화용: None/숫자/문자열/리스트/딕셔너리만 허용"""
    if obj is None:
        return None
    if isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, list):
        return [_make_json_safe(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    return str(obj)


@app.post("/collect")
async def collect(req: Request):
    try:
        body = await req.json()
    except Exception as e:
        print("[COLLECT] invalid json", e)
        return JSONResponse(content={"ok": False, "error": "invalid body"}, status_code=400)

    settings = load_settings()
    enabled_vars = set(settings.get("variables") or [])
    context = {k: v for k, v in body.items() if k in enabled_vars and not k.startswith("page_") and k != "ts"}

    page_url = body.get("page_url") or ""
    # SDK(NTMOBJ)에서 보낸 page_id/channel/referer_url 우선 사용, 없으면 기본값
    page_id = body.get("page_id")
    if not page_id and page_url:
        page_id = page_url.replace("https://ecommerce-dev.hectoinnovation.co.kr/", "").lstrip("/")
    channel = body.get("channel") or "Rround"
    referer_url = body.get("referer_url") or body.get("referrer") or ""

    # 넷쓰루 와이즈 콜렉터와 동일한 NTMOBJ 형태로 Kafka에 실시간 프로듀스
    event = {
        "tag_code": body.get("tag_code"),
        "act_type": body.get("event_type") or body.get("act_type"),
        "event_trigger": body.get("event_trigger"),
        "channel": channel,
        "page_url": page_url,
        "page_id": page_id or "",
        "referer_url": referer_url,
        "context": _make_json_safe(context),
        "payload": _make_json_safe({k: v for k, v in body.items() if k not in ("page_url", "ts", "tag_code", "event_type", "event_trigger")}),
        "client_ts": body.get("ts"),
        "server_ts": datetime.utcnow().isoformat(),
        "ip": (req.client.host if req.client else None),
        "user_agent": req.headers.get("user-agent"),
    }
    event = _make_json_safe(event)

    try:
        producer = get_kafka_producer()
        producer.send(KAFKA_TOPIC, value=event)
        producer.flush(timeout=10)  # 수집 즉시 Kafka 전송(실시간)
        print("[COLLECT→KAFKA]", event.get("act_type"), event.get("event_trigger"), KAFKA_TOPIC)
    except Exception as e:
        print("[COLLECT] Kafka produce failed:", e)
        return JSONResponse(content={"ok": False, "error": "produce failed"}, status_code=503)

    return {"ok": True}


# ======================
# 로그인
# ======================
@app.post("/api/login")
async def login(request: Request):
    try:
        body = await request.json()
        username = body.get("username")
        password = body.get("password")

        if not username or not password:
            raise HTTPException(status_code=400, detail="아이디와 비밀번호를 입력해주세요")

        ok, role, status = verify_user(username, password)
        if not ok and status == "pending":
            print(f"[LOGIN] 사용자 {username} 로그인 실패 - 승인 대기 중")
            raise HTTPException(status_code=401, detail="가입 승인 대기 중입니다. 관리자 승인 후 로그인할 수 있습니다.")
        if not ok:
            print(f"[LOGIN] 사용자 {username} 로그인 실패 - 인증 실패")
            raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다")
        # 승인된 사용자: 세션에 role 저장
        session_token = secrets.token_urlsafe(32)
        sessions[session_token] = {
            "username": username,
            "role": role or "user",
            "created_at": datetime.utcnow().isoformat()
        }
        redirect_url = "/static/dashboard.html" if (role or "user") == "user" else "/static/admin.html"
        response = JSONResponse(content={"success": True, "message": "로그인 성공", "role": role, "redirectUrl": redirect_url})
        response.set_cookie(
            key="session_token",
            value=session_token,
            httponly=True,
            samesite="lax",
            max_age=86400  # 24시간
        )
        print(f"[LOGIN] 사용자 {username} 로그인 성공 (role={role})")
        return response
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] 로그인 처리 중 오류: {e}")
        raise HTTPException(status_code=500, detail=f"로그인 처리 중 오류가 발생했습니다: {str(e)}")


@app.post("/api/logout")
async def logout(request: Request):
    token = get_session_token(request)
    if token and token in sessions:
        del sessions[token]
    
    response = JSONResponse(content={"success": True})
    response.delete_cookie(key="session_token")
    return response


@app.get("/api/check-auth")
def check_auth(request: Request):
    """인증 상태 확인. role 포함 (admin | user)."""
    user = get_session_user(request)
    if not user:
        return {"authenticated": False, "role": None}
    return {"authenticated": True, "role": user.get("role") or "user", "username": user.get("username")}


@app.post("/api/signup")
async def signup(request: Request):
    """
    회원가입 엔드포인트
    """
    try:
        body = await request.json()
        username = body.get("username", "").strip()
        password = body.get("password", "")

        # 유효성 검사
        if not username or not password:
            raise HTTPException(status_code=400, detail="아이디와 비밀번호를 입력해주세요")

        if len(username) < 3:
            raise HTTPException(status_code=400, detail="아이디는 최소 3자 이상이어야 합니다")

        if len(password) < 4:
            raise HTTPException(status_code=400, detail="비밀번호는 최소 4자 이상이어야 합니다")

        # 사용자 생성 시도
        try:
            if create_user(username, password):
                print(f"[SIGNUP] 사용자 {username} 가입 신청 (승인 대기)")
                return JSONResponse(content={
                    "success": True, 
                    "message": "가입 신청이 완료되었습니다. 관리자 승인 후 로그인할 수 있습니다."
                })
            else:
                return JSONResponse(
                    content={"success": False, "message": "이미 존재하는 아이디입니다."}, 
                    status_code=400
                )
        except Exception as db_error:
            print(f"[ERROR] DB 오류: {db_error}")
            # 중복 키 오류 체크
            if "duplicate" in str(db_error).lower() or "unique" in str(db_error).lower():
                return JSONResponse(
                    content={"success": False, "message": "이미 존재하는 아이디입니다."}, 
                    status_code=400
                )
            raise HTTPException(status_code=500, detail="계정 생성 중 오류가 발생했습니다")
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] 회원가입 처리 중 오류: {e}")
        raise HTTPException(status_code=500, detail=f"회원가입 처리 중 오류가 발생했습니다: {str(e)}")


@app.post("/api/create-user")
async def create_user_endpoint(request: Request, _: bool = Depends(require_admin)):
    """관리자 전용: 계정 직접 생성 (승인 없이 approved 처리하려면 생성 후 승인 API 사용)"""
    try:
        body = await request.json()
        username = body.get("username", "").strip()
        password = body.get("password")

        if not username or not password:
            raise HTTPException(status_code=400, detail="아이디와 비밀번호를 입력해주세요")
        if len(username) < 3 or len(password) < 4:
            raise HTTPException(status_code=400, detail="아이디 3자 이상, 비밀번호 4자 이상")

        if create_user(username, password):
            approve_user(username, body.get("role") or "user", get_session_user(request).get("username") or "admin")
            print(f"[CREATE_USER] 사용자 {username} 생성 및 승인")
            return JSONResponse(content={"success": True, "message": f"사용자 '{username}' 생성·승인 완료"})
        else:
            return JSONResponse(content={"success": False, "message": f"사용자 '{username}'가 이미 존재합니다"}, status_code=400)
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] 계정 생성 중 오류: {e}")
        raise HTTPException(status_code=500, detail=f"계정 생성 중 오류가 발생했습니다: {str(e)}")


# ======================
# 관리자: 기존 설정 조회
# ======================
@app.get("/admin/config")
def admin_config(_: bool = Depends(require_admin)):
    return {
        "variables": get_variables_full(),
        "variable_groups": get_variable_groups_full(),
        "triggers": get_triggers_full(),
        "tags": get_tags_full(),
    }


# ======================
# 관리자: Save (파일)
# ======================
@app.post("/admin/config")
def admin_save(payload: dict, _: bool = Depends(require_admin)):
    upsert_variables(payload.get("variables", []))
    upsert_variable_groups(payload.get("variable_groups", []))
    upsert_triggers(payload.get("triggers", []))
    upsert_tags(payload.get("tags", []))
    return {"ok": True}


# ======================
# Deploy (파일 → settings, 버전별 저장)
# ======================
@app.post("/admin/deploy")
async def admin_deploy(request: Request, _: bool = Depends(require_admin)):
    try:
        body = await request.json()
    except Exception:
        body = {}
    comment = (body.get("comment") or "").strip()
    deployed_by_name = (body.get("name") or "").strip()
    deployed_by_affiliation = (body.get("affiliation") or "").strip()

    os.makedirs(SETTINGS_DIR, exist_ok=True)
    os.makedirs(SETTINGS_VERSIONS_DIR, exist_ok=True)

    variables = get_variables()
    triggers = get_triggers()
    tags = get_tags()
    trigger_map = _build_trigger_map(triggers)
    variables_full = get_variables_full()
    variable_groups_full = get_variable_groups_full()
    triggers_full = get_triggers_full()
    tags_full = get_tags_full()

    version = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    deployed_at = datetime.utcnow().isoformat() + "Z"

    settings = {
        "version": version,
        "comment": comment,
        "deployed_at": deployed_at,
        "deployed_by_name": deployed_by_name,
        "deployed_by_affiliation": deployed_by_affiliation,
        "variables": variables,
        "triggers": trigger_map,
        "tags": tags,
        "variables_full": variables_full,
        "variable_groups_full": variable_groups_full,
        "triggers_full": triggers_full,
        "tags_full": tags_full,
    }

    with open(LATEST_SETTINGS, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

    version_file = os.path.join(SETTINGS_VERSIONS_DIR, f"{version}.json")
    with open(version_file, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)

    print("[DEPLOY]", version, deployed_by_name or "-", deployed_by_affiliation or "-", comment or "(코멘트 없음)")
    return {"ok": True, "version": version, "comment": comment, "name": deployed_by_name, "affiliation": deployed_by_affiliation}


@app.get("/admin/deploy/versions")
def admin_deploy_versions(_: bool = Depends(require_admin)):
    """배포 버전 목록 (버전, 코멘트, 배포일시)"""
    if not os.path.isdir(SETTINGS_VERSIONS_DIR):
        return {"versions": [], "current": None}
    result = []
    for name in os.listdir(SETTINGS_VERSIONS_DIR):
        if not name.endswith(".json"):
            continue
        version = name[:-5]
        path = os.path.join(SETTINGS_VERSIONS_DIR, name)
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            result.append({
                "version": data.get("version", version),
                "comment": data.get("comment", ""),
                "deployed_at": data.get("deployed_at", ""),
                "deployed_by_name": data.get("deployed_by_name", ""),
                "deployed_by_affiliation": data.get("deployed_by_affiliation", ""),
            })
        except Exception:
            result.append({"version": version, "comment": "", "deployed_at": "", "deployed_by_name": "", "deployed_by_affiliation": ""})
    result.sort(key=lambda x: x["deployed_at"] or x["version"], reverse=True)

    current = None
    if os.path.exists(LATEST_SETTINGS):
        try:
            with open(LATEST_SETTINGS, "r", encoding="utf-8") as f:
                latest = json.load(f)
            current = {
                "version": latest.get("version"),
                "comment": latest.get("comment", ""),
                "deployed_at": latest.get("deployed_at", ""),
                "deployed_by_name": latest.get("deployed_by_name", ""),
                "deployed_by_affiliation": latest.get("deployed_by_affiliation", ""),
            }
        except Exception:
            pass
    return {"versions": result, "current": current}


@app.post("/admin/deploy/rollback")
async def admin_deploy_rollback(request: Request, _: bool = Depends(require_admin)):
    """지정 버전으로 롤백: latest.json 복원 + 편집용 data 파일(variables/triggers/tags) 복원"""
    try:
        body = await request.json()
    except Exception:
        body = {}
    version = (body.get("version") or "").strip()
    if not version:
        raise HTTPException(status_code=400, detail="version 이 필요합니다")
    version_file = os.path.join(SETTINGS_VERSIONS_DIR, f"{version}.json")
    if not os.path.isfile(version_file):
        raise HTTPException(status_code=404, detail=f"버전 '{version}'을 찾을 수 없습니다")
    with open(version_file, "r", encoding="utf-8") as f:
        settings = json.load(f)
    # 1) 현재 적용 설정(latest.json) 복원
    with open(LATEST_SETTINGS, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    # 2) 편집용 data 파일 복원 (있으면) → 롤백 후 관리 화면에서도 해당 버전 내용이 보이도록
    if "variables_full" in settings and isinstance(settings["variables_full"], list):
        replace_variables(settings["variables_full"])
    if "triggers_full" in settings and isinstance(settings["triggers_full"], list):
        replace_triggers(settings["triggers_full"])
    if "tags_full" in settings and isinstance(settings["tags_full"], list):
        replace_tags(settings["tags_full"])
    if "variable_groups_full" in settings and isinstance(settings["variable_groups_full"], list):
        replace_variable_groups(settings["variable_groups_full"])
    print("[ROLLBACK]", version)
    return {"ok": True, "version": version, "message": f"버전 {version}(으)로 롤백되었습니다. 페이지를 새로고침하면 편집 화면에도 반영됩니다."}


@app.delete("/admin/deploy/versions/{version}")
def admin_deploy_version_delete(version: str, _: bool = Depends(require_admin)):
    """배포 이력에서 해당 버전 삭제 (versions 폴더의 스냅샷만 삭제, 현재 적용 중인 latest.json 은 변경 없음)"""
    version = (version or "").strip()
    if not version:
        raise HTTPException(status_code=400, detail="version 이 필요합니다")
    # 파일명에 .. 등 경로 조작 방지
    if ".." in version or "/" in version or "\\" in version:
        raise HTTPException(status_code=400, detail="잘못된 버전 값입니다")
    version_file = os.path.join(SETTINGS_VERSIONS_DIR, f"{version}.json")
    if not os.path.isfile(version_file):
        raise HTTPException(status_code=404, detail=f"버전 '{version}'을 찾을 수 없습니다")
    try:
        os.remove(version_file)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"삭제 실패: {str(e)}")
    print("[DELETE_VERSION]", version)
    return {"ok": True, "version": version, "message": f"버전 {version} 이력이 삭제되었습니다."}


# ======================
# 계정 관리 (관리자 전용)
# ======================
@app.get("/api/admin/accounts")
def api_admin_accounts_list(_: bool = Depends(require_admin)):
    """전체 계정 목록 (승인 대기·승인됨, 권한 포함)"""
    try:
        users = list_all_users()
        return {"ok": True, "data": users}
    except Exception as e:
        print("[ADMIN] accounts list error:", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/accounts/approve")
async def api_admin_accounts_approve(request: Request, _: bool = Depends(require_admin)):
    """가입 승인 및 권한 지정. body: { "username": "...", "role": "admin"|"user" }"""
    try:
        body = await request.json()
    except Exception:
        body = {}
    username = (body.get("username") or "").strip()
    role = (body.get("role") or "user").strip().lower()
    if role not in ("admin", "user"):
        role = "user"
    if not username:
        raise HTTPException(status_code=400, detail="username 이 필요합니다")
    approver = (get_session_user(request) or {}).get("username") or "admin"
    try:
        if approve_user(username, role, approver):
            return {"ok": True, "message": f"'{username}' 계정을 승인했습니다. (권한: {role})"}
        raise HTTPException(status_code=404, detail="해당 사용자를 찾을 수 없습니다")
    except HTTPException:
        raise
    except Exception as e:
        print("[ADMIN] approve error:", e)
        raise HTTPException(status_code=500, detail=str(e))


# ======================
# 행동 분석 대시보드 API (로그인 필요)
# ======================

def _parse_date(s: Optional[str], default: date):
    if not s:
        return default
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return default


def _empty_to_none(s: Optional[str]) -> Optional[str]:
    """쿼리 파라미터 'undefined'·'null'·빈 문자열을 None으로 처리해 필터를 쓰지 않게 함."""
    if s is None:
        return None
    t = str(s).strip()
    if t == "" or t.lower() in ("undefined", "null"):
        return None
    return s


@app.get("/api/dashboard/page_events")
def api_dashboard_page_events(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    group_by: str = "page_id",
    page_id: Optional[str] = None,
    channel: Optional[str] = None,
    act_type: Optional[str] = None,
    limit: int = 500,
    _: bool = Depends(require_login),
):
    """페이지별 이벤트 집계. group_by: stat_date | page_id | act_type | event_trigger | channel"""
    today = date.today()
    d_from = _parse_date(date_from, today - timedelta(days=30))
    d_to = _parse_date(date_to, today)
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    page_id = _empty_to_none(page_id)
    channel = _empty_to_none(channel)
    act_type = _empty_to_none(act_type)
    try:
        rows = get_agg_page_events(d_from, d_to, group_by, page_id, channel, act_type, limit)
        return {"ok": True, "data": rows, "meta": {"date_from": d_from.isoformat(), "date_to": d_to.isoformat(), "group_by": group_by}}
    except Exception as e:
        print("[DASHBOARD] page_events error:", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/overview_stats")
def api_dashboard_overview_stats(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page_id: Optional[str] = None,
    channel: Optional[str] = None,
    _: bool = Depends(require_login),
):
    """
    개요 대시보드 상단 KPI용 방문·방문수·페이지뷰·이탈률·방문기간 지표.

    - visitor / visit 정의: (ip, stat_date) 단위로 단순화
    """
    today = date.today()
    d_from = _parse_date(date_from, today - timedelta(days=30))
    d_to = _parse_date(date_to, today)
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    page_id = _empty_to_none(page_id)
    channel = _empty_to_none(channel)
    try:
        stats = get_overview_metrics(d_from, d_to, page_id, channel)
        return {
            "ok": True,
            "data": stats,
            "meta": {
                "date_from": d_from.isoformat(),
                "date_to": d_to.isoformat(),
            },
        }
    except Exception as e:
        print("[DASHBOARD] overview_stats error:", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/channels")
def api_dashboard_channels(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    _: bool = Depends(require_login),
):
    """기간 내 조회 가능한 channel 목록 (드롭다운용)."""
    today = date.today()
    d_from = _parse_date(date_from, today - timedelta(days=30))
    d_to = _parse_date(date_to, today)
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    try:
        channels = get_distinct_channels(d_from, d_to)
        return {"ok": True, "data": channels}
    except Exception as e:
        print("[DASHBOARD] channels error:", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/funnels")
def api_dashboard_funnels(_: bool = Depends(require_login)):
    """퍼널 정의 목록"""
    try:
        rows = get_funnel_definitions()
        return {"ok": True, "data": rows}
    except Exception as e:
        print("[DASHBOARD] funnels error:", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/funnel_daily")
def api_dashboard_funnel_daily(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    funnel_id: Optional[str] = None,
    _: bool = Depends(require_login),
):
    """퍼널 일별 단계별 이탈률. funnel_id 생략 시 전체."""
    today = date.today()
    d_from = _parse_date(date_from, today - timedelta(days=30))
    d_to = _parse_date(date_to, today)
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    fid = None
    if funnel_id and str(funnel_id).strip() and str(funnel_id) not in ("undefined", "null"):
        try:
            fid = int(funnel_id)
        except (ValueError, TypeError):
            pass
    try:
        rows = get_agg_funnel_daily(d_from, d_to, fid)
        return {"ok": True, "data": rows, "meta": {"date_from": d_from.isoformat(), "date_to": d_to.isoformat()}}
    except Exception as e:
        print("[DASHBOARD] funnel_daily error:", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/heatmap")
def api_dashboard_heatmap(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page_id: Optional[str] = None,
    heatmap_type: Optional[str] = None,
    channel: Optional[str] = None,
    limit: int = 500,
    _: bool = Depends(require_login),
):
    """스크롤·클릭 히트맵 집계. heatmap_type: scroll | click"""
    today = date.today()
    d_from = _parse_date(date_from, today - timedelta(days=30))
    d_to = _parse_date(date_to, today)
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    page_id = _empty_to_none(page_id)
    heatmap_type = _empty_to_none(heatmap_type)
    channel = _empty_to_none(channel)
    try:
        rows = get_agg_heatmap(d_from, d_to, page_id, heatmap_type, channel, limit)
        return {"ok": True, "data": rows, "meta": {"date_from": d_from.isoformat(), "date_to": d_to.isoformat()}}
    except Exception as e:
        print("[DASHBOARD] heatmap error:", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/dashboard/funnel_agg")
async def api_dashboard_funnel_agg(request: Request, _: bool = Depends(require_login)):
    """퍼널 일별 집계 배치 실행 (지정 날짜 또는 어제·오늘). body: {"date": "YYYY-MM-DD"} 선택."""
    try:
        ct = request.headers.get("content-type") or ""
        body = await request.json() if "application/json" in ct else {}
    except Exception:
        body = {}
    stat_date_str = body.get("date")
    if stat_date_str:
        try:
            d = date.fromisoformat(stat_date_str[:10])
        except ValueError:
            raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
        run_funnel_daily_aggregation(d)
        return {"ok": True, "message": f"Funnel aggregation done for {d}"}
    today = date.today()
    for d in (today - timedelta(days=1), today):
        run_funnel_daily_aggregation(d)
    return {"ok": True, "message": "Funnel aggregation done for yesterday and today."}
