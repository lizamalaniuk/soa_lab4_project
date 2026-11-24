
from uuid import UUID
from .api_client import APIClient

api = APIClient()


def valid_uuid(value):
    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Invalid UUID")


def list_homeworks():
    """Отримати всі домашні завдання."""
    return api.request("GET", "/homeworks")


def get_homework(task_id: str):
    """Отримати домашнє завдання за ID."""
    return api.request(
        "GET",
        f"/homeworks/{valid_uuid(task_id)}"
    )


def get_user(user_id: str):
    """Отримати користувача за ID."""
    return api.request(
        "GET",
        f"/users/{valid_uuid(user_id)}"
    )


def create_user(name: str, email: str):
    """Створити нового користувача."""
    if not name.strip() or not email.strip():
        return {"error": "Name and email are required"}

    return api.request(
        "POST",
        "/users",
        data={"name": name, "email": email}
    )


def create_homework(
    user_id: str,
    subject: str,
    description: str,
    deadline: str
):
    """Створити домашнє завдання."""
    return api.request(
        "POST",
        "/homeworks",
        data={
            "user_id": valid_uuid(user_id),
            "subject": subject,
            "description": description,
            "deadline": deadline
        }
    )


def complete_homework(task_id: str):
    """Позначити домашнє завдання виконаним."""
    return api.request(
        "PATCH",
        f"/homeworks/{valid_uuid(task_id)}/complete"
    )


TOOLS = {
    "list_homeworks": list_homeworks,
    "get_homework": get_homework,
    "get_user": get_user,
    "create_user": create_user,
    "create_homework": create_homework,
    "complete_homework": complete_homework
}
