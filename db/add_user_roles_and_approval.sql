-- 계정 권한(관리자/사용자) 및 가입 승인용 컬럼 추가
-- 기존 계정은 role=admin, status=approved 로 설정 (최초 관리자 유지)
-- 두 번째 실행 시 컬럼이 있으면 무시되도록 DO 블록 사용

DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='tracker_user' AND column_name='role') THEN
    ALTER TABLE tracker_user ADD COLUMN role VARCHAR(20) DEFAULT 'user';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='tracker_user' AND column_name='status') THEN
    ALTER TABLE tracker_user ADD COLUMN status VARCHAR(20) DEFAULT 'pending';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='tracker_user' AND column_name='approved_at') THEN
    ALTER TABLE tracker_user ADD COLUMN approved_at TIMESTAMPTZ;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='tracker_user' AND column_name='approved_by') THEN
    ALTER TABLE tracker_user ADD COLUMN approved_by VARCHAR(100);
  END IF;
END $$;

-- 기존 행: 승인된 관리자로 간주
UPDATE tracker_user SET role = 'admin', status = 'approved', approved_at = COALESCE(approved_at, NOW()) WHERE status IS NULL OR status = '';

-- 새 가입은 status=pending, role=user (승인 시 관리자가 role 지정)
COMMENT ON COLUMN tracker_user.role IS 'admin: 관리자, user: 사용자';
COMMENT ON COLUMN tracker_user.status IS 'pending: 승인대기, approved: 승인됨';
