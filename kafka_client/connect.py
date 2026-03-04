import os
from kafka import KafkaProducer
import json

_producer = None

def get_kafka_producer():
    global _producer
    if _producer is None:
        bootstrap = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        servers = [s.strip() for s in bootstrap.split(",") if s.strip()]
        _producer = KafkaProducer(
            bootstrap_servers=servers or ["localhost:9092"],
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            linger_ms=5,
            retries=3
        )
    return _producer
