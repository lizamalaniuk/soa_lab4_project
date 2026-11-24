
import json
import time
import pika
from common import db


def compensate_homework(event):
    if event.get("type") != "homework.created":
        return

    data = event["data"]
    task_id = data["id"]

    r = db()
    key = "homework:" + task_id

    # Атомарно перевіряємо і змінюємо стан.
    with r.pipeline() as pipe:
        while True:
            try:
                pipe.watch(key)
                raw = pipe.get(key)

                if not raw:
                    print(
                        f"SAGA: Homework {task_id} not found",
                        flush=True
                    )
                    return

                task = json.loads(raw)

                if task["status"] == "cancelled":
                    print(
                        f"SAGA: Already cancelled {task_id}",
                        flush=True
                    )
                    return

                if task["status"] != "pending":
                    print(
                        f"SAGA: Unexpected status for {task_id}",
                        flush=True
                    )
                    return

                task["status"] = "cancelled"

                pipe.multi()
                pipe.set(key, json.dumps(task))
                pipe.execute()

                print(
                    f"SAGA COMPENSATED: {task_id}",
                    flush=True
                )
                return

            except __import__("redis").WatchError:
                continue


def main():
    while True:
        try:
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(
                    host="rabbitmq",
                    heartbeat=30
                )
            )

            channel = connection.channel()
            channel.basic_qos(prefetch_count=1)

            def callback(ch, method, properties, body):
                try:
                    event = json.loads(body)

                    compensate_homework(event)

                    ch.basic_ack(
                        delivery_tag=method.delivery_tag
                    )

                except Exception as exc:
                    print(
                        f"SAGA ERROR: {exc}",
                        flush=True
                    )

                    # Повторна доставка при тимчасовій помилці
                    ch.basic_nack(
                        delivery_tag=method.delivery_tag,
                        requeue=True
                    )

            channel.basic_consume(
                queue="homework.dlq",
                on_message_callback=callback
            )

            print(
                "SAGA Coordinator started",
                flush=True
            )

            channel.start_consuming()

        except Exception as exc:
            print(
                f"SAGA reconnect: {exc}",
                flush=True
            )
            time.sleep(3)


if __name__ == "__main__":
    main()
