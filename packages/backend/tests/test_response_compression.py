"""Tests for API response compression & payload optimization."""
import pytest
import gzip
import json
from unittest.mock import patch, MagicMock

from app.services.response_compression import (
    _gzip_compress,
    _deflate_compress,
    compress_response_data,
    strip_null_fields,
    filter_fields,
    optimize_payload,
    measure_compression,
    COMPRESS_THRESHOLD_BYTES,
)


# ── Compression helpers ───────────────────────────────────────────────

def test_gzip_compress_decompresses_correctly():
    data = b"Hello, World! " * 100
    compressed = _gzip_compress(data)
    assert gzip.decompress(compressed) == data


def test_gzip_reduces_size():
    data = b"aaaa" * 1000
    compressed = _gzip_compress(data)
    assert len(compressed) < len(data)


def test_deflate_compress_reduces_size():
    import zlib
    data = b"bbbb" * 1000
    compressed = _deflate_compress(data)
    assert len(compressed) < len(data)
    assert zlib.decompress(compressed) == data


def test_compress_response_data_below_threshold():
    data = b"small"  # Below threshold
    result, encoding = compress_response_data(data, "application/json")
    assert result == data
    assert encoding == ""


def test_compress_response_data_non_compressible():
    data = b"binary data " * 200
    result, encoding = compress_response_data(data, "image/png")
    assert result == data
    assert encoding == ""


# ── Payload optimization ──────────────────────────────────────────────

def test_strip_null_fields_simple():
    data = {"a": 1, "b": None, "c": "hello"}
    result = strip_null_fields(data)
    assert result == {"a": 1, "c": "hello"}


def test_strip_null_fields_nested():
    data = {"user": {"name": "Alice", "age": None}, "score": None}
    result = strip_null_fields(data)
    assert result == {"user": {"name": "Alice"}}


def test_strip_null_fields_list():
    data = [{"a": 1, "b": None}, {"a": 2, "b": 3}]
    result = strip_null_fields(data)
    assert result == [{"a": 1}, {"a": 2, "b": 3}]


def test_filter_fields_basic():
    data = {"id": 1, "name": "Alice", "email": "alice@example.com"}
    result = filter_fields(data, ["id", "name"])
    assert result == {"id": 1, "name": "Alice"}
    assert "email" not in result


def test_filter_fields_list():
    data = [{"id": 1, "amount": 50.0, "notes": "x"}, {"id": 2, "amount": 100.0, "notes": "y"}]
    result = filter_fields(data, ["id", "amount"])
    assert result == [{"id": 1, "amount": 50.0}, {"id": 2, "amount": 100.0}]


def test_optimize_payload_combined():
    data = {"id": 1, "name": "Test", "notes": None, "amount": 50.0}
    optimized = optimize_payload(data, fields=["id", "amount"], strip_nulls=True)
    assert optimized == {"id": 1, "amount": 50.0}


def test_measure_compression_sizes():
    data = json.dumps({"key": "value " * 200}).encode("utf-8")
    stats = measure_compression(data)
    assert stats["original_bytes"] == len(data)
    assert stats["gzip_bytes"] < stats["original_bytes"]
    assert stats["gzip_savings_pct"] > 0


def test_measure_compression_tiny_data():
    data = b"hi"
    stats = measure_compression(data)
    assert stats["original_bytes"] == 2
    # gzip may be larger than original for tiny data
    assert "gzip_ratio" in stats