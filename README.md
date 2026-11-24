# ЛР3 SOA — варіант 11

**Тема:** Забезпечення транзакційності у взаємодії інтелектуальних сервісів.

**Мета:** Реалізувати патерни Transactional Outbox, Transactional Inbox та SAGA для забезпечення надійної взаємодії мікросервісів, обробки помилок і компенсації розподілених транзакцій.

## 1. Архітектура системи

Проєкт продовжує лабораторну роботу №2 — систему управління домашніми завданнями.

**Основні компоненти:**

- **Users Service** — створення та отримання даних користувачів.
- **Homework Service** — управління домашніми завданнями та їхніми статусами.
- **Notifications Service** — перегляд сформованих сповіщень.
- **Consumer** — обробка повідомлень із RabbitMQ.
- **Outbox Publisher** — передавання збережених подій із Redis до RabbitMQ.
- **SAGA Coordinator** — виконання компенсаційних операцій після помилок.
- **SAGA Timeout Monitor** — автоматичне скасування незавершених транзакцій після таймауту.
- **RabbitMQ** — брокер повідомлень із підтримкою Dead Letter Queue.
- **Redis** — зберігання даних, повідомлень Outbox та ідентифікаторів Inbox.
- **Nginx API Gateway** — єдина точка доступу до HTTP API.

Для запуску використовується Docker Compose.

## 2. Реалізовані патерни

### Transactional Outbox

Під час створення домашнього завдання Homework Service атомарно зберігає в Redis два записи:

1. Дані домашнього завдання.
2. Повідомлення в Outbox зі статусом `pending`.

Окремий Outbox Publisher отримує це повідомлення, публікує його в RabbitMQ та після підтвердження брокера змінює статус події на `published`.

### Transactional Inbox

Consumer зберігає ідентифікатор успішно обробленого повідомлення в Redis за ключем `inbox:<event_id>`.

Якщо повідомлення з таким ідентифікатором надходить повторно, Consumer розпізнає дублікат і не створює повторне сповіщення.

### SAGA

SAGA забезпечує узгодження стану домашнього завдання з результатом асинхронної обробки.

Передбачено два основні сценарії:

- **Успішне виконання:** `pending → confirmed`.
- **Помилка обробки:** `pending → cancelled`.

Компенсація може запускатися після отримання повідомлення з DLQ або після перевищення встановленого таймауту.

Компенсаційна операція є ідемпотентною: повторне скасування завдання зі статусом `cancelled` не змінює його стан.

## 3. Запуск системи

Для запуску всіх компонентів:

```bash
docker compose up --build -d
```

Перевірка контейнерів:

```bash
docker compose ps
```

Перевірка API Gateway:

```bash
curl -i http://localhost:8080/health
```

Очікувана відповідь:

```text
HTTP/1.1 200 OK

API Gateway OK
```

Інтерфейс RabbitMQ:

http://localhost:15672

Для стандартної локальної конфігурації:

- Login: `guest`
- Password: `guest`

## 4. Перевірка успішного сценарію SAGA

### 4.1. Створення користувача

```bash
curl -s -X POST http://localhost:8080/api/users \
-H "Content-Type: application/json" \
-d '{"name":"Saga Test","email":"saga@example.com"}'
```

Скопіювати `id` користувача з відповіді.

### 4.2. Створення домашнього завдання

Замінити `USER_ID` отриманим ідентифікатором.

```bash
curl -i -X POST http://localhost:8080/api/homeworks \
-H "Content-Type: application/json" \
-d '{"user_id":"USER_ID","subject":"Chemistry","description":"SAGA success test","deadline":"2026-12-01"}'
```

Очікується статус `201 Created`.

Початковий стан завдання:

```json
{
  "status": "pending",
  "event_queued": true,
  "event_published": false
}
```

Публікація події здійснюється асинхронно.

### 4.3. Перевірка Outbox Publisher

```bash
docker compose logs outbox_publisher --tail=20
```

Очікуваний запис:

```text
OUTBOX PUBLISHED: <event_id>
```

### 4.4. Перевірка Consumer

Для успішного сценарію в `docker-compose.yml` необхідно встановити:

```yaml
environment:
  SIMULATE_FAILURE: "false"
```

Після застосування конфігурації Consumer успішно обробляє повідомлення.

```bash
docker compose logs consumer --tail=20
```

Очікуваний запис:

```text
SAGA CONFIRMED: <task_id>
```

### 4.5. Перевірка статусу завдання

```bash
curl -s http://localhost:8080/api/homeworks/TASK_ID
```

Очікуваний результат:

```json
{
  "status": "confirmed"
}
```

## 5. Перевірка SAGA з помилкою Consumer

Для демонстрації помилки змінити налаштування Consumer у `docker-compose.yml`:

```yaml
environment:
  SIMULATE_FAILURE: "true"
```

Перезапустити Consumer:

```bash
docker compose up -d --build consumer
```

Створити нове домашнє завдання через `POST /api/homeworks`.

Перевірити журнали:

```bash
docker compose logs consumer --tail=20
```

Очікуваний результат:

```text
CONSUMER FAILED: Simulated consumer failure for SAGA
```

Consumer відхиляє повідомлення через `basic_nack(requeue=False)`, після чого RabbitMQ перенаправляє його до Dead Letter Queue.

Перевірити черги:

```bash
docker compose exec rabbitmq rabbitmqctl list_queues name messages consumers
```

Використовуються:

- `notification.events` — основна черга.
- `homework.dlq` — черга помилкових повідомлень.

SAGA Coordinator отримує повідомлення з DLQ та запускає компенсацію.

```bash
docker compose logs saga_coordinator --tail=20
```

Очікуваний запис:

```text
SAGA COMPENSATED: <task_id>
```

Після компенсації статус завдання:

```json
{
  "status": "cancelled"
}
```

Після завершення перевірки повернути `SIMULATE_FAILURE: "false"` та перезапустити Consumer.

## 6. Компенсація за таймаутом

Додатково реалізовано SAGA Timeout Monitor.

Для навчального експерименту встановлено:

```python
SAGA_TIMEOUT = 30
```

Якщо завдання залишається у статусі `pending` понад 30 секунд, Timeout Monitor запускає компенсаційну операцію.

Перевірка:

```bash
docker compose logs saga_timeout --tail=20
```

Очікуваний результат:

```text
SAGA TIMEOUT: <task_id>
SAGA COMPENSATED: <task_id>
```

Після цього статус завдання змінюється на `cancelled`.

## 7. Перевірка ідемпотентності

Для запобігання повторній обробці Consumer використовує Inbox із ключами `inbox:<event_id>`.

Повторна обробка вже підтвердженої події призводить до повідомлення:

```text
DUPLICATE EVENT: <event_id>
```

Повторна компенсація вже скасованого завдання призводить до:

```text
SAGA: Already cancelled <task_id>
```

Це демонструє захист від дублювання операцій.

## 8. Результати експериментів

Під час виконання лабораторної перевірено три основні сценарії.

| Сценарій | Результат |
|---|---|
| Успішна обробка повідомлення | `confirmed` |
| Помилка Consumer та компенсація через DLQ | `cancelled` |
| Перевищення таймауту SAGA | `cancelled` |

Додатково перевірено атомарний запис даних і повідомлення в Outbox, підтвердження публікації RabbitMQ та захист від повторної обробки подій.

## 9. Обмеження реалізації

Проєкт є навчальним прототипом.

Мікросервіси використовують спільне сховище Redis. Для промислової системи доцільно розділити бази даних сервісів та реалізувати обмін результатами локальних транзакцій через окремі події.

Також необхідно враховувати можливість повторної доставки повідомлень і конфлікти між таймаутом та успішним завершенням операції.

## 10. Завершення роботи

Зупинити всі контейнери:

```bash
docker compose down
```

Команда зупиняє та видаляє контейнери й мережі, створені Docker Compose.

**Не використовувати `docker compose down -v` без необхідності**, оскільки це додатково видаляє керовані Docker томи.

## Висновок

У лабораторній роботі №3 реалізовано механізми забезпечення транзакційності в мікросервісній системі на основі патернів Transactional Outbox, Transactional Inbox та SAGA.

Продемонстровано надійніше передавання подій через RabbitMQ, обробку помилок із використанням DLQ, компенсацію невдалих транзакцій та автоматичний відкат за таймаутом.

Проведені експерименти підтвердили роботу основних сценаріїв розподіленої транзакції та ідемпотентної обробки повідомлень.