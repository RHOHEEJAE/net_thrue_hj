#!/bin/sh
# docker compose 기동 시 DB 초기화: 테이블 생성 + admin 계정 생성
# POSTGRES_* 또는 PGHOST/PGUSER/PGDATABASE/PGPASSWORD 환경변수 필요
set -e
H="${PGHOST:-postgres}"
U="${PGUSER:-testuser}"
DB="${PGDATABASE:-testdb}"
echo "[init-db] Waiting for Postgres at $H..."
until pg_isready -h "$H" -U "$U" -d "$DB"; do sleep 2; done
echo "[init-db] Running migrations..."
psql -h "$H" -U "$U" -d "$DB" -f /app/create_user_table.sql
psql -h "$H" -U "$U" -d "$DB" -f /app/db/add_user_roles_and_approval.sql
psql -h "$H" -U "$U" -d "$DB" -f /app/db/create_analytics_tables.sql
psql -h "$H" -U "$U" -d "$DB" -f /app/db/init_admin.sql
echo "[init-db] Done. admin/admin account ready."
