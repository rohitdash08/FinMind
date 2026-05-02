from flask import request


def paginate_query(query, default_page_size=50, max_page_size=200):
    """Apply pagination to a SQLAlchemy query.

    Returns:
        tuple: (items, total, page, page_size) on success,
               (None, None, None, error_message) on invalid input.
    """
    try:
        page = max(1, int(request.args.get("page", "1")))
        page_size = min(
            max_page_size,
            max(1, int(request.args.get("page_size", str(default_page_size)))),
        )
    except ValueError:
        return None, None, None, "invalid pagination"

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()

    return items, total, page, page_size
