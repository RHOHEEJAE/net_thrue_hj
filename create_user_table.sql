-- 계정 정보 테이블 생성 쿼리
CREATE TABLE IF NOT EXISTS tracker_user (
    username VARCHAR(100) PRIMARY KEY,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 인덱스 생성 (선택사항)
CREATE INDEX IF NOT EXISTS idx_tracker_user_username ON tracker_user(username);

-- 초기 관리자 계정 생성 예시 (비밀번호: admin123)
-- INSERT INTO tracker_user (username, password_hash)
-- VALUES ('admin', '240be518fabd2724ddb6f04eeb1da5967448d7e831c08c8fa822809f74c720a9')
-- ON CONFLICT (username) DO NOTHING;
