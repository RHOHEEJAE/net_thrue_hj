-- ============================================================
-- 헥토 행동데이터 수집 — 이벤트 및 집계 테이블 DDL
-- 1. 원시 이벤트 2. 페이지별 이벤트 집계 3. 퍼널 단계별 이탈률 집계 4. 스크롤·인터랙션 히트맵 요약
-- ============================================================

-- 1) 원시 이벤트 테이블 (Kafka 컨슈머 적재용)
CREATE TABLE IF NOT EXISTS raw_events (
    id              BIGSERIAL PRIMARY KEY,
    tag_code        VARCHAR(200),
    act_type        VARCHAR(100) NOT NULL,
    event_trigger   VARCHAR(200),
    channel         VARCHAR(100) DEFAULT 'Rround',
    page_url        TEXT,
    page_id         VARCHAR(500),
    referer_url     TEXT,
    context         JSONB,
    payload         JSONB,
    client_ts       BIGINT,
    server_ts       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ip              VARCHAR(45),
    user_agent      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_raw_events_server_ts ON raw_events (server_ts);
CREATE INDEX IF NOT EXISTS idx_raw_events_page_id ON raw_events (page_id);
CREATE INDEX IF NOT EXISTS idx_raw_events_act_type ON raw_events (act_type);
CREATE INDEX IF NOT EXISTS idx_raw_events_channel ON raw_events (channel);
CREATE INDEX IF NOT EXISTS idx_raw_events_client_ts ON raw_events (client_ts);

-- 2) 페이지별 이벤트 집계 (일 단위: 페이지·행동유형·트리거별 건수)
CREATE TABLE IF NOT EXISTS agg_page_events (
    id              SERIAL PRIMARY KEY,
    stat_date       DATE NOT NULL,
    page_id         VARCHAR(500) NOT NULL,
    channel         VARCHAR(100) NOT NULL DEFAULT 'Rround',
    act_type        VARCHAR(100) NOT NULL,
    event_trigger   VARCHAR(200) NOT NULL DEFAULT '',
    event_count     BIGINT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (stat_date, page_id, channel, act_type, event_trigger)
);

CREATE INDEX IF NOT EXISTS idx_agg_page_events_stat_date ON agg_page_events (stat_date);
CREATE INDEX IF NOT EXISTS idx_agg_page_events_page_id ON agg_page_events (page_id);
CREATE INDEX IF NOT EXISTS idx_agg_page_events_act_type ON agg_page_events (act_type);

-- 3) 퍼널 정의 (이벤트 시퀀스: 상품조회 → 장바구니 → 결제 등)
CREATE TABLE IF NOT EXISTS funnel_definition (
    id              SERIAL PRIMARY KEY,
    funnel_code     VARCHAR(100) NOT NULL UNIQUE,
    funnel_name     VARCHAR(200) NOT NULL,
    steps          JSONB NOT NULL,
    enabled        BOOLEAN NOT NULL DEFAULT true,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON COLUMN funnel_definition.steps IS '예: [{"step":1,"name":"상품조회","page_id_pattern":"product/detail%"},{"step":2,"name":"장바구니","page_id_pattern":"order/cart"},{"step":3,"name":"결제","page_id_pattern":"order/payment"}]';

-- 3-2) 퍼널 단계별 이탈률 집계 (일 단위)
CREATE TABLE IF NOT EXISTS agg_funnel_daily (
    id                  SERIAL PRIMARY KEY,
    funnel_id           INT NOT NULL REFERENCES funnel_definition(id) ON DELETE CASCADE,
    stat_date           DATE NOT NULL,
    step_order          INT NOT NULL,
    step_name           VARCHAR(200) NOT NULL,
    users_entered       BIGINT NOT NULL DEFAULT 0,
    users_completed     BIGINT NOT NULL DEFAULT 0,
    users_dropped       BIGINT NOT NULL DEFAULT 0,
    drop_off_rate       NUMERIC(10,4),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (funnel_id, stat_date, step_order)
);

CREATE INDEX IF NOT EXISTS idx_agg_funnel_daily_funnel_date ON agg_funnel_daily (funnel_id, stat_date);

-- 4) 스크롤·인터랙션 히트맵 요약 집계
-- type: 'scroll' | 'click'  /  scroll_bucket: 25,50,75,99  /  element_key: click_text 또는 class_name 요약
CREATE TABLE IF NOT EXISTS agg_heatmap (
    id              SERIAL PRIMARY KEY,
    stat_date       DATE NOT NULL,
    page_id         VARCHAR(500) NOT NULL,
    channel         VARCHAR(100) NOT NULL DEFAULT 'Rround',
    heatmap_type    VARCHAR(20) NOT NULL,
    segment_key     VARCHAR(500) NOT NULL,
    event_count     BIGINT NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (stat_date, page_id, channel, heatmap_type, segment_key)
);

CREATE INDEX IF NOT EXISTS idx_agg_heatmap_stat_date ON agg_heatmap (stat_date);
CREATE INDEX IF NOT EXISTS idx_agg_heatmap_page_id ON agg_heatmap (page_id);
CREATE INDEX IF NOT EXISTS idx_agg_heatmap_type ON agg_heatmap (heatmap_type);

-- 기본 퍼널 정의 예시 (상품조회 → 장바구니 → 결제)
INSERT INTO funnel_definition (funnel_code, funnel_name, steps)
VALUES (
    'commerce_purchase',
    '상품조회 → 장바구니 → 결제',
    '[
        {"step": 1, "name": "상품조회", "page_id_pattern": "product/detail"},
        {"step": 2, "name": "장바구니", "page_id_pattern": "order/cart"},
        {"step": 3, "name": "결제", "page_id_pattern": "order/payment"}
    ]'::jsonb
)
ON CONFLICT (funnel_code) DO NOTHING;

-- 사용 안내:
-- 1. Kafka 컨슈머로 raw_events + agg_page_events, agg_heatmap 적재: python -m kafka_client.consumer
-- 2. 퍼널 일별 집계: python run_funnel_agg.py [YYYY-MM-DD]  또는 대시보드에서 "퍼널 집계 실행" 버튼
