# API Compression & Payload Optimization

## Overview

FinMind implements several optimizations to reduce API payload size and improve response times:

1. **Response Compression** — gzip and Brotli compression middleware
2. **Null Field Stripping** — `null` values are excluded from JSON responses
3. **Pagination Metadata** — all list endpoints return structured pagination info

## Response Compression

The compression middleware automatically compresses JSON responses based on the client's `Accept-Encoding` header. Brotli is preferred over gzip when both are supported.

### Headers

| Request Header | Effect |
|---------------|--------|
| `Accept-Encoding: br` | Brotli compression |
| `Accept-Encoding: gzip` | Gzip compression |
| (none) | No compression |

Responses smaller than 512 bytes are not compressed.

## Null Field Stripping

`null` values are automatically removed from JSON responses to reduce payload size. The custom `CompactJSONEncoder` strips all `null` fields recursively before serialization.

### Example

```json
// Before stripping nulls
{"id": 1, "name": "Test", "category_id": null, "notes": null}

// After stripping nulls
{"id": 1, "name": "Test"}
```

## Pagination Metadata

List endpoints return a standardized pagination envelope with metadata.

### Response Format

```json
{
  "data": [...],
  "pagination": {
    "page": 1,
    "page_size": 10,
    "total": 42,
    "total_pages": 5,
    "has_next": true,
    "has_prev": false
  }
}
```

### Query Parameters

| Parameter | Default | Max | Description |
|-----------|---------|-----|-------------|
| `page` | 1 | — | Page number (1-indexed) |
| `page_size` | 200 | 200 | Items per page |

### Endpoints with Pagination

- `GET /expenses` — expense list with filters
