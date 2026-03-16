from typing import Any

from flask import request


def get_json_object() -> dict[str, Any] | None:
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if isinstance(data, dict):
        return data
    return None
