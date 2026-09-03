import pytest
import requests

from library.http_utils import get_with_retry


class FakeResponse:
    def __init__(self, status_code, headers=None):
        self.status_code = status_code
        self.headers = headers or {}


def test_returns_immediately_on_success(monkeypatch):
    calls = []
    monkeypatch.setattr(
        "library.http_utils.requests.get",
        lambda *a, **k: (calls.append(1), FakeResponse(200))[1],
    )
    resp = get_with_retry("https://example.com")
    assert resp.status_code == 200
    assert len(calls) == 1


def test_retries_on_429_then_succeeds(monkeypatch):
    responses = [FakeResponse(429, {"Retry-After": "0"}), FakeResponse(200)]
    monkeypatch.setattr("library.http_utils.requests.get", lambda *a, **k: responses.pop(0))
    monkeypatch.setattr("library.http_utils.time.sleep", lambda s: None)

    resp = get_with_retry("https://example.com")

    assert resp.status_code == 200


def test_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr("library.http_utils.requests.get", lambda *a, **k: FakeResponse(429))
    monkeypatch.setattr("library.http_utils.time.sleep", lambda s: None)

    resp = get_with_retry("https://example.com")

    assert resp.status_code == 429


def test_retries_connection_error_then_succeeds(monkeypatch):
    calls = []

    def fake_get(*a, **k):
        calls.append(1)
        if len(calls) < 2:
            raise requests.exceptions.ConnectTimeout("handshake timed out")
        return FakeResponse(200)

    monkeypatch.setattr("library.http_utils.requests.get", fake_get)
    monkeypatch.setattr("library.http_utils.time.sleep", lambda s: None)

    resp = get_with_retry("https://example.com")

    assert resp.status_code == 200
    assert len(calls) == 2


def test_raises_after_exhausting_connection_retries(monkeypatch):
    monkeypatch.setattr(
        "library.http_utils.requests.get",
        lambda *a, **k: (_ for _ in ()).throw(requests.exceptions.ConnectTimeout("still down")),
    )
    monkeypatch.setattr("library.http_utils.time.sleep", lambda s: None)

    with pytest.raises(requests.exceptions.ConnectTimeout):
        get_with_retry("https://example.com")
