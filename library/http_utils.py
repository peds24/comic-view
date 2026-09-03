"""Shared HTTP helper for metadata source clients:
- retries a 429 response using the server's Retry-After header (falling
  back to simple backoff if that header is missing), instead of treating a
  rate limit as "no result"
- retries a connection-level failure (timeout, DNS blip, TLS handshake
  timeout) a few times too — confirmed happening against the real Metron
  API mid-batch-import, and left unhandled this silently produced records
  with zero enrichment that were fully findable on a retry, indistinguishable
  from a genuine "not in the database" result.
"""
from __future__ import annotations

import time

import requests

_MAX_RETRIES = 5
_DEFAULT_BACKOFF = 5.0
_CONNECTION_RETRIES = 3
_CONNECTION_BACKOFF = 3.0


def get_with_retry(url: str, **kwargs) -> requests.Response:
    last_error: requests.RequestException | None = None
    for conn_attempt in range(_CONNECTION_RETRIES):
        try:
            return _get_with_rate_limit_retry(url, **kwargs)
        except requests.RequestException as e:
            last_error = e
            if conn_attempt < _CONNECTION_RETRIES - 1:
                time.sleep(_CONNECTION_BACKOFF * (conn_attempt + 1))
    raise last_error


def _get_with_rate_limit_retry(url: str, **kwargs) -> requests.Response:
    for attempt in range(_MAX_RETRIES):
        resp = requests.get(url, **kwargs)
        if resp.status_code != 429:
            return resp
        retry_after = resp.headers.get("Retry-After")
        delay = float(retry_after) if retry_after else _DEFAULT_BACKOFF * (attempt + 1)
        time.sleep(delay)
    return resp
