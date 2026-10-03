"""Spectator API. The Jev client is fake and the suite does not use the network."""

import json
import threading

from fastapi.testclient import TestClient

from jev_poker.engine.game import SEATS, STARTING_STACK
from jev_poker.jev.client import JevResult
from jev_poker.web.app import create_app

TABLE_CHIPS = STARTING_STACK * SEATS


class CheckCall:
    def submit(self, state: dict, questions: dict) -> JevResult:
        legal = state["legal_actions"]
        choice = "check" if "check" in legal else "call"
        return JevResult(
            answers={
                "action": {
                    "type": "choice",
                    "choice": choice,
                    "confidence": 0.9,
                    "probabilities": {choice: 0.9},
                },
                "bluff_spot": {"type": "noul", "noul": 0.2},
                "range_advantage": {"type": "score", "score": 2.0, "confidence": 0.4, "probabilities": {"2": 1}},
            },
            cost=0.0001,
        )


class Blocked(CheckCall):
    def __init__(self) -> None:
        self.release = threading.Event()

    def submit(self, state: dict, questions: dict) -> JevResult:
        assert self.release.wait(timeout=5)
        return super().submit(state, questions)


def _events(client: TestClient) -> list[dict]:
    found: list[dict] = []
    with client.stream("GET", "/api/tournament/stream") as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if not line.startswith("data:"):
                continue
            payload = json.loads(line.split(":", 1)[1])
            found.append(payload)
            if payload["type"] == "finished":
                break
    return found


def test_health_and_dev_server_message(tmp_path):
    app = create_app(client=CheckCall(), runs_root=tmp_path, iterations=2)
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"status": "ok"}
        page = client.get("/")
        assert page.status_code == 200
        assert "The UI dev server is on port 5173." in page.text


def test_stream_deals_cards_and_conserves_chips(tmp_path):
    app = create_app(client=CheckCall(), runs_root=tmp_path, iterations=3)
    with TestClient(app) as client:
        started = client.post("/api/tournament", json={"hands": 2, "seed": 1})
        assert started.status_code == 202
        run_id = started.json()["id"]
        events = _events(client)
        kinds = {event["type"] for event in events}
        assert {"street", "decision", "showdown", "finished"} <= kinds
        street = next(event for event in events if event["type"] == "street")
        assert len(street["table"]["players"]) == 4
        assert all(len(player["hole_cards"]) == 2 for player in street["table"]["players"])
        summary = events[-1]["summary"]
        assert summary["hands_played"] == 2
        assert sum(summary["stacks"]) == TABLE_CHIPS == 8000
        listed = client.get("/api/runs").json()["runs"]
        assert listed[0]["id"] == run_id
        saved = client.get(f"/api/runs/{run_id}").json()
        assert len(saved["hands"]) == 2
        assert sum(saved["hands"][-1]["stacks"]) == 8000
        blob = json.dumps(saved["hands"])
        for hole in saved["hands"][0]["showdown_hole_cards"]:
            for card in hole["hole_cards"]:
                assert card in blob
        assert client.get("/api/runs/../secrets").status_code == 404


def test_second_start_is_rejected_while_a_run_is_active(tmp_path):
    blocked = Blocked()
    app = create_app(client=blocked, runs_root=tmp_path, iterations=2)
    with TestClient(app) as client:
        first = client.post("/api/tournament", json={"hands": 1, "seed": 4})
        assert first.status_code == 202
        second = client.post("/api/tournament", json={"hands": 1, "seed": 4})
        assert second.status_code == 409
        blocked.release.set()
        app.state.manager._thread.join(timeout=20)


def test_pause_between_hands_waits_for_resume(tmp_path):
    app = create_app(client=CheckCall(), runs_root=tmp_path, iterations=3)
    with TestClient(app) as client:
        started = client.post(
            "/api/tournament",
            json={"hands": 2, "seed": 3, "pause_between_hands": True},
        )
        assert started.status_code == 202
        manager = app.state.manager
        for _ in range(400):
            if manager.waiting:
                break
            threading.Event().wait(0.05)
        else:
            raise AssertionError("the run did not pause between hands")
        log = tmp_path / started.json()["id"] / "hands.jsonl"
        assert len([line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]) == 1
        resumed = client.post("/api/tournament/pause", json={"resume": True})
        assert resumed.status_code == 200
        assert manager._thread.join(timeout=20) is None
        assert not manager.active
        lines = [line for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(lines) == 2
        assert sum(json.loads(lines[-1])["stacks"]) == 8000
