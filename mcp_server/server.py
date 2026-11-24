
from uuid import UUID
from mcp.server.fastmcp import FastMCP

from ai_agent.tools import (
    list_homeworks as api_list_homeworks,
    get_homework as api_get_homework,
    get_user as api_get_user,
)

mcp = FastMCP("SOA Homework MCP Server")

MAX_ITEMS = 20


def validate_uuid(value: str) -> str:
    """Перевірка UUID перед зверненням до REST API."""
    if not isinstance(value, str) or len(value) > 36:
        raise ValueError("Invalid UUID")

    try:
        return str(UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Invalid UUID") from None


@mcp.tool()
def list_homeworks() -> dict:
    """Отримати список домашніх завдань."""
    result = api_list_homeworks()

    if not isinstance(result, dict):
        return {"error": "Invalid API response"}

    if "error" in result:
        return result

    items = result.get("items", [])

    if not isinstance(items, list):
        return {"error": "Invalid homework list"}

    safe_items = []

    for item in items[:MAX_ITEMS]:
        if not isinstance(item, dict):
            continue

        safe_items.append({
            "id": item.get("id"),
            "user_id": item.get("user_id"),
            "subject": item.get("subject"),
            "status": item.get("status"),
            "deadline": item.get("deadline")
        })

    return {
        "items": safe_items,
        "total": len(items),
        "truncated": len(items) > MAX_ITEMS
    }


@mcp.tool()
def get_homework(task_id: str) -> dict:
    """Отримати домашнє завдання за UUID."""
    task_id = validate_uuid(task_id)
    result = api_get_homework(task_id)

    if isinstance(result, dict) and "error" not in result:
        return {
            "id": result.get("id"),
            "user_id": result.get("user_id"),
            "subject": result.get("subject"),
            "status": result.get("status"),
            "deadline": result.get("deadline")
        }

    return result


@mcp.tool()
def get_user(user_id: str) -> dict:
    """Отримати користувача за UUID."""
    user_id = validate_uuid(user_id)
    result = api_get_user(user_id)

    if isinstance(result, dict) and "error" not in result:
        return {
            "id": result.get("id"),
            "name": result.get("name"),
            "email": result.get("email")
        }

    return result


if __name__ == "__main__":
    mcp.run(transport="stdio")
