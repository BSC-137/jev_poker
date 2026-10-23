"""Report command. Reads fixture logs and does not use the network."""

import json
import urllib.request

from jev_poker.sim.report import write_report


def _decision(**overrides) -> dict:
    state = {
        "hero": {"hole_cards": ["As", "Kd"]},
        "board": ["Ah", "7c", "2d"],
        "pot": 120,
        "to_call": 40,
        "pot_odds": 0.25,
        "hero_equity_vs_random": 0.62,
        "hero_equity_vs_continuing": 0.41,
        "opponents": [
            {"seat": 1, "in_hand": True, "stats": {"fold_to_bet": 0.5}},
            {"seat": 2, "in_hand": True, "stats": {"fold_to_bet": None}},
            {"seat": 3, "in_hand": False, "stats": {"fold_to_bet": 0.99}},
        ],
    }
    answers = {
        "action": {
            "type": "choice",
            "choice": "fold",
            "confidence": 0.8,
            "probabilities": {"fold": 0.7, "call": 0.3},
        },
        "bluff_spot": {"type": "noul", "noul": 0.7},
        "range_advantage": {"type": "score", "score": 3.2},
    }
    row = {
        "seat": 0,
        "persona_id": "rock",
        "street": "flop",
        "action": "fold",
        "math_action": "call",
        "source": "jev",
        "confidence": 0.8,
        "cost_usd": 0.01,
        "elapsed_seconds": 1.5,
        "answers": answers,
        "state": state,
    }
    row.update(overrides)
    return row


def _write(path, hands) -> None:
    path.parent.mkdir(parents=True)
    path.write_text("".join(json.dumps(hand) + "\n" for hand in hands), encoding="utf-8")


def test_report_writes_the_required_sections(tmp_path, monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("network access is not allowed")

    monkeypatch.setattr(urllib.request, "urlopen", explode)
    jev_path = tmp_path / "run-jev" / "hands.jsonl"
    math_path = tmp_path / "run-math" / "hands.jsonl"
    shark = _decision(
        seat=1,
        persona_id="shark",
        street="turn",
        action="raise_pot",
        math_action="check",
        confidence=0.4,
        cost_usd=0.02,
        elapsed_seconds=0.5,
        answers={
            "action": {
                "type": "choice",
                "choice": "raise_pot",
                "confidence": 0.4,
                "probabilities": {"raise_pot": 0.8},
            },
            "bluff_spot": {"type": "noul", "noul": 0.2},
            "range_advantage": {"type": "score", "score": 1.0},
        },
        state={
            "hero": {"hole_cards": ["Qs", "Qd"]},
            "board": ["Th", "9h", "8h", "2c"],
            "pot": 400,
            "to_call": 0,
            "pot_odds": 0.0,
            "hero_equity_vs_random": 0.71,
            "hero_equity_vs_continuing": 0.33,
            "opponents": [{"seat": 0, "in_hand": True, "stats": {"fold_to_bet": 0.2}}],
        },
    )
    hands = [
        {
            "seed": 7,
            "hand_number": 1,
            "stacks": [2100, 1900, 2000, 2000],
            "actions": [
                _decision(),
                shark,
                _decision(
                    seat=2,
                    persona_id="caller",
                    street="river",
                    action="check",
                    math_action="check",
                    source="math",
                    confidence=None,
                    cost_usd=0,
                    elapsed_seconds=0,
                    answers=None,
                    state={"pot": 10, "board": [], "hero": {"hole_cards": ["2c", "3d"]}},
                ),
                _decision(
                    seat=3,
                    persona_id="maniac",
                    street="preflop",
                    action="fold",
                    math_action="fold",
                    source="math_error",
                    confidence=None,
                    cost_usd=0,
                    elapsed_seconds=0,
                    answers=None,
                    error="RuntimeError: boom",
                    state={"pot": 30, "board": [], "hero": {"hole_cards": ["7h", "8h"]}},
                ),
            ],
        }
    ]
    _write(jev_path, hands)
    _write(math_path, [{"seed": 9, "hand_number": 1, "stacks": [1000, 3000, 2000, 2000], "actions": []}])
    destination = write_report(jev_path, math_path, reports_dir=tmp_path / "reports")
    assert destination.name == "run-jev.md"
    text = destination.read_text(encoding="utf-8")
    assert text.splitlines()[2] == (
        "Equity is Monte Carlo, the continuing range is a strength filter, "
        "and this is not a Nash equilibrium."
    )
    assert "Hands: 1" in text
    assert "Decisions: 4" in text
    assert "Sources: jev 2, math 1, math_error 1" in text
    assert "Mean confidence: 0.600" in text
    assert "Total USD: 0.030000" in text
    assert "Mean elapsed seconds: 0.500" in text
    assert "| Persona | fold | check | call | raise_half_pot | raise_pot | all_in |" in text
    assert "| rock | 1 | 0 | 0 | 0 | 0 | 0 |" in text
    assert "| shark | 0 | 0 | 0 | 0 | 1 | 0 |" in text
    assert "| caller | 0 | 1 | 0 | 0 | 0 | 0 |" in text
    assert "| maniac | 1 | 0 | 0 | 0 | 0 | 0 |" in text
    assert "2 / 2 (100.0%)" in text
    assert "bluff_spot >= 0.6" in text
    assert "1 / 1 (100.0%)" in text
    assert "range_advantage_score >= 3" in text
    spots = text.split("## Disagreement spots", 1)[1]
    assert spots.index("shark") < spots.index("rock")
    assert "Hole cards: Qs Qd" in spots
    assert "Board: Th 9h 8h 2c" in spots
    assert "Pot: 400" in spots
    assert "Hole cards: As Kd" in spots
    assert "Board: Ah 7c 2d" in spots
    assert "Pot: 120" in spots
    assert "To call: 40" in spots
    assert "Pot odds: 0.25" in spots
    assert "Equity vs random: 0.62" in spots
    assert "Equity vs continuing: 0.41" in spots
    assert "seat 1: 0.5" in spots
    assert "seat 2: n/a" in spots
    assert "0.99" not in text
    assert "Action: fold" in spots
    assert "Math action: call" in spots
    assert "Confidence: 0.8" in spots
    assert "fold 0.7, call 0.3" in spots
    assert "Bluff spot: 0.7" in spots
    assert "Range score: 3.2" in spots
    assert "Action: raise_pot" in spots
    assert "Math action: check" in spots
    assert "| Jev (run-jev) | 7 | 2100, 1900, 2000, 2000 |" in text
    assert "| Math | 9 | 1000, 3000, 2000, 2000 |" in text


def test_report_keeps_the_eight_largest_pots(tmp_path):
    actions = []
    for index in range(1, 10):
        actions.append(
            _decision(
                state={
                    "hero": {"hole_cards": ["As", "Kd"]},
                    "board": [],
                    "pot": index * 10,
                    "to_call": 1,
                    "pot_odds": 0.2,
                    "hero_equity_vs_random": 0.5,
                    "hero_equity_vs_continuing": 0.4,
                    "opponents": [],
                }
            )
        )
    path = tmp_path / "wide" / "hands.jsonl"
    _write(path, [{"seed": 1, "hand_number": 3, "stacks": [2000, 2000, 2000, 2000], "actions": actions}])
    text = write_report(path, reports_dir=tmp_path / "reports").read_text(encoding="utf-8")
    spots = text.split("## Disagreement spots", 1)[1]
    assert spots.count("### Hand") == 8
    assert "Pot: 90" in spots
    assert spots.index("Pot: 90") < spots.index("Pot: 80")
    assert "Pot: 10\n" not in spots
