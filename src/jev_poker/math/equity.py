"""Monte Carlo hold'em equity.

``equity_vs_top_fraction`` keeps only the strongest remaining hole-card
combos. On a dealt board those combos are ranked with treys (lower score
is better). Preflop, treys cannot score two cards, so classes are ranked
by the checked-in 169-hand order. That filter is a strength screen, not
a GTO range: it does not model position, stack depth, or balanced strategy.
"""

from __future__ import annotations

import math
import random

from jev_poker.engine.cards import standard_deck, is_card
from jev_poker.engine.evaluator import HandEvaluator
from jev_poker.math.preflop_order import PREFLOP_RANK, hand_class

_EVALUATOR = HandEvaluator()


def monte_carlo_equity(
    hero_cards: list[str],
    board: list[str] | None = None,
    opponent_count: int = 1,
    dead_cards: list[str] | None = None,
    iterations: int = 300,
    rng: random.Random | None = None,
) -> float:
    """Equity of ``hero_cards`` against ``opponent_count`` uniformly dealt hands.

    Known cards (hero, board, and ``dead_cards``) are removed from the deck.
    Each iteration deals every opponent two cards and completes the board to
    five cards. Ties split the pot. The result is in ``[0, 1]``.
    """
    hero, board_cards, deck = _known_deck(hero_cards, board, dead_cards)
    if iterations < 1:
        raise ValueError("iterations must be positive")
    if opponent_count < 0:
        raise ValueError("opponent_count cannot be negative")
    if opponent_count == 0:
        return 1.0
    needed = 2 * opponent_count + (5 - len(board_cards))
    if needed > len(deck):
        raise ValueError("not enough cards left to deal")
    source = rng if rng is not None else random.Random()
    share = 0.0
    for _ in range(iterations):
        draw = source.sample(deck, needed)
        holes = [draw[index * 2 : index * 2 + 2] for index in range(opponent_count)]
        run_board = board_cards + draw[2 * opponent_count :]
        share += _pot_share(hero, holes, run_board)
    return share / iterations


def equity_vs_top_fraction(
    hero_cards: list[str],
    board: list[str] | None = None,
    fraction: float = 0.4,
    dead_cards: list[str] | None = None,
    iterations: int = 300,
    rng: random.Random | None = None,
    opponent_count: int = 1,
) -> float:
    """Equity when every opponent holds a combo in the top ``fraction`` by strength.

    This is a strength filter, not a GTO range. Preflop strength is the
    checked-in class order from AA downward. Later streets use the current
    treys score of each combo on the board. Combos tied with the cutoff are
    kept, so the kept set can be slightly larger than ``fraction``.
    """
    if not 0 < fraction <= 1:
        raise ValueError("fraction must be in (0, 1]")
    hero, board_cards, _deck = _known_deck(hero_cards, board, dead_cards)
    if board_cards and len(board_cards) not in (3, 4, 5):
        raise ValueError("strength filter needs an empty board or 3 to 5 cards")
    if iterations < 1:
        raise ValueError("iterations must be positive")
    if opponent_count < 0:
        raise ValueError("opponent_count cannot be negative")
    if opponent_count == 0:
        return 1.0
    combos = _remaining_combos(hero, board_cards, dead_cards)
    if not combos:
        raise ValueError("no opponent combos remain")
    ranked = _top_combos(combos, board_cards, fraction)
    source = rng if rng is not None else random.Random()
    return _equity_from_combos(hero, board_cards, ranked, opponent_count, iterations, source)


def _known_deck(
    hero_cards: list[str],
    board: list[str] | None,
    dead_cards: list[str] | None,
) -> tuple[list[str], list[str], list[str]]:
    hero = list(hero_cards)
    board_cards = list(board or [])
    dead = list(dead_cards or [])
    if len(hero) != 2:
        raise ValueError("hero must have two cards")
    if len(board_cards) > 5:
        raise ValueError("board cannot have more than five cards")
    known = hero + board_cards + dead
    if len(known) != len(set(known)) or any(not is_card(card) for card in known):
        raise ValueError("cards must be unique and valid")
    blocked = set(known)
    deck = [card for card in standard_deck() if card not in blocked]
    return hero, board_cards, deck


def _remaining_combos(
    hero: list[str],
    board: list[str],
    dead_cards: list[str] | None,
) -> list[tuple[str, str]]:
    blocked = set(hero) | set(board) | set(dead_cards or [])
    deck = [card for card in standard_deck() if card not in blocked]
    return [(deck[index], deck[later]) for index in range(len(deck)) for later in range(index + 1, len(deck))]


def _top_combos(
    combos: list[tuple[str, str]],
    board: list[str],
    fraction: float,
) -> list[tuple[str, str]]:
    if board:
        strength = {
            combo: _EVALUATOR.score_best(list(combo), board)
            for combo in combos
        }
    else:
        strength = {combo: PREFLOP_RANK[hand_class(*combo)] for combo in combos}
    ordered = sorted(combos, key=strength.__getitem__)
    cutoff_index = max(1, math.ceil(fraction * len(ordered))) - 1
    cutoff = strength[ordered[cutoff_index]]
    return [combo for combo in ordered if strength[combo] <= cutoff]


def _equity_from_combos(
    hero: list[str],
    board: list[str],
    combos: list[tuple[str, str]],
    opponent_count: int,
    iterations: int,
    rng: random.Random,
) -> float:
    board_needed = 5 - len(board)
    blocked = set(hero) | set(board)
    deck = [card for card in standard_deck() if card not in blocked]
    share = 0.0
    filled = 0
    attempts = 0
    while filled < iterations and attempts < iterations * 30:
        attempts += 1
        available = set(deck)
        holes: list[list[str]] = []
        failed = False
        for _ in range(opponent_count):
            legal = [combo for combo in combos if combo[0] in available and combo[1] in available]
            if not legal:
                failed = True
                break
            chosen = legal[rng.randrange(len(legal))]
            holes.append([chosen[0], chosen[1]])
            available.remove(chosen[0])
            available.remove(chosen[1])
        if failed:
            continue
        run_board = list(board)
        if board_needed:
            run_board.extend(rng.sample(list(available), board_needed))
        share += _pot_share(hero, holes, run_board)
        filled += 1
    if filled == 0:
        raise RuntimeError("could not sample continuing hands")
    return share / filled


def _pot_share(hero: list[str], holes: list[list[str]], board: list[str]) -> float:
    hero_score = _EVALUATOR.score_best(hero, board)
    opponent_scores = [_EVALUATOR.score_best(hole, board) for hole in holes]
    best = min(opponent_scores)
    if hero_score < best:
        return 1.0
    if hero_score > best:
        return 0.0
    tied = 1 + sum(score == hero_score for score in opponent_scores)
    return 1.0 / tied
