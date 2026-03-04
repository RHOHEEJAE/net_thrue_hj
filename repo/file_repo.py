import json
import os
from typing import List, Dict, Optional

DATA_DIR = "data"
VARIABLES_FILE = f"{DATA_DIR}/variables.json"
TRIGGERS_FILE = f"{DATA_DIR}/triggers.json"
TAGS_FILE = f"{DATA_DIR}/tags.json"
VARIABLE_GROUPS_FILE = f"{DATA_DIR}/variable_groups.json"


def ensure_data_dir():
    """데이터 디렉토리가 없으면 생성"""
    os.makedirs(DATA_DIR, exist_ok=True)


def load_json_file(filepath: str, default: List = None) -> List:
    """JSON 파일 로드"""
    if default is None:
        default = []
    ensure_data_dir()
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return default


def save_json_file(filepath: str, data: List):
    """JSON 파일 저장"""
    ensure_data_dir()
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ======================
# Variables
# ======================
def get_variables(full: bool = False) -> List:
    """변수 목록 조회"""
    variables = load_json_file(VARIABLES_FILE)
    if full:
        return variables
    return [v["variable_code"] for v in variables if v.get("enabled", True)]


def get_variables_full() -> List[Dict]:
    """변수 전체 정보 조회"""
    return load_json_file(VARIABLES_FILE)


def upsert_variables(variables: List[Dict]):
    """변수 저장/업데이트"""
    existing = load_json_file(VARIABLES_FILE)
    existing_dict = {v["variable_code"]: v for v in existing}
    
    for var in variables:
        var_code = var.get("variable_code")
        if var_code:
            if var_code in existing_dict:
                existing_dict[var_code].update(var)
            else:
                existing_dict[var_code] = var
    
    save_json_file(VARIABLES_FILE, list(existing_dict.values()))


def replace_variables(variables: List[Dict]):
    """변수 전체 덮어쓰기 (롤백 등)"""
    save_json_file(VARIABLES_FILE, variables)


# ======================
# Variable Groups
# ======================
def get_variable_groups(full: bool = True) -> List[Dict]:
    """변수 그룹 목록 조회"""
    return load_json_file(VARIABLE_GROUPS_FILE)


def get_variable_groups_full() -> List[Dict]:
    """변수 그룹 전체 정보 조회"""
    return load_json_file(VARIABLE_GROUPS_FILE)


def upsert_variable_groups(groups: List[Dict]):
    """변수 그룹 저장/업데이트 (group_id 기준)"""
    existing = load_json_file(VARIABLE_GROUPS_FILE)
    existing_dict = {}
    for g in existing:
        gid = g.get("group_id")
        if gid:
            existing_dict[gid] = g
    for grp in groups:
        gid = grp.get("group_id")
        if gid:
            if gid in existing_dict:
                existing_dict[gid].update(grp)
            else:
                existing_dict[gid] = grp
    save_json_file(VARIABLE_GROUPS_FILE, list(existing_dict.values()))


def replace_variable_groups(groups: List[Dict]):
    """변수 그룹 전체 덮어쓰기 (롤백 등)"""
    save_json_file(VARIABLE_GROUPS_FILE, groups)


# ======================
# Triggers
# ======================
def get_triggers(full: bool = False) -> List:
    """트리거 목록 조회 (배포 시 conditions 포함)"""
    triggers = load_json_file(TRIGGERS_FILE)
    if full:
        return triggers
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
    """트리거 전체 정보 조회"""
    return load_json_file(TRIGGERS_FILE)


def upsert_triggers(triggers: List[Dict]):
    """트리거 저장/업데이트"""
    existing = load_json_file(TRIGGERS_FILE)
    existing_dict = {t["trigger_code"]: t for t in existing}
    
    for trigger in triggers:
        trigger_code = trigger.get("trigger_code")
        if trigger_code:
            if trigger_code in existing_dict:
                # 기존 항목 업데이트
                existing_dict[trigger_code].update(trigger)
            else:
                # 새 항목 추가
                existing_dict[trigger_code] = trigger
    
    save_json_file(TRIGGERS_FILE, list(existing_dict.values()))


def replace_triggers(triggers: List[Dict]):
    """트리거 전체 덮어쓰기 (롤백 등)"""
    save_json_file(TRIGGERS_FILE, triggers)


# ======================
# Tags
# ======================
def get_tags(full: bool = False) -> List:
    """태그 목록 조회"""
    tags = load_json_file(TAGS_FILE)
    if full:
        return tags
    return [
        {
            "tag_code": t["tag_code"],
            "trigger_code": (t.get("triggers") and t["triggers"] and t["triggers"][0]) or t.get("trigger_code") or "",
            "triggers": t.get("triggers") if t.get("triggers") else ([t["trigger_code"]] if t.get("trigger_code") else []),
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
    """태그 전체 정보 조회"""
    return load_json_file(TAGS_FILE)


def upsert_tags(tags: List[Dict]):
    """태그 저장/업데이트"""
    existing = load_json_file(TAGS_FILE)
    existing_dict = {t["tag_code"]: t for t in existing}
    
    for tag in tags:
        tag_code = tag.get("tag_code")
        if tag_code:
            if tag_code in existing_dict:
                # 기존 항목 업데이트
                existing_dict[tag_code].update(tag)
            else:
                # 새 항목 추가
                existing_dict[tag_code] = tag
    
    save_json_file(TAGS_FILE, list(existing_dict.values()))


def replace_tags(tags: List[Dict]):
    """태그 전체 덮어쓰기 (롤백 등)"""
    save_json_file(TAGS_FILE, tags)
