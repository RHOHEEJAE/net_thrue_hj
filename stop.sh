#!/bin/bash
# 헥토 행동데이터 수집 — start.sh로 기동한 프로세스 일괄 종료

cd "$(dirname "$0")"
RUN_DIR=".run"

stop_pid() {
  local name=$1
  local pid_file=$2
  if [ -f "$pid_file" ]; then
    local pid
    pid=$(cat "$pid_file")
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
      echo "[stop.sh] $name 종료 (PID $pid)"
    else
      echo "[stop.sh] $name 이미 종료됨 (PID $pid)"
    fi
    rm -f "$pid_file"
  else
    echo "[stop.sh] $name PID 파일 없음 ($pid_file)"
  fi
}

stop_pid "uvicorn" "$RUN_DIR/uvicorn.pid"
stop_pid "Kafka consumer" "$RUN_DIR/consumer.pid"
stop_pid "퍼널 집계 루프" "$RUN_DIR/funnel_agg.pid"

# uvicorn --reload 시 자식 프로세스가 있을 수 있음
pkill -f "uvicorn app:app" 2>/dev/null || true
pkill -f "kafka_client.consumer" 2>/dev/null || true
pkill -f "run_funnel_agg_loop.sh" 2>/dev/null || true

echo "[stop.sh] 완료"
