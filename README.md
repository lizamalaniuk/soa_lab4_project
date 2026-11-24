# ЛР4 SOA — інтеграція сервісних API з AI-агентами

**Тема:** Function Calling, Model Context Protocol (MCP), Agent-to-Agent (A2A).  
**Основа проєкту:** мікросервісна система керування домашніми завданнями з ЛР3 (REST API, Redis, RabbitMQ, Transactional Outbox/Inbox, SAGA).

## Мета роботи

Надати локальній LLM доступ до REST API через Function Calling, реалізувати MCP-сервер з інструментами для читання даних та організувати взаємодію Producer Agent і Consumer Agent через A2A. Перевірити обмеження викликів, валідацію аргументів і захист від недовірених даних.

## 1. Структура

```text
soa_lab4_project/
├── ai_agent/
│   ├── __init__.py
│   ├── api_client.py       # REST-клієнт до Nginx API Gateway
│   ├── tools.py            # Python-інструменти для REST API
│   ├── agent.py            # LLM + Function Calling + guardrails
│   └── test_injection.py   # тест недовіреного опису завдання
├── mcp_server/
│   ├── __init__.py
│   └── server.py           # MCP-сервер (stdio)
├── a2a_agents/
│   ├── __init__.py
│   ├── producer_agent.py   # A2A Producer, порт 9001 у Docker
│   ├── consumer_agent.py   # тестовий A2A-клієнт Producer
│   ├── consumer_server.py  # A2A Consumer, порт 9002 локально
│   └── test_consumer.py    # наскрізний A2A-тест
├── nginx/
├── services/              # мікросервіси, Publisher, Consumer, SAGA з ЛР3
├── Dockerfile.a2a
├── docker-compose.yml
└── README.md
```

## 2. Архітектура

- **REST API ЛР3:** Users, Homework і Notifications працюють через Nginx API Gateway. Дані та Outbox зберігаються в Redis; Outbox Publisher публікує події в RabbitMQ. Компоненти SAGA та звичайний RabbitMQ Consumer залишилися з попередньої лабораторної.
- **Function Calling:** локальна модель `llama3.1:8b` через Ollama вибирає інструменти Python, а програма перевіряє параметри і виконує HTTP-запити через Gateway.
- **MCP:** окремий stdio-сервер надає інструменти `list_homeworks`, `get_homework`, `get_user`; їх перевірено в MCP Inspector.
- **A2A:** клієнт звертається до Consumer Agent (`9002`), Consumer через JSON-RPC звертається до Producer Agent (`9001`), Producer записує тестову подію `a2a.ping` у Redis Outbox. Outbox Publisher надсилає її до RabbitMQ.

## 3. Вимоги

- Windows, Git Bash або термінал VS Code, Python із встановленими залежностями, Docker Desktop.
- Node.js та `npx` — для MCP Inspector.
- Ollama з моделлю `llama3.1:8b` — для Function Calling.
- Python-залежності: `requests`, `ollama`, сумісний з кодом **MCP SDK 1.x** (`mcp[cli]<2`), `a2a-sdk>=1,<2`, `httpx`, `uvicorn`, `starlette`. Для контейнера Producer залежності задаються у `Dockerfile.a2a`.

Приклад локального встановлення:

```bash
python -m pip install requests ollama "mcp[cli]<2" "a2a-sdk>=1,<2" httpx uvicorn starlette
ollama pull llama3.1:8b
```

## 4. Запуск мікросервісів

Запуск з кореня проєкту:

```bash
docker compose up -d --build
docker compose ps
curl -i http://localhost:8080/health
```

Типові локальні адреси:

| Компонент | Адреса |
|---|---|
| Nginx API Gateway | `http://localhost:8080` |
| REST API (через Gateway) | `http://localhost:8080/api` |
| RabbitMQ Management | `http://localhost:15672` |
| Producer Agent Card | `http://127.0.0.1:9001/.well-known/agent-card.json` |
| Consumer Agent Card | `http://127.0.0.1:9002/.well-known/agent-card.json` (після локального запуску Consumer) |


## 5. Завдання 1 — Function Calling

`ai_agent/agent.py` використовує `llama3.1:8b` для вибору інструментів. Для читання доступні `list_homeworks`, `get_homework`, `get_user`. API-клієнт звертається до `http://localhost:8080/api` (або значення змінної середовища `API_BASE_URL`).

Запуск:

```bash
python -m ai_agent.agent
```

**Приклад перевірочного запиту:**

> Знайди завдання з математики, отримай інформацію про його користувача через get_user та повідом точний статус завдання.

Під час перевірки зафіксовано послідовний виклик `list_homeworks` → `get_user` з реальним `user_id`, а також коректне відображення `cancelled` як «скасовано».

**Guardrails:** обмеження числа кроків, викликів інструментів і обліку токенів; перевірка UUID та переліку дозволених інструментів; лише читання через запропоновані LLM інструменти; виключення вільних описів завдань із контексту в цьому сценарії.

Окремий тест недовіреного вмісту без зміни реальних записів Redis:

```bash
python -m ai_agent.test_injection
```

Тест підтвердив, що інструкція `delete_all_homeworks` з підставленого опису не виконувалася, а статус `cancelled` був відображений правильно. Це тест конкретного сценарію, **не гарантія абсолютного захисту від prompt injection**. Ліміт токенів обчислюється за метриками, поверненими Ollama, і не є жорстким передбаченням витрат до кожного запиту.

## 6. Завдання 2 — MCP

MCP-сервер надає три інструменти для читання REST API. Використовується транспорт **stdio**.

```bash
python -m mcp_server.server
```

Для інтерактивної перевірки через MCP Inspector (потрібен Node.js):

```bash
npx @modelcontextprotocol/inspector python -m mcp_server.server
```

У браузері відкрийте адресу Inspector, надруковану в терміналі, з наданим токеном; не публікуйте токен. Виберіть **Tools → List Tools**, викличте `list_homeworks`, `get_user` або `get_homework`.

Перевірено успішне отримання списку, користувача та конкретного завдання. Також перевірено відхилення `not-a-valid-uuid` з повідомленням `Invalid UUID`. MCP-сервер обмежує список до 20 елементів та вилучає `description` із результатів. Сервер навчальний, без окремої авторизації клієнтів.

## 7. Завдання 3 — A2A

### Producer Agent

`a2a_agents/producer_agent.py` — A2A-сервер з Agent Card, skill `producer_messaging`, JSON-RPC endpoint та задачами (tasks). Producer запускається в Docker на порту `9001`.

```bash
docker compose up -d --build a2a_producer
curl -i http://127.0.0.1:9001/.well-known/agent-card.json
```

A2A-команда `Опублікуй тестову подію a2a.ping` створює запис `outbox:<event_id>` зі статусом `pending`. Наявний Outbox Publisher передає його до RabbitMQ і після підтвердження змінює статус на `published`.

### Consumer Agent

`a2a_agents/consumer_server.py` — **окремий A2A-сервер** з Agent Card і навичкою `request_producer_publication`. Він працює локально на порту `9002`, отримує A2A-запит і через A2A звертається до Producer. Це не той самий процес, що RabbitMQ Consumer із `services/consumer.py`.

Запуск у другому терміналі (Producer має працювати в Docker):

```bash
python -m a2a_agents.consumer_server
```

У третьому терміналі:

```bash
curl -i http://127.0.0.1:9002/.well-known/agent-card.json
python -m a2a_agents.test_consumer
```

Для окремої перевірки прямого клієнта Producer:

```bash
python -m a2a_agents.consumer_agent
```

### Перевірка публікації

Збережіть `Event ID`, який поверне A2A-тест, та виконайте:

```bash
docker compose logs --tail=30 outbox_publisher
docker compose exec redis redis-cli GET "outbox:EVENT_ID"
```

У перевіреному запуску журнал містив `OUTBOX PUBLISHED` для створеного Event ID, а запис Redis мав `"type": "a2a.ping"` та `"status": "published"`.


## 8. Результати

| Компонент | Що перевірено |
|---|---|
| Function Calling | Виклик REST-інструментів LLM, послідовність `list_homeworks` → `get_user`, точність статусу |
| AI guardrails | Блокування невідомого інструмента, перевірка UUID, тест недовіреного опису |
| MCP | Підключення Inspector, успішні виклики трьох tools, помилка `Invalid UUID` |
| A2A Producer | Agent Card, JSON-RPC, створення A2A task і запису в Redis Outbox |
| A2A Consumer | Власна Agent Card, звернення через A2A до Producer і повернення результату |
| Outbox / RabbitMQ | Відповідний `OUTBOX PUBLISHED` та запис Redis зі статусом `published` |


## Висновок

У лабораторній роботі №4 розширено систему мікросервісів з попередньої лабораторної засобами інтеграції з AI-агентами. Реалізовано Function Calling для локальної LLM, MCP-сервер для REST API та взаємодію двох A2A-агентів із використанням Redis Outbox і RabbitMQ. Перевірено основні запити, обмеження інструментів і публікацію тестових подій; окремо визначено межі продемонстрованої реалізації.
