from fastapi import FastAPI, Request, Response, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, JSONResponse
from datetime import datetime, date, timedelta
import os
import jwt
from typing import Optional
from dotenv import load_dotenv

load_dotenv()  # .env 파일 로드 (로컬 개발용, Vercel에서는 환경변수 직접 주입)

from repo.config_repo import (
    get_variables, get_variables_full, upsert_variables, replace_variables,
    get_variable_groups_full, upsert_variable_groups, replace_variable_groups,
    get_triggers, get_triggers_full, upsert_triggers, replace_triggers,
    get_tags, get_tags_full, upsert_tags, replace_tags,
    load_latest_settings, save_latest_settings,
    save_settings_version, list_settings_versions,
    get_settings_version, delete_settings_version,
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
    insert_raw_event,
    process_event_aggregations,
)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("ALLOWED_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# JWT 시크릿 — Vercel 환경변수 JWT_SECRET 에서 읽음 (없으면 고정값 사용)
JWT_SECRET = os.environ.get("JWT_SECRET", "ntm_jwt_secret_change_me")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24


def _create_jwt(username: str, role: str) -> str:
    payload = {
        "sub": username,
        "role": role,
        "exp": datetime.utcnow() + timedelta(hours=JWT_EXPIRE_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _decode_jwt(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None


def get_session_user(request: Request) -> Optional[dict]:
    token = request.cookies.get("session_token")
    if not token:
        return None
    payload = _decode_jwt(token)
    if not payload:
        return None
    return {"username": payload["sub"], "role": payload.get("role", "user")}


def check_login(request: Request) -> bool:
    return get_session_user(request) is not None


def require_login(request: Request):
    if not check_login(request):
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    return True


def require_admin(request: Request):
    user = get_session_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="관리자만 접근할 수 있습니다")
    return True


def _event_type_to_dom_event(event_type: str, event_config: dict) -> str:
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


def _make_json_safe(obj):
    if obj is None:
        return None
    if isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, list):
        return [_make_json_safe(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    return str(obj)


# ======================
# SDK 설정 제공
# ======================
@app.get("/")
def root():
    return RedirectResponse(url="/static/login.html")


@app.get("/settings/latest")
def get_latest_settings():
    return load_latest_settings()


# ======================
# 이벤트 수집 → Supabase 직접 적재
# ======================
@app.post("/collect")
async def collect(req: Request):
    try:
        body = await req.json()
    except Exception as e:
        print("[COLLECT] invalid json", e)
        return JSONResponse(content={"ok": False, "error": "invalid body"}, status_code=400)

    settings = load_latest_settings()
    enabled_vars = set(settings.get("variables") or [])
    context = {k: v for k, v in body.items() if k in enabled_vars and not k.startswith("page_") and k != "ts"}

    page_url = body.get("page_url") or ""
    page_id = body.get("page_id")
    if not page_id and page_url:
        page_id = page_url.replace("https://ecommerce-dev.hectoinnovation.co.kr/", "").lstrip("/")
    channel = body.get("channel") or "Rround"
    referer_url = body.get("referer_url") or body.get("referrer") or ""

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
        raw_id = insert_raw_event(event)
        if raw_id is not None:
            server_ts = event.get("server_ts")
            try:
                stat_date = datetime.fromisoformat(server_ts).date() if server_ts else date.today()
            except Exception:
                stat_date = date.today()
            process_event_aggregations(event, stat_date)
        print("[COLLECT→DB]", event.get("act_type"), event.get("event_trigger"))
    except Exception as e:
        print("[COLLECT] DB insert failed:", e)
        return JSONResponse(content={"ok": False, "error": "insert failed"}, status_code=503)

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
            raise HTTPException(status_code=401, detail="가입 승인 대기 중입니다. 관리자 승인 후 로그인할 수 있습니다.")
        if not ok:
            raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다")

        token = _create_jwt(username, role or "user")
        redirect_url = "/static/dashboard.html" if (role or "user") == "user" else "/static/admin.html"
        response = JSONResponse(content={"success": True, "message": "로그인 성공", "role": role, "redirectUrl": redirect_url})
        is_https = request.url.scheme == "https"
        response.set_cookie(key="session_token", value=token, httponly=True, samesite="lax", max_age=86400, secure=is_https)
        print(f"[LOGIN] {username} 로그인 성공 (role={role})")
        return response
    except HTTPException:
        raise
    except Exception as e:
        print(f"[ERROR] 로그인 처리 중 오류: {e}")
        raise HTTPException(status_code=500, detail=f"로그인 처리 중 오류가 발생했습니다: {str(e)}")


@app.post("/api/logout")
async def logout():
    response = JSONResponse(content={"success": True})
    response.delete_cookie(key="session_token")
    return response


@app.get("/api/check-auth")
def check_auth(request: Request):
    user = get_session_user(request)
    if not user:
        return {"authenticated": False, "role": None}
    return {"authenticated": True, "role": user.get("role") or "user", "username": user.get("username")}


@app.post("/api/signup")
async def signup(request: Request):
    try:
        body = await request.json()
        username = body.get("username", "").strip()
        password = body.get("password", "")

        if not username or not password:
            raise HTTPException(status_code=400, detail="아이디와 비밀번호를 입력해주세요")
        if len(username) < 3:
            raise HTTPException(status_code=400, detail="아이디는 최소 3자 이상이어야 합니다")
        if len(password) < 4:
            raise HTTPException(status_code=400, detail="비밀번호는 최소 4자 이상이어야 합니다")

        try:
            if create_user(username, password):
                return JSONResponse(content={"success": True, "message": "가입 신청이 완료되었습니다. 관리자 승인 후 로그인할 수 있습니다."})
            else:
                return JSONResponse(content={"success": False, "message": "이미 존재하는 아이디입니다."}, status_code=400)
        except Exception as db_error:
            if "duplicate" in str(db_error).lower() or "unique" in str(db_error).lower():
                return JSONResponse(content={"success": False, "message": "이미 존재하는 아이디입니다."}, status_code=400)
            raise HTTPException(status_code=500, detail="계정 생성 중 오류가 발생했습니다")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"회원가입 처리 중 오류가 발생했습니다: {str(e)}")


@app.post("/api/create-user")
async def create_user_endpoint(request: Request, _: bool = Depends(require_admin)):
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
            return JSONResponse(content={"success": True, "message": f"사용자 '{username}' 생성·승인 완료"})
        else:
            return JSONResponse(content={"success": False, "message": f"사용자 '{username}'가 이미 존재합니다"}, status_code=400)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"계정 생성 중 오류가 발생했습니다: {str(e)}")


# ======================
# 관리자: 설정 조회/저장
# ======================
@app.get("/admin/config")
def admin_config(_: bool = Depends(require_admin)):
    return {
        "variables": get_variables_full(),
        "variable_groups": get_variable_groups_full(),
        "triggers": get_triggers_full(),
        "tags": get_tags_full(),
    }


@app.post("/admin/config")
def admin_save(payload: dict, _: bool = Depends(require_admin)):
    upsert_variables(payload.get("variables", []))
    upsert_variable_groups(payload.get("variable_groups", []))
    upsert_triggers(payload.get("triggers", []))
    upsert_tags(payload.get("tags", []))
    return {"ok": True}


# ======================
# 배포 (DB 저장 기반)
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

    save_latest_settings(settings)
    save_settings_version(version, comment, deployed_at, deployed_by_name, deployed_by_affiliation, settings)

    print("[DEPLOY]", version, deployed_by_name or "-", deployed_by_affiliation or "-", comment or "(코멘트 없음)")
    return {"ok": True, "version": version, "comment": comment, "name": deployed_by_name, "affiliation": deployed_by_affiliation}


@app.get("/admin/deploy/versions")
def admin_deploy_versions(_: bool = Depends(require_admin)):
    versions = list_settings_versions()
    current_settings = load_latest_settings()
    current = None
    if current_settings.get("version"):
        current = {
            "version": current_settings.get("version"),
            "comment": current_settings.get("comment", ""),
            "deployed_at": current_settings.get("deployed_at", ""),
            "deployed_by_name": current_settings.get("deployed_by_name", ""),
            "deployed_by_affiliation": current_settings.get("deployed_by_affiliation", ""),
        }
    return {"versions": versions, "current": current}


@app.post("/admin/deploy/rollback")
async def admin_deploy_rollback(request: Request, _: bool = Depends(require_admin)):
    try:
        body = await request.json()
    except Exception:
        body = {}
    version = (body.get("version") or "").strip()
    if not version:
        raise HTTPException(status_code=400, detail="version 이 필요합니다")

    settings = get_settings_version(version)
    if settings is None:
        raise HTTPException(status_code=404, detail=f"버전 '{version}'을 찾을 수 없습니다")

    save_latest_settings(settings)

    if "variables_full" in settings and isinstance(settings["variables_full"], list):
        replace_variables(settings["variables_full"])
    if "triggers_full" in settings and isinstance(settings["triggers_full"], list):
        replace_triggers(settings["triggers_full"])
    if "tags_full" in settings and isinstance(settings["tags_full"], list):
        replace_tags(settings["tags_full"])
    if "variable_groups_full" in settings and isinstance(settings["variable_groups_full"], list):
        replace_variable_groups(settings["variable_groups_full"])

    print("[ROLLBACK]", version)
    return {"ok": True, "version": version, "message": f"버전 {version}(으)로 롤백되었습니다."}


@app.delete("/admin/deploy/versions/{version}")
def admin_deploy_version_delete(version: str, _: bool = Depends(require_admin)):
    version = (version or "").strip()
    if not version:
        raise HTTPException(status_code=400, detail="version 이 필요합니다")
    if ".." in version or "/" in version or "\\" in version:
        raise HTTPException(status_code=400, detail="잘못된 버전 값입니다")
    if not delete_settings_version(version):
        raise HTTPException(status_code=404, detail=f"버전 '{version}'을 찾을 수 없습니다")
    print("[DELETE_VERSION]", version)
    return {"ok": True, "version": version, "message": f"버전 {version} 이력이 삭제되었습니다."}


# ======================
# 계정 관리 (관리자 전용)
# ======================
@app.get("/api/admin/accounts")
def api_admin_accounts_list(_: bool = Depends(require_admin)):
    try:
        users = list_all_users()
        return {"ok": True, "data": users}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/admin/accounts/approve")
async def api_admin_accounts_approve(request: Request, _: bool = Depends(require_admin)):
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
        raise HTTPException(status_code=500, detail=str(e))


# ======================
# 행동 분석 대시보드 API
# ======================

def _parse_date(s: Optional[str], default: date):
    if not s:
        return default
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return default


def _empty_to_none(s: Optional[str]) -> Optional[str]:
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
    today = date.today()
    d_from = _parse_date(date_from, today - timedelta(days=30))
    d_to = _parse_date(date_to, today)
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    try:
        rows = get_agg_page_events(d_from, d_to, group_by, _empty_to_none(page_id), _empty_to_none(channel), _empty_to_none(act_type), limit)
        return {"ok": True, "data": rows, "meta": {"date_from": d_from.isoformat(), "date_to": d_to.isoformat(), "group_by": group_by}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/overview_stats")
def api_dashboard_overview_stats(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    page_id: Optional[str] = None,
    channel: Optional[str] = None,
    _: bool = Depends(require_login),
):
    today = date.today()
    d_from = _parse_date(date_from, today - timedelta(days=30))
    d_to = _parse_date(date_to, today)
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    try:
        stats = get_overview_metrics(d_from, d_to, _empty_to_none(page_id), _empty_to_none(channel))
        return {"ok": True, "data": stats, "meta": {"date_from": d_from.isoformat(), "date_to": d_to.isoformat()}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/channels")
def api_dashboard_channels(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    _: bool = Depends(require_login),
):
    today = date.today()
    d_from = _parse_date(date_from, today - timedelta(days=30))
    d_to = _parse_date(date_to, today)
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    try:
        channels = get_distinct_channels(d_from, d_to)
        return {"ok": True, "data": channels}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/funnels")
def api_dashboard_funnels(_: bool = Depends(require_login)):
    try:
        rows = get_funnel_definitions()
        return {"ok": True, "data": rows}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/dashboard/funnel_daily")
def api_dashboard_funnel_daily(
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    funnel_id: Optional[str] = None,
    _: bool = Depends(require_login),
):
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
    today = date.today()
    d_from = _parse_date(date_from, today - timedelta(days=30))
    d_to = _parse_date(date_to, today)
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    try:
        rows = get_agg_heatmap(d_from, d_to, _empty_to_none(page_id), _empty_to_none(heatmap_type), _empty_to_none(channel), limit)
        return {"ok": True, "data": rows, "meta": {"date_from": d_from.isoformat(), "date_to": d_to.isoformat()}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/dashboard/funnel_agg")
async def api_dashboard_funnel_agg(request: Request, _: bool = Depends(require_login)):
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
