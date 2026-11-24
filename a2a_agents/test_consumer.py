
import asyncio
import uuid

import httpx

from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.helpers import get_artifact_text, get_message_text
from a2a.types import Message, Part, Role, SendMessageRequest
from a2a.types.a2a_pb2 import TaskState


CONSUMER_URL = "http://127.0.0.1:9002"


async def main():
    async with httpx.AsyncClient(timeout=30) as http:
        resolver = A2ACardResolver(http, CONSUMER_URL)
        card = await resolver.get_agent_card()

        print("[TEST] Знайдено:", card.name)

        client = await create_client(
            card,
            client_config=ClientConfig(streaming=False)
        )

        try:
            request = SendMessageRequest(
                message=Message(
                    role=Role.ROLE_USER,
                    message_id=str(uuid.uuid4()),
                    parts=[
                        Part(
                            text="Перевір публікацію через Producer"
                        )
                    ]
                )
            )

            print("[TEST] Надсилаємо запит Consumer Agent")

            async for event in client.send_message(request):
                if event.HasField("message"):
                    print(
                        "[TEST] Повідомлення:",
                        get_message_text(event.message)
                    )

                elif event.HasField("task"):
                    print("[TEST] Task ID:", event.task.id)

                    for artifact in event.task.artifacts:
                        print(
                            "[TEST] Результат:",
                            get_artifact_text(artifact)
                        )

                    if event.task.status.state == TaskState.TASK_STATE_FAILED:
                        print("[TEST] Завдання завершилося помилкою")

                elif event.HasField("artifact_update"):
                    print(
                        "[TEST] Результат:",
                        get_artifact_text(
                            event.artifact_update.artifact
                        )
                    )

        finally:
            await client.close()


if __name__ == "__main__":
    asyncio.run(main())
