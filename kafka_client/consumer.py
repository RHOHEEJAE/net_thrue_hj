"""
Kafka 토픽 컨슈머 — 수집 이벤트를 raw_events에 적재하고 페이지별·히트맵 집계 갱신.
실행: python -m kafka_client.consumer (또는 python kafka_client/consumer.py)
"""
import json
import os
import sys
import signal

from kafka import KafkaConsumer
from datetime import date

# 프로젝트 루트를 path에 추가
sys.path.insert(0, "." if "." not in sys.path else "")

from repo.analytics_repo import insert_raw_event, process_event_aggregations
from db.connect import get_db_conn


KAFKA_BOOTSTRAP = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_TOPIC = os.environ.get("KAFKA_TOPIC", "test")
GROUP_ID = os.environ.get("KAFKA_CONSUMER_GROUP", "analytics-consumer")


def run_consumer():
    consumer = KafkaConsumer(
        KAFKA_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        group_id=GROUP_ID,
        value_deserializer=lambda m: json.loads(m.decode("utf-8")) if m else {},
        auto_offset_reset="latest",
        enable_auto_commit=True,
    )

    def shutdown(sig, frame):
        consumer.close()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    for message in consumer:
        try:
            event = message.value
            if not event or not isinstance(event, dict):
                continue
            raw_id = insert_raw_event(event)
            if raw_id is None:
                continue
            server_ts = event.get("server_ts")
            if isinstance(server_ts, str) and "T" in server_ts:
                from datetime import datetime
                try:
                    dt = datetime.fromisoformat(server_ts.replace("Z", "+00:00"))
                    stat_date = dt.date()
                except Exception:
                    stat_date = date.today()
            else:
                stat_date = date.today()
            process_event_aggregations(event, stat_date)
        except Exception as e:
            print("[CONSUMER] error processing message:", e, file=sys.stderr)


if __name__ == "__main__":
    run_consumer()
