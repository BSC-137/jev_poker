"""Hand-flow tests for the 4-handed play-money engine."""

from jev_poker.engine.actions import Action
from jev_poker.engine.cards import standard_deck
from jev_poker.engine.game import Game
from treys import Card, Evaluator

import pytest


def stacks(game: Game) -> list[int]:
    return [player["stack"] for player in game.public_state()["players"]]


def with_prefix(prefix: list[str]) -> list[str]:
    if len(prefix) != len(set(prefix)):
        raise AssertionError("duplicate card in scripted deck")
    rest = [card for card in standard_deck() if card not in set(prefix)]
    deck = prefix + rest
    assert len(deck) == 52
    return deck


def call_down(game: Game) -> None:
    board_len = {"preflop": 0, "flop": 3, "turn": 4, "river": 5}
    for _ in range(40):
        if game.is_hand_over():
            return
        state = game.public_state()
        assert len(state["board"]) == board_len[state["street"]]
        seat = state["to_act"]
        actions = game.legal_actions(seat)
        if Action.CHECK in actions:
            game.apply(seat, Action.CHECK)
        elif Action.CALL in actions:
            game.apply(seat, Action.CALL)
        else:
            raise AssertionError(f"no passive action for seat {seat}: {actions}")
    raise AssertionError("hand did not finish")


def test_blinds_posted_and_button_rotates():
    game = Game(seed=0)
    game.new_hand()
    state = game.public_state()
    assert state["button"] == 0
    assert state["pot"] == 30
    assert state["to_act"] == 3
    players = state["players"]
    assert [player["position"] for player in players] == ["BTN", "SB", "BB", "UTG"]
    assert players[1]["street_commit"] == 10
    assert players[1]["stack"] == 1990
    assert players[2]["street_commit"] == 20
    assert players[2]["stack"] == 1980
    assert players[0]["street_commit"] == 0
    assert players[3]["street_commit"] == 0

    game.apply(3, Action.FOLD)
    game.apply(0, Action.FOLD)
    game.apply(1, Action.FOLD)
    assert game.is_hand_over()
    assert stacks(game) == [2000, 1990, 2010, 2000]

    game.new_hand()
    state = game.public_state()
    assert state["button"] == 1
    assert state["to_act"] == 0
    players = state["players"]
    assert [player["position"] for player in players] == ["UTG", "BTN", "SB", "BB"]
    assert players[2]["street_commit"] == 10
    assert players[2]["stack"] == 2000
    assert players[3]["street_commit"] == 20
    assert players[3]["stack"] == 1980
    assert players[1]["stack"] == 1990
    assert players[1]["street_commit"] == 0


def test_short_blind_posts_remainder_all_in():
    game = Game(stacks=[2000, 5, 2000, 2000], seed=0)
    game.new_hand()
    sb = game.public_state()["players"][1]
    assert sb["position"] == "SB"
    assert sb["street_commit"] == 5
    assert sb["stack"] == 0
    assert sb["all_in"] is True
    assert game.public_state()["current_bet"] == 20
    assert game.public_state()["pot"] == 25


def test_check_illegal_facing_a_bet_and_fold_illegal_when_to_call_is_zero():
    game = Game(seed=1)
    game.new_hand()
    utg = game.legal_actions(3)
    assert Action.CHECK not in utg
    assert Action.FOLD in utg
    assert game.public_state()["players"][3]["to_call"] == 20
    with pytest.raises(ValueError):
        game.apply(3, Action.CHECK)

    game.apply(3, Action.CALL)
    game.apply(0, Action.CALL)
    game.apply(1, Action.CALL)
    bb = game.legal_actions(2)
    assert Action.CHECK in bb
    assert Action.FOLD not in bb
    assert game.public_state()["players"][2]["to_call"] == 0
    with pytest.raises(ValueError):
        game.apply(2, Action.FOLD)


def test_full_hand_dealt_to_showdown_with_scripted_calls():
    game = Game(seed=42)
    game.new_hand()
    call_down(game)
    assert game.is_hand_over()
    state = game.public_state()
    assert state["street"] == "showdown"
    assert len(state["board"]) == 5
    assert "hole_cards" not in state
    assert all("hole_cards" not in player for player in state["players"])
    holes = [game.private_state(seat)["hole_cards"] for seat in range(4)]
    assert all(len(hole) == 2 for hole in holes)
    assert len({tuple(hole) for hole in holes}) == 4

    evaluator = Evaluator()
    board = [Card.new(card) for card in state["board"]]
    scores = {
        seat: evaluator.evaluate([Card.new(card) for card in holes[seat]], board)
        for seat in range(4)
    }
    best = min(scores.values())
    won = game.winners()
    assert {item["seat"] for item in won} == {seat for seat, score in scores.items() if score == best}
    assert sum(item["amount"] for item in won) == 80
    assert sum(stacks(game)) == 8000


def test_short_all_in_side_pot_returns_uncovered_chips():
    # UTG is dealt aces and is all-in for 80. BTN is dealt kings and raises to 190.
    # The 110 that UTG cannot cover returns to BTN. UTG wins only the main pot.
    deck = with_prefix(
        [
            "2c", "4c", "Ah", "Kd",
            "3c", "5c", "As", "Ks",
            "Tc",
            "2h", "3d", "7c",
            "Jc",
            "8d",
            "Qc",
            "9s",
        ]
    )
    game = Game(stacks=[2000, 2000, 2000, 80], deck=deck)
    game.new_hand()
    assert game.private_state(3)["hole_cards"] == ["Ah", "As"]
    assert game.private_state(0)["hole_cards"] == ["Kd", "Ks"]
    assert game.public_state()["to_act"] == 3

    game.apply(3, Action.ALL_IN)
    game.apply(0, Action.RAISE_POT)
    assert game.public_state()["players"][0]["street_commit"] == 190
    game.apply(1, Action.FOLD)
    game.apply(2, Action.FOLD)

    assert game.is_hand_over()
    state = game.public_state()
    assert state["street"] == "showdown"
    assert state["board"] == ["2h", "3d", "7c", "8d", "9s"]
    assert game.winners() == [
        {"seat": 0, "amount": 110},
        {"seat": 3, "amount": 190},
    ]
    assert stacks(game) == [1920, 1990, 1980, 190]


def test_exact_tie_splits_pot():
    # Board is a royal flush, so the three live players tie.
    # Pot 70 splits 23 each, and the 1-chip remainder goes to the BB,
    # the first winner left of the button. SB folded and wins nothing.
    deck = with_prefix(
        [
            "2c", "3c", "4c", "5c",
            "6c", "7c", "8c", "9c",
            "Tc",
            "Ah", "Kh", "Qh",
            "Jc",
            "Jh",
            "Qc",
            "Th",
        ]
    )
    game = Game(deck=deck, seed=0)
    game.new_hand()
    game.apply(3, Action.CALL)
    game.apply(0, Action.CALL)
    game.apply(1, Action.FOLD)
    game.apply(2, Action.CHECK)
    for _ in range(3):
        for _ in range(3):
            seat = game.public_state()["to_act"]
            assert Action.CHECK in game.legal_actions(seat)
            game.apply(seat, Action.CHECK)

    assert game.is_hand_over()
    assert game.public_state()["street"] == "showdown"
    assert game.public_state()["board"] == ["Ah", "Kh", "Qh", "Jh", "Th"]
    assert game.winners() == [
        {"seat": 0, "amount": 23},
        {"seat": 2, "amount": 24},
        {"seat": 3, "amount": 23},
    ]
    assert stacks(game) == [2003, 1990, 2004, 2003]


def test_raise_sizing_clamps_to_min_raise_or_stack():
    game = Game(seed=0)
    game.new_hand()
    game.apply(3, Action.RAISE_HALF_POT)
    assert game.public_state()["players"][3]["street_commit"] == 40

    pot_game = Game(seed=0)
    pot_game.new_hand()
    pot_game.apply(3, Action.RAISE_POT)
    assert pot_game.public_state()["players"][3]["street_commit"] == 50
    assert pot_game.public_state()["min_raise"] == 30

    short = Game(stacks=[2000, 2000, 2000, 25], seed=0)
    short.new_hand()
    short.apply(3, Action.RAISE_POT)
    state = short.public_state()
    assert state["players"][3]["all_in"] is True
    assert state["players"][3]["street_commit"] == 25
    assert state["players"][3]["stack"] == 0
    assert state["current_bet"] == 25
    assert state["min_raise"] == 20
    assert Action.RAISE_POT in short.legal_actions(0)


def test_tiny_all_in_does_not_reopen_action():
    game = Game(stacks=[2000, 2000, 2000, 25], seed=1)
    game.new_hand()
    assert game.public_state()["to_act"] == 3
    game.apply(3, Action.CALL)
    game.apply(0, Action.CALL)
    game.apply(1, Action.CALL)
    game.apply(2, Action.CHECK)
    assert game.public_state()["street"] == "flop"
    assert game.public_state()["players"][3]["stack"] == 5

    assert game.public_state()["to_act"] == 1
    game.apply(1, Action.CHECK)
    game.apply(2, Action.CHECK)
    assert Action.ALL_IN in game.legal_actions(3)
    game.apply(3, Action.ALL_IN)

    state = game.public_state()
    assert state["to_act"] == 0
    assert state["current_bet"] == 5
    assert state["min_raise"] == 20
    assert Action.RAISE_POT in game.legal_actions(0)
    assert Action.RAISE_HALF_POT in game.legal_actions(0)
    game.apply(0, Action.CALL)

    assert game.public_state()["to_act"] == 1
    assert set(game.legal_actions(1)) == {Action.FOLD, Action.CALL}


def test_uncontested_pot_when_everyone_else_folds():
    game = Game(seed=0)
    game.new_hand()
    game.apply(3, Action.FOLD)
    game.apply(0, Action.FOLD)
    game.apply(1, Action.FOLD)
    assert game.is_hand_over()
    state = game.public_state()
    assert state["street"] == "preflop"
    assert state["board"] == []
    assert game.winners() == [{"seat": 2, "amount": 30}]
    assert stacks(game) == [2000, 1990, 2010, 2000]
    assert sum(stacks(game)) == 8000


def test_seeded_shuffle_is_deterministic():
    def holes(seed: int) -> list[tuple[str, str]]:
        game = Game(seed=seed)
        game.new_hand()
        return [tuple(game.private_state(seat)["hole_cards"]) for seat in range(4)]

    assert holes(123) == holes(123)
    assert holes(123) != holes(99)
