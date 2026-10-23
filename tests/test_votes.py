"""River votes. The client is fake and this file makes no network calls."""

import copy
import json
import urllib.request

from fastapi.testclient import TestClient

from jev_poker.agents.personas import PERSONAS
from jev_poker.jev.client import JevResult, JevTransportError
from jev_poker.votes import load_frozen, prepare_state, probe, run_votes
from jev_poker.web.app import create_app

_LEGAL = ["check", "raise_half_pot", "raise_pot", "all_in"]
_SCORES = (0.4, 1.4, 2.4, 3.6)


class VoteFake:
    def __init__(self, choices: list[str], confidences: list[float | None]) -> None:
        self.choices = list(choices)
        self.confidences = list(confidences)
        self.calls: list[tuple[dict, dict]] = []
        self._prior = 0

    def submit(self, state: dict, questions: dict) -> JevResult:
        self.calls.append((copy.deepcopy(state), copy.deepcopy(questions)))
        if "action" not in questions:
            self._prior += 1
            score = _SCORES[self._prior - 1]
            return JevResult(
                answers={
                    "bluff_spot": {"type": "noul", "noul": self._prior / 10},
                    "range_advantage": {"type": "score", "score": score},
                },
                cost=0.0,
            )
        choice = self.choices.pop(0)
        confidence = self.confidences.pop(0)
        probabilities = {name: 0.1 for name in state["legal_actions"]}
        probabilities[choice] = 0.7
        action = {"type": "choice", "choice": choice, "probabilities": probabilities}
        if confidence is not None:
            action["confidence"] = confidence
        return JevResult(answers={"action": action}, cost=0.0)


class ProbeClient:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.calls: list[tuple[dict, dict]] = []

    def submit(self, state: dict, questions: dict) -> JevResult:
        self.calls.append((state, questions))
        if self.error is not None:
            raise self.error
        return JevResult(answers={"probe": {"type": "noul", "noul": 0.0}}, cost=0.0)


def _decision() -> dict:
    return {
        "hand_number": 2,
        "state": {
            "street": "river",
            "hero": {
                "seat": 3,
                "hole_cards": ["2h", "2c"],
                "position": "BB",
                "stack": 1800,
                "committed_this_street": 0,
            },
            "board": ["Ks", "As", "Jd", "4s", "5d"],
            "pot": 320,
            "to_call": 0,
            "pot_odds": 0.0,
            "spr": 5.6,
            "hero_equity_vs_random": 0.32666666666666666,
            "hero_equity_vs_continuing": 0.08333333333333333,
            "continuing_fraction": 0.7,
            "board_texture": {"monotone": False, "connectedness": 0, "paired": False},
            "legal_actions": list(_LEGAL),
            "opponents": [],
            "prior_judgments": {
                "bluff_spot": 0.99,
                "range_advantage_score": 0.0,
                "range_advantage_label": "Clear disadvantage",
            },
        },
    }


def _block_network(monkeypatch) -> None:
    def explode(*_args, **_kwargs):
        raise AssertionError("network")

    monkeypatch.setattr(urllib.request, "urlopen", explode)


def test_load_frozen_selects_the_hand_two_river_raise(tmp_path) -> None:
    decoy = {
        "hand_number": 2,
        "actions": [
            {"street": "river", "persona_id": "maniac", "action": "check", "state": {"board": ["2c"]}},
        ],
    }
    other = {
        "hand_number": 3,
        "actions": [
            {"street": "river", "persona_id": "maniac", "action": "raise_half_pot", "state": {"board": ["3c"]}},
        ],
    }
    match = {
        "hand_number": 2,
        "actions": [
            {
                "street": "river",
                "persona_id": "maniac",
                "action": "raise_half_pot",
                "state": {"board": ["Ks", "As", "Jd", "4s", "5d"], "legal_actions": list(_LEGAL)},
            }
        ],
    }
    path = tmp_path / "hands.jsonl"
    path.write_text(
        "\n".join(json.dumps(row) for row in (decoy, other, match)) + "\n",
        encoding="utf-8",
    )
    frozen = load_frozen(path)
    assert frozen["hand_number"] == 2
    assert frozen["state"]["board"] == ["Ks", "As", "Jd", "4s", "5d"]


def test_recorded_spot_is_the_frozen_river(monkeypatch) -> None:
    _block_network(monkeypatch)
    frozen = load_frozen("recordings/seed2-four-hands.jsonl")
    state = frozen["state"]
    assert frozen["hand_number"] == 2
    assert frozen["street"] == "river"
    assert frozen["persona_id"] == "maniac"
    assert frozen["action"] == "raise_half_pot"
    assert state["hero"]["hole_cards"] == ["2h", "2c"]
    assert state["board"] == ["Ks", "As", "Jd", "4s", "5d"]
    assert state["legal_actions"] == _LEGAL
    assert "prior_judgments" not in state


def test_votes_reuse_the_two_call_path_and_skip_the_network(monkeypatch) -> None:
    _block_network(monkeypatch)
    decision = _decision()
    original = copy.deepcopy(decision)
    client = VoteFake(
        ["check", "raise_half_pot", "fold", "all_in", "raise_pot", "check"],
        [0.81, 0.55, 0.9, 0.7, 0.6, 0.4],
    )
    payload = run_votes(client, decision)

    assert decision == original
    assert len(client.calls) == 10
    assert [persona.id for persona in PERSONAS] == ["rock", "shark", "caller", "maniac"]
    for index, persona in enumerate(PERSONAS):
        prior_state, prior_questions = client.calls[index * 2]
        action_state, action_questions = client.calls[index * 2 + 1]
        assert "prior_judgments" not in prior_state
        assert set(prior_questions) == {"bluff_spot", "range_advantage"}
        assert set(action_questions) == {"action"}
        assert list(action_questions["action"]["criteria"]) == _LEGAL
        assert prior_state["legal_actions"] == _LEGAL
        assert action_state["legal_actions"] == _LEGAL
        assert prior_state["hero_equity_vs_continuing"] == 0.08333333333333333
        assert prior_state["persona"]["id"] == persona.id
        assert action_state["prior_judgments"]["bluff_spot"] == (index + 1) / 10
        assert action_state["prior_judgments"]["range_advantage_score"] == _SCORES[index]

    by_id = {row["id"]: row for row in payload["personas"]}
    assert by_id["rock"]["action"] == "check"
    assert by_id["rock"]["confidence"] == 0.81
    assert by_id["rock"]["probabilities"]["check"] == 0.7
    assert by_id["rock"]["bluff"] == 0.1
    assert by_id["rock"]["range_score"] == 0.4
    assert by_id["shark"]["action"] == "raise_half_pot"
    assert by_id["caller"]["action"] == "check"
    assert by_id["caller"]["confidence"] == 0.9
    assert by_id["maniac"]["action"] == "all_in"
    assert by_id["maniac"]["range_score"] == 3.6
    assert by_id["maniac"]["bluff"] == 0.4
    for row in payload["personas"]:
        assert row["math_action"] == "check"
    assert payload["hole_cards"] == ["2h", "2c"]
    assert payload["board"] == ["Ks", "As", "Jd", "4s", "5d"]
    assert payload["legal_actions"] == _LEGAL

    forced_states = client.calls[8:]
    assert [call[0]["prior_judgments"]["bluff_spot"] for call in forced_states] == [0.1, 0.9]
    for state, questions in forced_states:
        assert set(questions) == {"action"}
        assert state["prior_judgments"]["range_advantage_score"] == 3.6
        assert state["prior_judgments"]["range_advantage_label"] == "Clear advantage"
        assert state["legal_actions"] == _LEGAL
        assert state["persona"]["id"] == "maniac"
    assert [row["bluff_spot"] for row in payload["maniac_bluff"]] == [0.1, 0.9]
    assert [row["action"] for row in payload["maniac_bluff"]] == ["raise_pot", "check"]
    assert [row["range_score"] for row in payload["maniac_bluff"]] == [3.6, 3.6]
    assert payload["maniac_bluff"][0]["probabilities"]["raise_pot"] == 0.7


def test_missing_confidence_plays_the_equity_rule(monkeypatch) -> None:
    _block_network(monkeypatch)
    client = VoteFake(
        ["check", "check", "check", "all_in", "check", "check"],
        [0.5, 0.5, 0.5, None, 0.5, 0.5],
    )
    payload = run_votes(client, _decision())
    maniac = next(row for row in payload["personas"] if row["id"] == "maniac")
    assert maniac["action"] == "check"
    assert maniac["math_action"] == "check"
    assert maniac["confidence"] is None


def test_prepare_state_drops_prior_judgments_and_keeps_legal_actions() -> None:
    state = _decision()["state"]
    prepared = prepare_state(state, PERSONAS[0])
    assert "prior_judgments" not in prepared
    assert prepared["legal_actions"] == _LEGAL
    assert prepared["persona"]["id"] == "rock"
    assert "prior_judgments" in state


def test_probe_succeeds_only_on_a_returned_call(capsys) -> None:
    ok = ProbeClient()
    assert probe(ok) == 200
    assert ok.calls[0][0] == {"probe": True}
    assert "action" not in ok.calls[0][1]
    assert capsys.readouterr().out == ""

    failed = ProbeClient(JevTransportError(503, "busy"))
    assert probe(failed) == 503
    assert capsys.readouterr().out.strip() == "probe HTTP 503"


def test_votes_route_reads_the_file_and_does_not_call_out(tmp_path, monkeypatch) -> None:
    _block_network(monkeypatch)
    missing = tmp_path / "missing.json"
    present = tmp_path / "river-votes.json"
    present.write_text(json.dumps({"board": ["Ks"], "personas": [{"action": "check"}]}), encoding="utf-8")
    monkeypatch.setattr("jev_poker.web.app._votes_file", lambda: missing)
    app = create_app(client=VoteFake(["check"], [0.5]), runs_root=tmp_path)
    with TestClient(app) as client:
        assert client.get("/api/votes").status_code == 404
        monkeypatch.setattr("jev_poker.web.app._votes_file", lambda: present)
        body = client.get("/api/votes").json()
    assert body["board"] == ["Ks"]
    assert body["personas"][0]["action"] == "check"
