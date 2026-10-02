"""Decisions client tests. HTTP is mocked; nothing is sent to OpenRouter."""

import io
import json
import urllib.error
import urllib.request
from email.message import Message

import pytest

from jev_poker.jev.client import (
    DECISIONS_URL,
    MODEL_ID,
    JevClient,
    JevError,
    JevResponseError,
    JevTransportError,
)


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("network access is not allowed")

    monkeypatch.setattr(urllib.request, "urlopen", explode)


class _Response:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def getcode(self) -> int:
        return self.status

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class ScriptedOpener:
    def __init__(self, events: list) -> None:
        self.events = list(events)
        self.requests = []
        self.timeouts = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        self.timeouts.append(timeout)
        event = self.events.pop(0)
        if isinstance(event, BaseException):
            raise event
        if isinstance(event, dict):
            status, body = 200, event
        else:
            status, body = event
        payload = body if isinstance(body, bytes) else json.dumps(body).encode()
        return _Response(status, payload)


def _ok(choice: str = "call", confidence: float = 0.8, cost: float = 0.00021) -> dict:
    return {
        "id": "gen-test",
        "model": "typesafe/jev-1.13-20260917",
        "provider": "TypeSafe",
        "answers": {
            "action": {
                "type": "choice",
                "choice": choice,
                "confidence": confidence,
                "probabilities": {choice: confidence},
            },
            "bluff_spot": {"type": "noul", "noul": 0.33},
            "range_advantage": {
                "type": "score",
                "score": 3.1,
                "confidence": 0.7,
                "probabilities": {"0": 0, "1": 0, "2": 0.1, "3": 0.7, "4": 0.2},
            },
        },
        "usage": {"input_tokens": 120, "output_tokens": 8, "cost": cost},
    }


def _http_error(status: int, body: bytes = b"{}") -> urllib.error.HTTPError:
    return urllib.error.HTTPError(
        DECISIONS_URL,
        status,
        "error",
        Message(),
        io.BytesIO(body),
    )


def _client(events, sleep=None, api_key: str = "test-key") -> tuple[JevClient, ScriptedOpener]:
    opener = ScriptedOpener(events)
    slept: list[float] = []
    client = JevClient(
        api_key,
        opener=opener,
        sleep=slept.append if sleep is None else sleep,
    )
    client._slept = slept  # type: ignore[attr-defined]
    return client, opener


def test_posts_model_auth_and_returns_answers_and_cost():
    client, opener = _client([_ok(cost=0.00019)])
    result = client.submit(
        {"street": "flop", "persona": {"id": "shark"}},
        {"action": {"type": "choice", "instructions": "Pick.", "criteria": {"call": "priced"}}},
    )
    assert len(opener.requests) == 1
    request = opener.requests[0]
    assert request.full_url == DECISIONS_URL
    assert request.get_header("Authorization") == "Bearer test-key"
    assert request.get_header("Content-type") == "application/json"
    assert opener.timeouts == [20]
    body = json.loads(request.data.decode())
    assert body["model"] == MODEL_ID == "typesafe/jev-1.13"
    assert set(body["questions"]) == {"action"}
    assert body["state"]["persona"]["id"] == "shark"
    assert result.answers["action"]["choice"] == "call"
    assert result.answers["bluff_spot"]["noul"] == 0.33
    assert result.cost == 0.00019


def test_api_key_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-env")
    opener = ScriptedOpener([_ok()])
    JevClient(opener=opener).submit({}, {"action": {"type": "choice"}})
    assert opener.requests[0].get_header("Authorization") == "Bearer from-env"


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(JevError):
        JevClient()


def test_retries_429_and_5xx_with_backoff():
    client, opener = _client([_http_error(429), (500, b"unavailable"), _ok()])
    result = client.submit({}, {})
    assert result.cost == 0.00021
    assert len(opener.requests) == 3
    assert client._slept == [0.5, 1.0]  # type: ignore[attr-defined]


def test_retries_status_429_without_urllib_error():
    client, opener = _client([(429, b"slow"), _ok(cost=0.01)])
    assert client.submit({}, {}).cost == 0.01
    assert len(opener.requests) == 2
    assert client._slept == [0.5]  # type: ignore[attr-defined]


def test_exhausted_retries_raise_transport_error():
    client, opener = _client([(503, b"down"), (502, b"down"), (500, b"down")])
    with pytest.raises(JevTransportError) as caught:
        client.submit({}, {})
    assert caught.value.status == 500
    assert len(opener.requests) == 3
    assert client._slept == [0.5, 1.0]  # type: ignore[attr-defined]


def test_client_error_is_not_retried():
    client, opener = _client([(400, b"bad request")])
    with pytest.raises(JevTransportError) as caught:
        client.submit({}, {})
    assert caught.value.status == 400
    assert len(opener.requests) == 1
    assert client._slept == []  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"answers": {}},
        {"answers": {"bluff_spot": {"type": "noul", "noul": 0.5}}},
        {"answers": {"action": None}},
        {"answers": {"action": {"type": "noul", "noul": 0.4}}},
        {"answers": {"action": {"type": "choice", "choice": "call"}}},
        {"answers": {"action": {"type": "choice", "choice": "", "confidence": 0.5}}},
        {"answers": {"action": {"type": "choice", "choice": "call", "confidence": "high"}}},
        {"answers": {"action": {"type": "choice", "choice": "call", "confidence": 1.2}}},
        {"answers": {"action": {"type": "choice", "choice": "call", "confidence": True}}},
        [],
    ],
)
def test_missing_or_malformed_action_raises(payload):
    client, _opener = _client([(200, payload)])
    with pytest.raises(JevResponseError, match="answers.action"):
        client.submit({}, {})


def test_missing_cost_raises():
    payload = _ok()
    del payload["usage"]["cost"]
    client, _opener = _client([(200, payload)])
    with pytest.raises(JevResponseError, match="usage.cost"):
        client.submit({}, {})


def test_non_json_success_raises():
    client, _opener = _client([(200, b"not-json")])
    with pytest.raises(JevResponseError):
        client.submit({}, {})
