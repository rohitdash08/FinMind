import json
from typing import Any


def strip_nulls(data: Any) -> Any:
    if isinstance(data, dict):
        return {k: strip_nulls(v) for k, v in data.items() if v is not None}
    if isinstance(data, list):
        return [strip_nulls(v) for v in data]
    return data


def sparse_fieldsets(data: Any, fields: set[str] | None) -> Any:
    if not fields:
        return data
    if isinstance(data, dict):
        return {k: v for k, v in data.items() if k in fields}
    if isinstance(data, list):
        return [sparse_fieldsets(v, fields) for v in data]
    return data


def paginated_response(items: list[dict], total: int, page: int, page_size: int) -> dict:
    total_pages = max(1, (total + page_size - 1) // page_size)
    return {
        "data": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    }


class CompactJSONEncoder(json.JSONEncoder):
    def default(self, obj: Any) -> Any:
        return super().default(obj)

    def encode(self, o: Any) -> str:
        o = strip_nulls(o)
        return super().encode(o)

    def iterencode(self, o: Any, _one_shot: bool = False) -> Any:
        o = strip_nulls(o)
        return super().iterencode(o, _one_shot)
