"""Tournament runner with a fake Jev client. No network."""

import json

from jev_poker.agents.personas import PERSONAS
from jev_poker.engine.game import SEATS, STARTING_STACK, Game
from jev_poker.jev.client import JevResult
from jev_poker.sim.__main__ import parse_args
from jev_poker.sim.tournament import PERSONA_IDS, format_summary, play_tournament

TABLE_CHIPS = STARTING_STACK * SEATS


class CheckCallClient:
    """Always a legal check or call at confidence 0.9."""

    def __init__(self, cost: float = 0.0001) -> None:
        self.cost = cost
        self.calls = 0

    def submit(self, state: dict, questions: dict) -> JevResult:
        self.calls += 1
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
                "bluff_spot": {"type": "noul", "noul": 0.1},
                "range_advantage": {"type": "score", "score": 2.0, "confidence": 0.4},
            },
            cost=self.cost,
        )


class RaisingClient:
    def submit(self, state: dict, questions: dict) -> JevResult:
        raise RuntimeError("jev unavailable")


def test_three_hands_conserve_chips_and_log_legal_actions(tmp_path):
    client = CheckCallClient()
    result = play_tournament(3, 1, client=client, iterations=8, runs_root=tmp_path)
    hands = result["hands"]

    assert len(hands) == 3
    assert [persona.id for persona in PERSONAS] == ["rock", "shark", "caller", "maniac"]
    assert hands[0]["actions"][0]["seat"] == 3
    assert hands[0]["actions"][0]["persona_id"] == "maniac"

    replay = Game(seed=1)
    for hand in hands:
        assert hand["seed"] == 1
        assert sum(hand["stacks"]) == TABLE_CHIPS == 8000
        assert hand["showdown_hole_cards"] is not None
        assert len(hand["board"]) == 5
        holes = {item["seat"]: item["hole_cards"] for item in hand["showdown_hole_cards"]}
        assert set(holes) == {0, 1, 2, 3}
        replay.new_hand()
        for decision in hand["actions"]:
            seat = decision["seat"]
            assert replay.to_act == seat
            legal = [action.value for action in replay.legal_actions(seat)]
            assert decision["action"] in legal
            assert decision["source"] == "jev"
            blob = json.dumps(decision)
            for other, cards in holes.items():
                if other == seat:
                    assert all(card in blob for card in cards)
                    continue
                for card in cards:
                    assert card not in blob
            replay.apply(seat, decision["action"])
        assert replay.is_hand_over()
        assert [player["stack"] for player in replay.public_state()["players"]] == hand["stacks"]

    lines = result["path"].read_text(encoding="utf-8").splitlines()
    assert result["path"].name == "hands.jsonl"
    assert len(lines) == 3
    assert [json.loads(line)["hand_number"] for line in lines] == [1, 2, 3]
    summary = result["summary"]
    assert summary["hands_played"] == 3
    assert summary["stacks"] == hands[-1]["stacks"]
    assert summary["decisions"]["jev"] == client.calls
    assert summary["decisions"]["math"] == 0
    assert summary["decisions"]["math_error"] == 0
    assert summary["mean_jev_confidence"] == 0.9
    text = format_summary(summary)
    assert "Hands played: 3" in text
    assert "math_error 0" in text
    assert "Mean Jev confidence: 0.900" in text


def test_client_exception_uses_math_error_and_finishes(tmp_path):
    result = play_tournament(1, 2, client=RaisingClient(), iterations=8, runs_root=tmp_path)
    hand = result["hands"][0]
    assert hand["actions"]
    assert {action["source"] for action in hand["actions"]} == {"math_error"}
    assert all(action["answers"] is None for action in hand["actions"])
    assert all(action["cost_usd"] == 0.0 for action in hand["actions"])
    assert sum(hand["stacks"]) == 8000
    assert hand["pot_results"]
    assert result["summary"]["decisions"]["math_error"] == len(hand["actions"])
    assert result["summary"]["mean_jev_confidence"] is None

    replay = Game(seed=2)
    replay.new_hand()
    for decision in hand["actions"]:
        legal = [action.value for action in replay.legal_actions(decision["seat"])]
        assert decision["action"] in legal
        replay.apply(decision["seat"], decision["action"])
    assert replay.is_hand_over()


def test_cli_defaults_to_ten_hands():
    args = parse_args(["--seed", "1"])
    assert args.hands == 10
    assert args.seed == 1
    assert PERSONA_IDS == ("rock", "shark", "caller", "maniac")
