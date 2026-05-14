import gzip

from flask import Response, request


COMPRESSIBLE_MIMETYPES = {
    "application/json",
    "application/javascript",
    "text/css",
    "text/html",
    "text/javascript",
    "text/plain",
}

MIN_COMPRESS_SIZE_BYTES = 512


def maybe_compress_response(response: Response) -> Response:
    """Gzip compress eligible responses when the client supports it."""

    if "gzip" not in request.headers.get("Accept-Encoding", "").lower():
        return response
    if response.status_code < 200 or response.status_code >= 300:
        return response
    if response.direct_passthrough:
        return response
    if response.headers.get("Content-Encoding"):
        return response
    if response.mimetype not in COMPRESSIBLE_MIMETYPES:
        return response

    payload = response.get_data()
    if len(payload) < MIN_COMPRESS_SIZE_BYTES:
        return response

    compressed = gzip.compress(payload)
    response.set_data(compressed)
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Length"] = str(len(compressed))
    response.headers["Vary"] = _append_vary(response.headers.get("Vary"), "Accept-Encoding")
    return response


def _append_vary(existing: str | None, value: str) -> str:
    if not existing:
        return value

    parts = [part.strip() for part in existing.split(",") if part.strip()]
    if value.lower() not in {part.lower() for part in parts}:
        parts.append(value)
    return ", ".join(parts)

