-- ============================================================
-- Vercel + Supabase 마이그레이션
-- 기존 파일 기반 설정(data/*.json, settings/)을 DB로 이관
-- Supabase SQL Editor에서 실행하세요.
-- ============================================================

-- 1) 편집용 설정 저장 테이블 (data/*.json 대체)
--    key: 'variables' | 'variable_groups' | 'triggers' | 'tags'
CREATE TABLE IF NOT EXISTS tracker_config (
    key        TEXT PRIMARY KEY,
    value      JSONB NOT NULL DEFAULT '[]',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 초기 빈 행 삽입 (없으면 조회 시 NULL 반환 방지)
INSERT INTO tracker_config (key, value) VALUES
    ('variables',       '[]'),
    ('variable_groups', '[]'),
    ('triggers',        '[]'),
    ('tags',            '[]')
ON CONFLICT (key) DO NOTHING;


-- 2) 배포 최신 설정 테이블 (settings/latest.json 대체)
CREATE TABLE IF NOT EXISTS tracker_settings_latest (
    id         INT PRIMARY KEY DEFAULT 1,   -- 항상 1개 행만 존재
    settings   JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

INSERT INTO tracker_settings_latest (id, settings) VALUES (1, '{}')
ON CONFLICT (id) DO NOTHING;


-- 3) 배포 버전 이력 테이블 (settings/versions/*.json 대체)
CREATE TABLE IF NOT EXISTS tracker_settings_versions (
    version               VARCHAR(20) PRIMARY KEY,  -- '20260223_013350'
    comment               TEXT NOT NULL DEFAULT '',
    deployed_at           TIMESTAMPTZ,
    deployed_by_name      VARCHAR(200) NOT NULL DEFAULT '',
    deployed_by_affiliation VARCHAR(200) NOT NULL DEFAULT '',
    settings              JSONB NOT NULL,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_tracker_settings_versions_deployed_at
    ON tracker_settings_versions (deployed_at DESC);
