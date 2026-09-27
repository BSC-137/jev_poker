"""JSON-ready view of one hero decision. Opponent hole cards are omitted."""

from __future__ import annotations

import random

from jev_poker.engine.game import Game
from jev_poker.math.equity import equity_vs_top_fraction, monte_carlo_equity
from jev_poker.math.stats import stats_by_seat
from jev_poker.math.texture import board_texture

_HISTORY_KEYS = ("street", "seat", "position", "action", "amount")


def decision_state(
    game: Game,
    hero_seat: int,
    *,
    continuing_fraction: float = 0.4,
    iterations: int = 300,
    rng: random.Random | None = None,
) -> dict:
    """Build the object a later decision model will read.

    ``hero_equity_vs_continuing`` uses ``continuing_fraction`` as a strength
    filter, not a GTO range. Equity does not see other players' hole cards.
    """
    public = game.public_state()
    hero_row = public["players"][hero_seat]
    hole_cards = list(game.private_state(hero_seat)["hole_cards"])
    board = list(public["board"])
    pot = public["pot"]
    to_call = hero_row["to_call"]
    live_opponents = sum(
        1
        for player in public["players"]
        if player["seat"] != hero_seat and player["in_hand"] and not player["folded"]
    )
    source = rng if rng is not None else random.Random()
    if live_opponents == 0:
        versus_random = 1.0
        versus_continuing = 1.0
    else:
        versus_random = monte_carlo_equity(
            hole_cards,
            board,
            live_opponents,
            iterations=iterations,
            rng=source,
        )
        versus_continuing = equity_vs_top_fraction(
            hole_cards,
            board,
            continuing_fraction,
            iterations=iterations,
            rng=source,
            opponent_count=live_opponents,
        )
    seat_stats = stats_by_seat(game.action_log)
    return {
        "street": public["street"],
        "hero": {
            "seat": hero_seat,
            "position": hero_row["position"],
            "hole_cards": hole_cards,
            "stack": hero_row["stack"],
            "committed_this_street": hero_row["street_commit"],
        },
        "board": board,
        "pot": pot,
        "to_call": to_call,
        "pot_odds": 0.0 if to_call == 0 else to_call / (pot + to_call),
        "spr": None if pot <= 0 else hero_row["stack"] / pot,
        "hero_equity_vs_random": versus_random,
        "hero_equity_vs_continuing": versus_continuing,
        "continuing_fraction": continuing_fraction,
        "board_texture": board_texture(board),
        "legal_actions": [action.value for action in game.legal_actions(hero_seat)],
        "action_history": _current_history(game),
        "opponents": [
            {
                "seat": player["seat"],
                "position": player["position"],
                "stack": player["stack"],
                "in_hand": player["in_hand"] and not player["folded"],
                "stats": seat_stats[player["seat"]],
            }
            for player in public["players"]
            if player["seat"] != hero_seat
        ],
    }


def _current_history(game: Game) -> list[dict]:
    return [
        {key: event[key] for key in _HISTORY_KEYS}
        for event in game.action_log
        if event["hand_id"] == game.hand_number
    ]
