# API Response Compression & Payload Optimization

## Overview

Comprehensive API response compression and payload optimization system for FinMind. Reduces bandwidth usage and improves response times through gzip compression, field selection, pagination, and smart payload stripping.

## Features

### Gzip Compression
- Automatic gzip compression for responses exceeding configurable threshold (default 500 bytes)
- Content-type aware — excludes images, audio, video, and already-compressed formats
- Configurable compression level (1-9)
- Only applies when client sends `Accept-Encoding: gzip`
- Transparent — no client-side changes needed

### ETag Support
- Automatic ETag generation for GET responses
- Conditional request handling with `If-None-Match`
- Returns 304 Not Modified when content unchanged
- Reduces bandwidth for repeat requests

### Payload Optimization
- **Field selection**: Return only requested fields from JSON responses
- **Null stripping**: Remove null values to reduce payload size
- **Empty stripping**: Optionally remove empty arrays, objects, and strings
- **Nested optimization**: Recursively processes nested objects

### Pagination
- Standard pagination with page/page_size parameters
- Response includes full metadata (total_items, total_pages, has_next, has_prev)
- Configurable max page size (default 100)

### Statistics
- Real-time compression statistics
- Per-endpoint breakdown
- Compression ratio tracking
- Bytes saved counter
- ETag hit counter

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/compression/stats` | Get compression statistics |
| POST | `/compression/stats/reset` | Reset statistics |
| GET | `/compression/config` | Get compression configuration |
| POST | `/compression/optimize` | Try payload optimization |
| POST | `/compression/paginate` | Try pagination |

## Middleware Integration

The compression middleware is automatically applied to all responses via Flask's `after_request` hook. No per-route configuration needed.

## Configuration

```python
DEFAULT_CONFIG = {
    "min_size": 500,            # Minimum bytes to trigger compression
    "compression_level": 6,     # gzip level (1=fast, 9=best)
    "enable_etag": True,        # Enable ETag headers
    "enable_stats": True,       # Track compression stats
    "max_page_size": 100,       # Max items per page
    "default_page_size": 20,    # Default items per page
}
```

## Testing

```bash
cd packages/backend
.venv/bin/python -m pytest tests/test_compression.py -v
```
