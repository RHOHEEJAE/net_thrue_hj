-- docker compose 기동 시 초기 관리자 계정 생성 (ID: admin, PW: admin)
-- password_hash = SHA256('admin') = 8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918
INSERT INTO tracker_user (username, password_hash, role, status, approved_at, approved_by)
VALUES (
  'admin',
  '8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918',
  'admin',
  'approved',
  NOW(),
  'docker-init'
)
ON CONFLICT (username) DO UPDATE SET
  password_hash = EXCLUDED.password_hash,
  role = 'admin',
  status = 'approved',
  approved_at = NOW(),
  approved_by = 'docker-init';
