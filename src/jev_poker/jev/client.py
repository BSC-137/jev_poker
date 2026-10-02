"""HTTP client for the OpenRouter Decisions API.

Jev answers every question in one request in parallel. Questions do not
see each other, and the response is typed probabilities, not text.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
MODEL_ID = "typesafe/jev-1.13"
TIMEOUT_SECONDS = 20
_MAX_RETRIES = 2
_RETRY_BACKOFF_SECONDS = (0.5, 1.0)


class JevError(Exception):
    """Base error for the Jev client."""


class JevResponseError(JevError):
    """``answers.action`` is missing or malformed, or ``usage.cost`` is unusable."""


class JevTransportError(JevError):
    """The decisions endpoint failed after the allowed retries."""

    def __init__(self, status: int, detail: str = "") -> None:
        self.status = status
        message = f"decisions request failed with HTTP {status}"
        if detail:
            message = f"{message}: {detail}"
        super().__init__(message)


@dataclass(frozen=True)
class JevResult:
    """Parsed decisions payload the agent can branch on."""

    answers: dict
    cost: float


class JevClient:
    """POST a decisions request and return parsed answers plus ``usage.cost``."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        url: str = DECISIONS_URL,
        timeout: float = TIMEOUT_SECONDS,
        opener: Callable | None = None,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise JevError("OPENROUTER_API_KEY is not set")
        self._api_key = key
        self._url = url
        self._timeout = timeout
        self._opener = opener
        self._sleep = time.sleep if sleep is None else sleep

    def submit(self, state: dict, questions: dict) -> JevResult:
        body = {"model": MODEL_ID, "state": state, "questions": questions}
        status, raw = self._send_with_retries(body)
        if status < 200 or status >= 300:
            raise JevTransportError(status, _snippet(raw))
        return _parse_result(raw)

    def _send_with_retries(self, body: dict) -> tuple[int, bytes]:
        attempt = 0
        while True:
            status, raw = self._exchange(body)
            retryable = status == 429 or 500 <= status <= 599
            if 200 <= status < 300 or not retryable or attempt >= _MAX_RETRIES:
                return status, raw
            self._sleep(_RETRY_BACKOFF_SECONDS[attempt])
            attempt += 1

    def _exchange(self, body: dict) -> tuple[int, bytes]:
        request = urllib.request.Request(
            self._url,
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
        )
        opener = self._opener or urllib.request.urlopen
        try:
            with opener(request, timeout=self._timeout) as response:
                status = response.getcode() if hasattr(response, "getcode") else response.status
                return status, response.read()
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read()
        except urllib.error.URLError as exc:
            raise JevTransportError(0, str(exc.reason)) from exc


def _parse_result(raw: bytes) -> JevResult:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise JevResponseError("decisions response is not JSON") from exc
    if not isinstance(payload, dict):
        raise JevResponseError("missing answers.action")
    answers = payload.get("answers")
    if not isinstance(answers, dict) or "action" not in answers:
        raise JevResponseError("missing answers.action")
    _require_action(answers["action"])
    usage = payload.get("usage")
    if not isinstance(usage, dict) or "cost" not in usage:
        raise JevResponseError("missing usage.cost")
    cost = usage["cost"]
    if not _real_number(cost):
        raise JevResponseError("missing usage.cost")
    return JevResult(answers=answers, cost=float(cost))


def _require_action(action: object) -> None:
    if not isinstance(action, dict):
        raise JevResponseError("malformed answers.action")
    choice = action.get("choice")
    confidence = action.get("confidence")
    if action.get("type") != "choice":
        raise JevResponseError("malformed answers.action")
    if not isinstance(choice, str) or not choice:
        raise JevResponseError("malformed answers.action")
    if not _real_number(confidence) or not 0 <= float(confidence) <= 1:
        raise JevResponseError("malformed answers.action")


def _real_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _snippet(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace").strip()
    if len(text) > 300:
        return text[:300]
    return text
