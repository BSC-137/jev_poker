"""Decision-state, texture, and running-stat checks."""

import json
import random

from jev_poker.engine.actions import Action
from jev_poker.engine.game import Game
from jev_poker.math.state import decision_state
from jev_poker.math.stats import stats_by_seat
from jev_poker.math.texture import board_texture


def test_pot_odds_legal_actions_and_hidden_opponent_holes():
    game = Game(seed=7)
    game.new_hand()
    game.apply(3, Action.RAISE_POT)

    hero = 0
    state = decision_state(game, hero, iterations=30, rng=random.Random(0))
    public = game.public_state()
    hero_row = public["players"][hero]
    to_call = hero_row["to_call"]
    pot = public["pot"]

    assert state["street"] == "preflop"
    assert state["pot"] == pot == 80
    assert state["to_call"] == to_call == 50
    assert state["pot_odds"] == to_call / (pot + to_call)
    assert state["spr"] == hero_row["stack"] / pot
    assert state["legal_actions"] == [action.value for action in game.legal_actions(hero)]
    assert state["legal_actions"] == [
        "fold",
        "call",
        "raise_half_pot",
        "raise_pot",
        "all_in",
    ]
    assert Action.CHECK.value not in state["legal_actions"]
    assert state["hero"]["hole_cards"] == game.private_state(hero)["hole_cards"]
    assert state["hero"]["committed_this_street"] == 0
    assert state["continuing_fraction"] == 0.4
    assert state["action_history"] == [
        {
            "street": "preflop",
            "seat": 3,
            "position": "UTG",
            "action": "raise_pot",
            "amount": 50,
        }
    ]
    assert 0.0 <= state["hero_equity_vs_random"] <= 1.0
    assert 0.0 <= state["hero_equity_vs_continuing"] <= 1.0

    encoded = json.dumps(state)
    for seat, player in enumerate(game.players):
        if seat == hero:
            continue
        for card in player.hole:
            assert card not in encoded
    for opponent in state["opponents"]:
        assert "hole_cards" not in opponent
        assert "hole" not in opponent
    assert "hole_cards" not in state
    assert state["hero"]["hole_cards"]


def test_empty_history_stats_are_null_not_zero():
    empty = stats_by_seat([])
    assert empty[0] == {
        "vpip": None,
        "pfr": None,
        "fold_to_bet": None,
        "aggression_factor": None,
    }
    game = Game(seed=1)
    game.new_hand()
    state = decision_state(game, 3, iterations=5, rng=random.Random(2))
    assert state["action_history"] == []
    assert state["pot_odds"] == 20 / 50
    assert all(opponent["stats"]["vpip"] is None for opponent in state["opponents"])
    assert all(opponent["stats"]["aggression_factor"] is None for opponent in state["opponents"])


def test_stats_use_completed_decisions_across_hands():
    game = Game(seed=1)
    game.new_hand()
    game.apply(3, Action.FOLD)
    game.apply(0, Action.FOLD)
    game.apply(1, Action.FOLD)
    assert game.is_hand_over()
    folded = stats_by_seat(game.action_log)[3]
    assert folded["vpip"] == 0.0
    assert folded["pfr"] == 0.0
    assert folded["fold_to_bet"] == 1.0
    assert folded["aggression_factor"] is None

    game.new_hand()
    state = decision_state(game, 0, iterations=5, rng=random.Random(3))
    assert state["action_history"] == []
    previous = next(opponent for opponent in state["opponents"] if opponent["seat"] == 3)
    assert previous["stats"]["fold_to_bet"] == 1.0
    assert previous["stats"]["vpip"] == 0.0


def test_board_texture_features():
    assert board_texture([]) == {
        "paired": False,
        "monotone": False,
        "two_tone": False,
        "connectedness": 0,
        "high_card": None,
    }
    disconnected = board_texture(["Qs", "7c", "2d"])
    assert disconnected["paired"] is False
    assert disconnected["monotone"] is False
    assert disconnected["two_tone"] is False
    assert disconnected["connectedness"] == 0
    assert disconnected["high_card"] == "Q"
    monotone = board_texture(["Jh", "Th", "9h"])
    assert monotone["monotone"] is True
    assert monotone["two_tone"] is False
    assert monotone["connectedness"] == 1
    assert monotone["high_card"] == "J"
    paired = board_texture(["Ah", "Ad", "Kd"])
    assert paired["paired"] is True
    assert paired["two_tone"] is True
    assert paired["monotone"] is False
    assert paired["connectedness"] == 1
    assert paired["high_card"] == "A"
    straight_draw = board_texture(["Jh", "Th", "9c", "8d"])
    assert straight_draw["connectedness"] == 2
    assert straight_draw["two_tone"] is False
    assert straight_draw["monotone"] is False
