import pytest

from shazamlite.errors import FailedDecodeJson, HTTPStatusError, MaxRetriesExceeded
from shazamlite.http import HTTPClient, Response


def test_json_ok():
    response = Response(200, b'{"hello": "world"}', "http://example.test")
    assert response.json() == {"hello": "world"}


def test_failed_decode_json_carries_status_body_url():
    response = Response(502, b"<html>gateway</html>", "http://example.test")
    with pytest.raises(FailedDecodeJson) as exc_info:
        response.json()
    error = exc_info.value
    assert error.status_code == 502
    assert error.body == "<html>gateway</html>"
    assert error.url == "http://example.test"
    assert "502" in str(error)


def test_csv_parsing():
    response = Response(200, b"Rank,Artist,Title\n1,Alpha,Beta\n2,Gamma,Delta\n", "u")
    rows = response.csv()
    assert rows[0] == ["Rank", "Artist", "Title"]
    assert rows[1] == ["1", "Alpha", "Beta"]
    assert rows[2] == ["2", "Gamma", "Delta"]


def test_csv_blank_lines_filtered():
    response = Response(200, b"Rank,Artist,Title\n\n1,Alpha,Beta\n", "u")
    rows = response.csv()
    assert len(rows) == 2


def test_retry_on_retryable_status():
    calls = {"count": 0}

    class FakeClient(HTTPClient):
        def _request_once(self, method, url, headers, data, json_body, timeout):
            calls["count"] += 1
            if calls["count"] < 3:
                return Response(503, b"unavailable", url)
            return Response(200, b'{"ok": true}', url)

    client = FakeClient(use_curl_cffi=False, retries=3)
    result = client.request("GET", "http://example.test")
    assert result == {"ok": True}
    assert calls["count"] == 3


def test_exhausted_retryable_status_raises_http_status_error():
    calls = {"count": 0}

    class AlwaysFail(HTTPClient):
        def _request_once(self, method, url, headers, data, json_body, timeout):
            calls["count"] += 1
            return Response(500, b"boom", url)

    client = AlwaysFail(use_curl_cffi=False, retries=2)
    with pytest.raises(HTTPStatusError) as exc_info:
        client.request("GET", "http://example.test")
    assert exc_info.value.status_code == 500
    assert exc_info.value.body == "boom"
    assert calls["count"] == 2


def test_transport_error_raises_max_retries_exceeded():
    import urllib.error

    calls = {"count": 0}

    class AlwaysDrops(HTTPClient):
        def _request_once(self, method, url, headers, data, json_body, timeout):
            calls["count"] += 1
            raise urllib.error.URLError("connection reset")

    client = AlwaysDrops(use_curl_cffi=False, retries=3)
    with pytest.raises(MaxRetriesExceeded):
        client.request("GET", "http://example.test")
    assert calls["count"] == 3


def test_non_retryable_status_raises_http_status_error():
    class NotFound(HTTPClient):
        def _request_once(self, method, url, headers, data, json_body, timeout):
            return Response(404, b"nope", url)

    client = NotFound(use_curl_cffi=False, retries=1)
    with pytest.raises(HTTPStatusError) as exc_info:
        client.request("GET", "http://example.test")
    assert exc_info.value.status_code == 404
