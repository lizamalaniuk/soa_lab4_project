
import os
import uuid

import httpx
import uvicorn

from starlette.applications import Starlette

from a2a.client import (
    A2ACardResolver,
    ClientConfig,
    create_client,
)
from a2a.helpers import (
    get_artifact_text,
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
    Message,
    Part,
    Role,
    SendMessageRequest,
)
from a2a.types.a2a_pb2 import TaskState


HOST = "127.0.0.1"
PORT = 9002

PRODUCER_URL = os.getenv(
    "PRODUCER_A2A_URL",
    "http://127.0.0.1:9001"
)


async def contact_producer():
    """Надсилає A2A-запит до Producer Agent."""

    async with httpx.AsyncClient(timeout=30) as http:
        resolver = A2ACardResolver(
            http,
            PRODUCER_URL
        )

        card = await resolver.get_agent_card()

        client = await create_client(
            card,
            client_config=ClientConfig(streaming=False)
        )

        try:
            message = Message(
                role=Role.ROLE_USER,
                message_id=str(uuid.uuid4()),
                parts=[
                    Part(
                        text="Опублікуй тестову подію a2a.ping"
                    )
                ]
            )

            request = SendMessageRequest(
                message=message
            )

            results = []

            async for event in client.send_message(request):
                if event.HasField("message"):
                    results.append(
                        get_message_text(event.message)
                    )

                elif event.HasField("task"):
                    task = event.task

                    for artifact in task.artifacts:
                        results.append(
                            get_artifact_text(artifact)
                        )

                    if task.status.state == TaskState.TASK_STATE_FAILED:
                        raise RuntimeError(
                            "Producer reported task failure"
                        )

                elif event.HasField("artifact_update"):
                    results.append(
                        get_artifact_text(
                            event.artifact_update.artifact
                        )
                    )

            if not results:
                raise RuntimeError(
                    "Producer returned no result"
                )

            return "\n".join(results)

        finally:
            await client.close()


class ConsumerAgentExecutor(AgentExecutor):

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
                "Consumer виконує A2A-запит"
            )
        )

        text = get_message_text(
            context.message
        ).strip()

        if text != "Перевір публікацію через Producer":
            result = (
                "Доступна команда: "
                "Перевір публікацію через Producer"
            )
        else:
            try:
                producer_result = await contact_producer()

                result = (
                    "Consumer Agent отримав результат "
                    "від Producer Agent:\n"
                    + producer_result
                )

            except (httpx.HTTPError, RuntimeError, OSError) as exc:
                print(
                    "[CONSUMER ERROR]",
                    type(exc).__name__,
                    flush=True
                )

                await updater.update_status(
                    state=TaskState.TASK_STATE_FAILED,
                    message=new_text_message(
                        "Не вдалося виконати A2A-запит"
                    )
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
                "Consumer завершив A2A-запит"
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


consumer_skill = AgentSkill(
    id="request_producer_publication",
    name="Request Producer Publication",
    description=(
        "Надсилає запит Producer Agent через A2A "
        "для створення тестової події."
    ),
    tags=["consumer", "a2a", "events"],
    examples=[
        "Перевір публікацію через Producer"
    ],
    input_modes=["text/plain"],
    output_modes=["text/plain"]
)


agent_card = AgentCard(
    name="SOA Consumer Agent",
    description=(
        "A2A-агент, який взаємодіє "
        "з SOA Producer Agent."
    ),
    version="1.0.0",
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    capabilities=AgentCapabilities(
        streaming=False
    ),
    supported_interfaces=[
        AgentInterface(
            protocol_binding="JSONRPC",
            url="http://127.0.0.1:9002",
            protocol_version="1.0"
        )
    ],
    skills=[consumer_skill]
)


handler = DefaultRequestHandler(
    agent_executor=ConsumerAgentExecutor(),
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
