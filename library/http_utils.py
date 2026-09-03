"""Shared HTTP helper for metadata source clients: retries a 429 response
using the server's Retry-After header (falling back to simple backoff if
that header is missing), instead of treating a rate limit as "no result".
"""
from __future__ import annotations

import time

import requests

_MAX_RETRIES = 5
_DEFAULT_BACKOFF = 5.0


def get_with_retry(url: str, **kwargs) -> requests.Response:
    for attempt in range(_MAX_RETRIES):
        resp = requests.get(url, **kwargs)
        if resp.status_code != 429:
            return resp
        retry_after = resp.headers.get("Retry-After")
        delay = float(retry_after) if retry_after else _DEFAULT_BACKOFF * (attempt + 1)
        time.sleep(delay)
    return resp
