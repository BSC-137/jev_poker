"""Monte Carlo equity and the checked-in preflop order."""

import random

from jev_poker.engine.cards import RANKS
from jev_poker.math.equity import monte_carlo_equity
from jev_poker.math.preflop_order import PREFLOP_CLASS_ORDER


class _RecordingRandom(random.Random):
    def __init__(self, seed: int) -> None:
        super().__init__(seed)
        self.picks: list[tuple[list[str], list[str]]] = []

    def sample(self, population, k):
        pool = list(population)
        picked = super().sample(pool, k)
        self.picks.append((pool, list(picked)))
        return picked


def test_aces_versus_one_random_opponent_are_strong():
    equity = monte_carlo_equity(
        ["Ah", "As"],
        [],
        opponent_count=1,
        iterations=400,
        rng=random.Random(1),
    )
    assert 0.0 <= equity <= 1.0
    assert equity > 0.80


def test_seven_two_offsuit_versus_one_random_opponent_is_weak():
    equity = monte_carlo_equity(
        ["7c", "2d"],
        [],
        opponent_count=1,
        iterations=400,
        rng=random.Random(1),
    )
    assert equity < 0.40


def test_known_board_cards_are_never_dealt_again():
    recorder = _RecordingRandom(5)
    hero = ["Kd", "Kc"]
    board = ["Qs", "7c", "2d"]
    dead = ["Ah"]
    monte_carlo_equity(
        hero,
        board,
        opponent_count=1,
        dead_cards=dead,
        iterations=25,
        rng=recorder,
    )
    banned = set(hero) | set(board) | set(dead)
    assert len(recorder.picks) == 25
    for population, picked in recorder.picks:
        assert banned.isdisjoint(population)
        assert banned.isdisjoint(picked)
        assert len(picked) == len(set(picked))


def test_same_seed_repeats_equity():
    kwargs = {
        "hero_cards": ["Ah", "Kd"],
        "board": ["Qs", "7c", "2d"],
        "opponent_count": 1,
        "iterations": 40,
    }
    first = monte_carlo_equity(**kwargs, rng=random.Random(11))
    second = monte_carlo_equity(**kwargs, rng=random.Random(11))
    assert first == second


def test_preflop_order_runs_from_aces_through_the_weakest_class():
    assert len(PREFLOP_CLASS_ORDER) == 169
    assert len(set(PREFLOP_CLASS_ORDER)) == 169
    assert PREFLOP_CLASS_ORDER[0] == "AA"
    assert PREFLOP_CLASS_ORDER[-1] == "42o"
    assert "72o" in PREFLOP_CLASS_ORDER[-8:]
    expected = {rank * 2 for rank in RANKS}
    for index, high in enumerate(RANKS):
        for low in RANKS[:index]:
            expected.add(high + low + "s")
            expected.add(high + low + "o")
    assert set(PREFLOP_CLASS_ORDER) == expected
