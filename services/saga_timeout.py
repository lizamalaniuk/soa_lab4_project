
import json
import time
from datetime import datetime, timezone

from common import db
from saga_coordinator import compensate_homework

# Для лабораторної встановлюємо 30 секунд
SAGA_TIMEOUT = 30


def check_timeouts():
    r = db()

    for key in r.scan_iter("outbox:*"):
        raw = r.get(key)

        if not raw:
            continue

        event = json.loads(raw)

        if event.get("type") != "homework.created":
            continue

        created_at = datetime.fromisoformat(
            event["created_at"]
        )

        elapsed = (
            datetime.now(timezone.utc) - created_at
        ).total_seconds()

        if elapsed < SAGA_TIMEOUT:
            continue

        task_id = event["data"]["id"]
        task_raw = r.get("homework:" + task_id)

        if not task_raw:
            continue

        task = json.loads(task_raw)

        if task.get("status") != "pending":
            continue

        print(
            f"SAGA TIMEOUT: {task_id}",
            flush=True
        )

        compensate_homework(event)


if __name__ == "__main__":
    print("SAGA Timeout Monitor started", flush=True)

    while True:
        try:
            check_timeouts()
        except Exception as exc:
            print(f"TIMEOUT ERROR: {exc}", flush=True)

        time.sleep(5)
