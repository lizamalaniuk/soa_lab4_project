
import asyncio
import uuid

import httpx

from a2a.client import (
    A2ACardResolver,
    ClientConfig,
    create_client,
)
from a2a.types import (
    Message,
    Part,
    Role,
    SendMessageRequest,
)
from a2a.helpers import (
    get_artifact_text,
    get_message_text,
)

PRODUCER_URL = "http://127.0.0.1:9001"


async def main():
    async with httpx.AsyncClient(timeout=30) as http:
        # 1. Отримуємо Agent Card
        resolver = A2ACardResolver(http, PRODUCER_URL)
        card = await resolver.get_agent_card()

        print("[A2A] Producer Agent знайдено")
        print("[A2A] Назва:", card.name)

        # 2. Створюємо A2A-клієнт
        client = await create_client(
            card,
            client_config=ClientConfig(
                streaming=False
            )
        )

        try:
            # 3. Формуємо A2A-повідомлення
            message = Message(
                role=Role.ROLE_USER,
                message_id=str(uuid.uuid4()),
                parts=[
                    Part(
                        text="Опублікуй тестову подію a2a.ping"
                    )
                ],
            )

            request = SendMessageRequest(
                message=message
            )

            print("[A2A] Надсилаємо повідомлення")

            # 4. Отримуємо результат від Producer
            async for event in client.send_message(request):
                if event.HasField("message"):
                    print(
                        "[A2A] Відповідь:",
                        get_message_text(event.message)
                    )

                elif event.HasField("task"):
                    task = event.task
                    print("[A2A] Task ID:", task.id)

                    for artifact in task.artifacts:
                        print(
                            "[A2A] Результат:",
                            get_artifact_text(artifact)
                        )

                elif event.HasField("artifact_update"):
                    print(
                        "[A2A] Результат:",
                        get_artifact_text(
                            event.artifact_update.artifact
                        )
                    )

        finally:
            await client.close()


if __name__ == "__main__":
    asyncio.run(main())
