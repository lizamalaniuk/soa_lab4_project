
import asyncio
import json
import os
import uuid
from datetime import datetime, timezone

import redis
import uvicorn

from starlette.applications import Starlette

from a2a.helpers import (
    get_message_text,
    new_task_from_user_message,
    new_text_message,
    new_text_part,
)
from a2a.server.agent_execution import (
    AgentExecutor,
    RequestContext,
)
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater

from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentInterface,
    AgentSkill,
)
from a2a.types.a2a_pb2 import TaskState


HOST = "0.0.0.0"
PORT = 9001

PUBLIC_URL = os.getenv(
    "PRODUCER_A2A_URL",
    "http://127.0.0.1:9001"
)

PING_COMMAND = "Опублікуй тестову подію a2a.ping"


def create_ping_event(task_id: str):
    """Зберігає тестову подію в Redis Outbox."""

    connection = redis.Redis(
        host="redis",
        port=6379,
        decode_responses=True,
        socket_connect_timeout=3,
        socket_timeout=3
    )

    event_id = str(uuid.uuid4())

    event = {
        "event_id": event_id,
        "type": "a2a.ping",
        "data": {
            "task_id": task_id,
            "source": "SOA Producer Agent",
            "message": "A2A test event"
        },
        "status": "pending",
        "created_at": datetime.now(
            timezone.utc
        ).isoformat()
    }

    connection.set(
        "outbox:" + event_id,
        json.dumps(event)
    )

    return event_id


class ProducerAgentExecutor(AgentExecutor):

    async def execute(
        self,
        context: RequestContext,
        event_queue: EventQueue
    ) -> None:

        task = context.current_task

        if task is None:
            task = new_task_from_user_message(
                context.message
            )
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(
            event_queue=event_queue,
            task_id=task.id,
            context_id=task.context_id
        )

        await updater.update_status(
            state=TaskState.TASK_STATE_WORKING,
            message=new_text_message(
                "Producer обробляє A2A-запит"
            )
        )

        text = get_message_text(context.message).strip()

        if text.casefold() != PING_COMMAND.casefold():
            result = (
                "Producer Agent отримав A2A-запит. "
                "Для тестової публікації надішліть: "
                + PING_COMMAND
            )
        else:
            try:
                event_id = await asyncio.to_thread(
                    create_ping_event,
                    task.id
                )

                result = (
                    "A2A-запит успішно оброблено. "
                    "Тестову подію a2a.ping "
                    "додано до Redis Outbox. "
                    "Event ID: " + event_id
                    + ". Публікацію в RabbitMQ "
                    "потрібно перевірити окремо."
                )

            except (redis.RedisError, OSError) as exc:
                await updater.update_status(
                    state=TaskState.TASK_STATE_FAILED,
                    message=new_text_message(
                        "Помилка збереження події в Outbox"
                    )
                )
                print(
                    "[A2A ERROR]",
                    type(exc).__name__,
                    flush=True
                )
                return

        await updater.add_artifact(
            parts=[
                new_text_part(
                    text=result,
                    media_type="text/plain"
                )
            ]
        )

        await updater.update_status(
            state=TaskState.TASK_STATE_COMPLETED,
            message=new_text_message(
                "A2A-запит оброблено"
            )
        )

    async def cancel(
        self,
        context: RequestContext,
        event_queue: EventQueue
    ) -> None:
        raise NotImplementedError(
            "Cancellation is not supported"
        )


producer_skill = AgentSkill(
    id="producer_messaging",
    name="Producer Messaging",
    description=(
        "Приймає A2A-запити та створює дозволену "
        "тестову подію a2a.ping у Redis Outbox."
    ),
    tags=["producer", "outbox", "rabbitmq"],
    examples=[PING_COMMAND],
    input_modes=["text/plain"],
    output_modes=["text/plain"]
)


agent_card = AgentCard(
    name="SOA Producer Agent",
    description=(
        "A2A-агент для інтеграції з Redis Outbox "
        "та RabbitMQ із лабораторної роботи №3."
    ),
    version="1.1.0",
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    capabilities=AgentCapabilities(
        streaming=False
    ),
    supported_interfaces=[
        AgentInterface(
            protocol_binding="JSONRPC",
            url=PUBLIC_URL,
            protocol_version="1.0"
        )
    ],
    skills=[producer_skill]
)


handler = DefaultRequestHandler(
    agent_executor=ProducerAgentExecutor(),
    task_store=InMemoryTaskStore(),
    agent_card=agent_card
)


routes = []
routes.extend(create_agent_card_routes(agent_card))
routes.extend(create_jsonrpc_routes(handler, "/"))

app = Starlette(routes=routes)


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=HOST,
        port=PORT
    )
