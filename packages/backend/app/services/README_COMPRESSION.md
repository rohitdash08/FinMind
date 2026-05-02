# API Response Compression

## Overview

FinMind uses Flask-Compress to automatically compress HTTP responses, reducing bandwidth usage and improving response times for clients.

## Configuration

Compression is configured in `app/__init__.py`:

```python
app.config["COMPRESS_MIMETYPES"] = [
    "application/json",
    "text/html",
    "text/css",
    "text/xml",
    "application/javascript",
]
app.config["COMPRESS_MIN_SIZE"] = 500  # Only compress responses > 500 bytes
```

### Settings

| Setting | Value | Description |
|---------|-------|-------------|
| `COMPRESS_MIMETYPES` | See above | MIME types eligible for compression |
| `COMPRESS_MIN_SIZE` | 500 | Minimum response size in bytes to compress |

## How It Works

1. Client sends request with `Accept-Encoding: gzip` (or `deflate`, `br`)
2. Flask-Compress checks if the response MIME type is in `COMPRESS_MIMETYPES`
3. If response size exceeds `COMPRESS_MIN_SIZE`, it's compressed
4. Response includes `Content-Encoding` header indicating compression method

## Supported Compression Methods

- **gzip** - Most widely supported
- **deflate** - Legacy support
- **brotli** - Best compression ratio (requires `brotli` package)

## Response Size Monitoring

Response sizes are tracked via Prometheus metrics:

```
finmind_http_response_size_bytes_bucket
finmind_http_response_size_bytes_count
finmind_http_response_size_bytes_sum
```

### Metric Labels

- `method` - HTTP method (GET, POST, etc.)
- `endpoint` - URL pattern (e.g., `/expenses`, `/health`)

### Viewing Metrics

```bash
# View all response size metrics
curl http://localhost:5000/metrics | grep response_size

# View specific endpoint
curl http://localhost:5000/metrics | grep 'endpoint="/expenses"'
```

## Pagination

List endpoints support consistent pagination via `paginate_query()`:

### Query Parameters

| Parameter | Default | Max | Description |
|-----------|---------|-----|-------------|
| `page` | 1 | - | Page number (1-indexed) |
| `page_size` | 50 | 200 | Items per page |

### Response Format

```json
{
    "items": [...],
    "total": 150,
    "page": 1,
    "page_size": 50
}
```

### Example Usage

```python
from ..utils.pagination import paginate_query

@bp.get("")
@jwt_required()
def list_items():
    q = db.session.query(Item).filter_by(user_id=uid)
    q = q.order_by(Item.created_at.desc())
    
    items, total, page, page_size = paginate_query(q)
    if items is None:
        return jsonify(error=total), 400
    
    return jsonify({
        "items": [item.to_dict() for item in items],
        "total": total,
        "page": page,
        "page_size": page_size,
    })
```

### Client Examples

```bash
# First page, 20 items per page
GET /expenses?page=1&page_size=20

# Third page
GET /expenses?page=3

# Default pagination (page=1, page_size=50)
GET /expenses
```

## Performance Impact

- **Compression CPU overhead**: Minimal for JSON responses
- **Bandwidth savings**: Typically 60-80% for JSON payloads
- **Latency improvement**: Significant for slow connections

## Production Notes

- Gunicorn workers handle compression independently
- No additional configuration needed for reverse proxies (nginx, etc.)
- Monitor `finmind_http_response_size_bytes` for optimization opportunities

## Dependencies

```
flask-compress==1.14
```

For Brotli support (optional):
```
brotli==1.1.0
```
