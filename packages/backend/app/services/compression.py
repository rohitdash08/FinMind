import gzip
import io
import logging
from flask import Flask, request, Response, current_app

logger = logging.getLogger("finmind.compression")

MIN_COMPRESSION_SIZE = 512


def _brotli_compress(data: bytes, quality: int = 4) -> bytes | None:
    try:
        import brotli
        return brotli.compress(data, quality=quality)
    except ImportError:
        return None


def _compress_response(response: Response) -> Response:
    if response.status_code >= 300 and response.status_code != 304:
        return response
    if response.content_length is not None and response.content_length < MIN_COMPRESSION_SIZE:
        return response
    if response.mimetype not in ("application/json", "text/plain", "text/html", "text/css", "application/javascript"):
        return response
    content = response.get_data()
    if not content or len(content) < MIN_COMPRESSION_SIZE:
        return response
    accept_encoding = request.headers.get("Accept-Encoding", "")
    if "br" in accept_encoding:
        compressed = _brotli_compress(content)
        if compressed and len(compressed) < len(content):
            response.set_data(compressed)
            response.headers["Content-Encoding"] = "br"
            response.headers["Content-Length"] = str(len(compressed))
            logger.debug("Compressed %s with brotli: %d -> %d bytes", request.path, len(content), len(compressed))
            return response
    if "gzip" in accept_encoding:
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", compresslevel=6) as f:
            f.write(content)
        compressed = buf.getvalue()
        if len(compressed) < len(content):
            response.set_data(compressed)
            response.headers["Content-Encoding"] = "gzip"
            response.headers["Content-Length"] = str(len(compressed))
            logger.debug("Compressed %s with gzip: %d -> %d bytes", request.path, len(content), len(compressed))
            return response
    return response


def init_compression(app: Flask) -> None:
    app.after_request(_compress_response)
    logger.info("Response compression initialized (gzip + brotli)")
