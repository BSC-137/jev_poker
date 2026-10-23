"""Math fallback, persona criteria, and the agent with a fake Jev client."""

import json
import random
import urllib.request

from jev_poker.agents.jev_agent import JevAgent, build_action_questions, build_prior_questions
from jev_poker.agents.personas import PERSONAS, PERSONAS_BY_ID
from jev_poker.agents.policy import board_bonus_from_texture, decide
from jev_poker.engine.actions import Action
from jev_poker.engine.game import Game
from jev_poker.jev.client import JevClient, JevResult, MODEL_ID

_FACING = ["fold", "call", "raise_half_pot", "raise_pot", "all_in"]
_RANGE = [
    "Clear disadvantage",
    "Slight disadvantage",
    "Neutral",
    "Slight advantage",
    "Clear advantage",
]


class FakeClient:
    def __init__(
        self,
        choice: str,
        confidence: float,
        cost: float = 0.001,
        *,
        noul: float = 0.25,
        score: float = 2.0,
    ) -> None:
        self.choice = choice
        self.confidence = confidence
        self.cost = cost
        self.noul = noul
        self.score = score
        self.states: list[dict] = []
        self.questions: list[dict] = []

    def submit(self, state: dict, questions: dict) -> JevResult:
        self.states.append(state)
        self.questions.append(questions)
        return JevResult(
            answers={
                "action": {
                    "type": "choice",
                    "choice": self.choice,
                    "confidence": self.confidence,
                    "probabilities": {self.choice: self.confidence},
                },
                "bluff_spot": {"type": "noul", "noul": self.noul},
                "range_advantage": {
                    "type": "score",
                    "score": self.score,
                    "confidence": 0.5,
                    "probabilities": {"2": 1.0},
                },
            },
            cost=self.cost,
        )


class MissingConfidence:
    def submit(self, state: dict, questions: dict) -> JevResult:
        if "action" in questions:
            return JevResult(answers={"action": {"type": "choice", "choice": "call"}}, cost=0.001)
        return JevResult(
            answers={
                "bluff_spot": {"type": "noul", "noul": 0.2},
                "range_advantage": {"type": "score", "score": 1.0},
            },
            cost=0.001,
        )


class _Response:
    def __init__(self, body: bytes) -> None:
        self._body = body

    def getcode(self) -> int:
        return 200

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class RecordingOpener:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.requests = []
        self.timeouts = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        self.timeouts.append(timeout)
        return _Response(json.dumps(self.payload).encode())


def _facing_bet() -> tuple[Game, int]:
    game = Game(seed=1)
    game.new_hand()
    seat = game.to_act
    assert [action.value for action in game.legal_actions(seat)] == _FACING
    return game, seat


def _check_only() -> tuple[Game, int]:
    game = Game(seed=1)
    game.new_hand()
    game.apply(3, Action.CALL)
    game.apply(0, Action.CALL)
    game.apply(1, Action.CALL)
    seat = game.to_act
    game.players[seat].can_raise = False
    assert [action.value for action in game.legal_actions(seat)] == ["check"]
    return game, seat


def _play(choice: str, confidence: float, node: str = "facing", persona: str = "shark"):
    game, seat = _facing_bet() if node == "facing" else _check_only()
    fake = FakeClient(choice, confidence)
    record = JevAgent(PERSONAS_BY_ID[persona], fake).decide(
        game,
        seat,
        iterations=10,
        rng=random.Random(0),
    )
    return record, fake


def test_personas_are_the_four_specified_profiles():
    assert [persona.id for persona in PERSONAS] == ["rock", "shark", "caller", "maniac"]
    assert [persona.continuing_fraction for persona in PERSONAS] == [0.25, 0.40, 0.55, 0.70]
    assert [persona.fallback_equity_margin for persona in PERSONAS] == [0.12, 0.04, 0.0, -0.06]
    assert len({persona.color for persona in PERSONAS}) == 4
    assert [persona.display_name for persona in PERSONAS] == ["Rock", "Shark", "Caller", "Maniac"]


def test_illegal_jev_action_falls_back_to_math():
    record, fake = _play("fold", 0.9, node="check")
    assert len(fake.questions) == 2
    assert "action" not in fake.questions[0]
    assert list(fake.questions[1]) == ["action"]
    assert "prior_judgments" in fake.states[1]
    assert record["source"] == "math"
    assert record["action"] == "check"
    assert record["math_action"] == "check"
    assert record["answers"]["bluff_spot"]["type"] == "noul"
    assert record["answers"]["range_advantage"]["type"] == "score"
    assert record["cost_usd"] == fake.cost * 2


def test_low_confidence_legal_action_stays_with_jev():
    record, _fake = _play("all_in", 0.2)
    assert record["source"] == "jev"
    assert record["action"] == "all_in"
    assert record["confidence"] == 0.2
    assert record["action"] in record["state"]["legal_actions"]


def test_confident_legal_action_comes_from_jev():
    record, fake = _play("call", 0.8)
    assert record["action"] == "call"
    assert record["source"] == "jev"
    assert record["seat"] == record["state"]["hero"]["seat"]
    assert record["persona_id"] == "shark"
    assert record["street"] == record["state"]["street"]
    assert record["state"]["persona"]["continuing_fraction"] == 0.40
    assert record["state"]["continuing_fraction"] == 0.40
    assert set(record) == {
        "seat",
        "persona_id",
        "street",
        "state",
        "answers",
        "action",
        "math_action",
        "source",
        "confidence",
        "cost_usd",
        "elapsed_seconds",
    }
    assert len(fake.questions) == 2
    assert record["cost_usd"] == fake.cost * 2


def test_criteria_keys_match_check_only_and_facing_bet_nodes():
    expected = {
        "check": ["check"],
        "facing": _FACING,
    }
    for node, legal in expected.items():
        _record, fake = _play("check" if node == "check" else "call", 0.8, node=node, persona="rock")
        assert "action" not in fake.questions[0]
        assert set(fake.questions[0]) == {"bluff_spot", "range_advantage"}
        assert list(fake.questions[1]) == ["action"]
        assert list(fake.questions[1]["action"]["criteria"]) == legal
        assert "prior_judgments" not in fake.states[0]
        assert set(fake.states[1]["prior_judgments"]) == {
            "bluff_spot",
            "range_advantage_score",
            "range_advantage_label",
        }
        assert fake.questions[0]["range_advantage"]["criteria"] == _RANGE


def test_request_body_pins_model_and_question_names(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("network access is not allowed")

    monkeypatch.setattr(urllib.request, "urlopen", explode)
    opener = RecordingOpener(
        {
            "answers": {
                "action": {"type": "choice", "choice": "call", "confidence": 0.8},
                "bluff_spot": {"type": "noul", "noul": 0.1},
                "range_advantage": {"type": "score", "score": 2.0, "confidence": 0.4},
            },
            "usage": {"cost": 0.00019},
        }
    )
    game, seat = _facing_bet()
    record = JevAgent(PERSONAS_BY_ID["caller"], JevClient("test-key", opener=opener)).decide(
        game,
        seat,
        iterations=10,
        rng=random.Random(1),
    )
    assert len(opener.requests) == 2
    assert opener.timeouts == [20, 20]
    first = json.loads(opener.requests[0].data.decode())
    second = json.loads(opener.requests[1].data.decode())
    assert first["model"] == second["model"] == "typesafe/jev-1.13" == MODEL_ID
    assert set(first["questions"]) == {"bluff_spot", "range_advantage"}
    assert "action" not in first["questions"]
    assert first["questions"]["bluff_spot"]["type"] == "noul"
    assert first["questions"]["range_advantage"]["type"] == "score"
    assert "prior_judgments" not in first["state"]
    assert set(second["questions"]) == {"action"}
    assert second["questions"]["action"]["type"] == "choice"
    assert list(second["questions"]["action"]["criteria"]) == _FACING
    assert "check" not in second["questions"]["action"]["criteria"]
    assert second["state"]["prior_judgments"] == {
        "bluff_spot": 0.1,
        "range_advantage_score": 2.0,
        "range_advantage_label": "Neutral",
    }
    assert second["state"]["persona"]["id"] == "caller"
    assert record["source"] == "jev"
    assert record["cost_usd"] == 0.00019 * 2
    assert record["elapsed_seconds"] >= 0


def test_questions_use_the_documented_instructions():
    prior = build_prior_questions(PERSONAS_BY_ID["maniac"])
    action = build_action_questions(PERSONAS_BY_ID["maniac"], ["check", "raise_half_pot"])
    assert action["action"]["instructions"] == (
        "Pick the legal action for this persona. "
        "prior_judgments are evidence, not orders. "
        "Use only the provided actions."
    )
    assert prior["bluff_spot"]["instructions"] == (
        "Is a bluff bet or raise aligned with this persona on this street? "
        "Use hero_equity_vs_continuing, pot_odds, board_texture, opponent fold_to_bet, and spr from the state."
    )
    assert "0.5" not in prior["bluff_spot"]["instructions"]
    assert prior["range_advantage"]["instructions"] == (
        "How strong is hero's range advantage for value betting on this board?"
    )
    assert prior["range_advantage"]["criteria"] == _RANGE
    assert list(action["action"]["criteria"]) == ["check", "raise_half_pot"]


def test_criteria_do_not_use_retired_equity_numerals():
    retired = ("0.70", "0.80", "0.92", "0.55", "0.45")
    actions = ["fold", "check", "call", "raise_half_pot", "raise_pot", "all_in"]
    for persona in PERSONAS:
        lines = list(persona.action_criteria(actions).values())
        lines.extend(persona.bluff_criteria().values())
        for line in lines:
            for numeral in retired:
                assert numeral not in line


def test_prior_judgments_round_and_clamp_the_range_score():
    game, seat = _facing_bet()
    high = FakeClient("call", 0.8, score=5.2, noul=0.42)
    JevAgent(PERSONAS_BY_ID["shark"], high).decide(game, seat, iterations=10, rng=random.Random(0))
    assert "action" not in high.questions[0]
    assert list(high.questions[1]) == ["action"]
    assert high.states[1]["prior_judgments"] == {
        "bluff_spot": 0.42,
        "range_advantage_score": 5.2,
        "range_advantage_label": "Clear advantage",
    }
    game, seat = _facing_bet()
    low = FakeClient("call", 0.8, score=-1)
    JevAgent(PERSONAS_BY_ID["shark"], low).decide(game, seat, iterations=10, rng=random.Random(0))
    assert low.states[1]["prior_judgments"]["range_advantage_label"] == "Clear disadvantage"


def test_missing_confidence_uses_math():
    game, seat = _facing_bet()
    record = JevAgent(PERSONAS_BY_ID["rock"], MissingConfidence()).decide(
        game,
        seat,
        iterations=10,
        rng=random.Random(0),
    )
    assert record["source"] == "math"
    assert record["confidence"] is None
    assert record["action"] == record["math_action"]
    assert record["answers"]["action"]["choice"] == "call"


def test_jev_confidence_threshold_and_illegal_action():
    legal = ["fold", "call"]
    assert decide(legal, 0.3, 0.1, 0.12, "call", 0.45)["source"] == "jev"
    assert decide(legal, 0.3, 0.1, 0.12, "call", 0.449) == {"action": "fold", "source": "math"}
    assert decide(legal, 0.3, 0.1, 0.12, "raise_pot", 0.99)["source"] == "math"
    assert decide(legal, 0.3, 0.1, 0.12, "call", 0.8) == {"action": "call", "source": "jev"}


def test_math_policy_checks_bets_calls_and_shoves():
    free = ["check", "raise_half_pot", "raise_pot", "all_in"]
    facing = _FACING
    dry = board_bonus_from_texture({"connectedness": 0, "monotone": False})
    wet = board_bonus_from_texture({"connectedness": 2, "monotone": False})
    assert dry == 0.03
    assert wet == 0.0
    assert board_bonus_from_texture({"connectedness": 0, "monotone": True}) == 0.0

    shark_bet = decide(free, 0.0, 0.52, 0.04, None, None, to_call=0, persona_id="shark", board_bonus=dry)
    assert shark_bet == {"action": "raise_half_pot", "source": "math"}
    rock_check = decide(free, 0.0, 0.60, 0.12, None, None, to_call=0, persona_id="rock", board_bonus=dry)
    assert rock_check == {"action": "check", "source": "math"}
    thin = decide(free, 0.0, 0.50, 0.04, None, None, to_call=0, persona_id="maniac", board_bonus=0.0)
    assert thin == {"action": "check", "source": "math"}

    fold = decide(facing, 0.33, 0.40, 0.12, None, None, to_call=50, spr=10, persona_id="rock")
    assert fold == {"action": "fold", "source": "math"}
    call = decide(facing, 0.33, 0.40, 0.04, None, None, to_call=50, spr=10, persona_id="shark")
    assert call == {"action": "call", "source": "math"}
    light = decide(facing, 0.33, 0.28, -0.06, None, None, to_call=50, spr=10, persona_id="maniac")
    assert light == {"action": "call", "source": "math"}

    pot = decide(facing, 0.2, 0.80, 0.0, None, None, to_call=20, spr=8, persona_id="caller")
    assert pot == {"action": "raise_pot", "source": "math"}
    shove = decide(facing, 0.2, 0.92, 0.0, None, None, to_call=20, spr=2.9, persona_id="caller")
    assert shove == {"action": "all_in", "source": "math"}
    no_shove = decide(facing, 0.2, 0.92, 0.0, None, None, to_call=20, spr=3, persona_id="caller")
    assert no_shove == {"action": "raise_pot", "source": "math"}
    clamped = decide(["check"], 0.0, 0.95, 0.04, "all_in", 0.99, to_call=0, spr=1, persona_id="shark")
    assert clamped == {"action": "check", "source": "math"}
