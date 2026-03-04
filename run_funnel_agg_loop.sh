#!/bin/bash
# 퍼널 일별 집계 — 오늘 날짜로 매분 실행
# start.sh에서 백그라운드로 기동됨. 단독 실행: ./run_funnel_agg_loop.sh

set -e
cd "$(dirname "$0")"

while true; do
  TODAY=$(date +%Y-%m-%d 2>/dev/null || date "+%Y-%m-%d" 2>/dev/null)
  if [ -n "$TODAY" ]; then
    python run_funnel_agg.py "$TODAY" >> .run/funnel_agg.log 2>&1 || true
  fi
  sleep 60
done
