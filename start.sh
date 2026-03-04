#!/bin/bash
# 헥토 행동데이터 수집 — 모든 서비스 일괄 기동
# 실행: ./start.sh (또는 bash start.sh)

set -e
cd "$(dirname "$0")"
RUN_DIR=".run"
mkdir -p "$RUN_DIR"

echo "[start.sh] 프로젝트 루트: $(pwd)"

# 1) FastAPI (uvicorn)
if [ -f "$RUN_DIR/uvicorn.pid" ] && kill -0 "$(cat "$RUN_DIR/uvicorn.pid")" 2>/dev/null; then
  echo "[start.sh] uvicorn 이미 실행 중 (PID $(cat "$RUN_DIR/uvicorn.pid"))"
else
  nohup python -m uvicorn app:app --reload --host 0.0.0.0 --port 8000 > "$RUN_DIR/uvicorn.log" 2>&1 &
  echo $! > "$RUN_DIR/uvicorn.pid"
  echo "[start.sh] uvicorn 기동 (PID $!, 포트 8000)"
fi

# 2) Kafka 컨슈머
if [ -f "$RUN_DIR/consumer.pid" ] && kill -0 "$(cat "$RUN_DIR/consumer.pid")" 2>/dev/null; then
  echo "[start.sh] Kafka consumer 이미 실행 중 (PID $(cat "$RUN_DIR/consumer.pid"))"
else
  nohup python -m kafka_client.consumer > "$RUN_DIR/consumer.log" 2>&1 &
  echo $! > "$RUN_DIR/consumer.pid"
  echo "[start.sh] Kafka consumer 기동 (PID $!)"
fi

# 3) 퍼널 집계 루프 (오늘 날짜로 매분 실행)
if [ -f "$RUN_DIR/funnel_agg.pid" ] && kill -0 "$(cat "$RUN_DIR/funnel_agg.pid")" 2>/dev/null; then
  echo "[start.sh] 퍼널 집계 루프 이미 실행 중 (PID $(cat "$RUN_DIR/funnel_agg.pid"))"
else
  nohup bash run_funnel_agg_loop.sh >> "$RUN_DIR/funnel_agg.log" 2>&1 &
  echo $! > "$RUN_DIR/funnel_agg.pid"
  echo "[start.sh] 퍼널 집계 루프 기동 (PID $!, 오늘 날짜 매분)"
fi

echo "[start.sh] 완료. 로그: $RUN_DIR/uvicorn.log, $RUN_DIR/consumer.log, $RUN_DIR/funnel_agg.log | 종료: ./stop.sh"
