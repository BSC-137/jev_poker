"""Offline preflop strength order for the 169 hand classes.

Generated once, not at runtime. Each class used one representative combo
and 5,000 runouts against a random hand (seed ``jev-preflop-<class>``,
ties count as half a win). Classes are sorted from strongest to weakest.

AA is first. 72o is in the bottom group. This sample's weakest class is
42o, just below 32o. The order is a strength ranking, not a GTO range.
"""

from __future__ import annotations

from jev_poker.engine.cards import RANKS

PREFLOP_CLASS_ORDER: tuple[str, ...] = (
    'AA', 'KK', 'QQ', 'JJ', 'TT', '99', '88', 'AKs',
    '77', 'AQs', 'AJs', 'AKo', 'AJo', 'AQo', 'ATs', 'KQs',
    '66', 'A8s', 'KJs', 'KTs', 'KQo', 'ATo', 'QJs', 'A9s',
    'A7s', 'A9o', 'KJo', 'K8s', '55', 'A5s', 'A6s', 'QTs',
    'KTo', 'A4s', 'A7o', 'A8o', 'QTo', 'K9s', 'Q9s', 'A6o',
    'Q8s', 'A3s', 'K6s', 'A5o', 'QJo', 'JTs', '44', 'A2s',
    'K7s', 'A3o', 'K9o', 'J9s', 'K8o', 'A4o', 'K7o', 'K5s',
    'JTo', 'K6o', 'Q9o', 'A2o', 'K4s', 'K3s', 'Q8o', 'Q7s',
    'J8s', 'K4o', 'T9s', '33', 'Q5s', 'T8s', 'J9o', 'Q6s',
    'Q7o', 'K2s', 'K5o', '98s', 'Q4s', 'J7s', 'J8o', 'K3o',
    'T7s', 'Q6o', 'J7o', '22', 'T9o', 'Q2s', 'Q3s', 'K2o',
    'Q5o', '97s', 'Q4o', 'J4s', 'J6s', 'J5s', 'J3s', 'T6s',
    'T8o', '87s', 'J6o', '98o', 'Q3o', 'T7o', 'T5s', 'J2s',
    '97o', '95s', 'J5o', '96s', 'T4s', 'Q2o', '76s', '86s',
    'T3s', 'J4o', 'J2o', 'J3o', 'T6o', '87o', 'T2s', 'T5o',
    '94s', '85s', '75s', '96o', '93s', '95o', '92s', 'T2o',
    '86o', '54s', '65s', 'T3o', 'T4o', '74s', '84s', '76o',
    '75o', '65o', '83s', '73s', '94o', '85o', '82s', '93o',
    '84o', '64s', '53s', '54o', '52s', '62s', '74o', '43s',
    '63s', '64o', '42s', '72s', '92o', '63o', '32s', '83o',
    '82o', '53o', '73o', '72o', '43o', '52o', '62o', '32o',
    '42o',
)

PREFLOP_RANK: dict[str, int] = {name: index for index, name in enumerate(PREFLOP_CLASS_ORDER)}

if len(PREFLOP_CLASS_ORDER) != 169 or len(set(PREFLOP_CLASS_ORDER)) != 169:
    raise RuntimeError("preflop class order must contain 169 unique classes")


def hand_class(card_a: str, card_b: str) -> str:
    rank_a, suit_a = card_a[0], card_a[1]
    rank_b, suit_b = card_b[0], card_b[1]
    if RANKS.index(rank_a) < RANKS.index(rank_b):
        rank_a, rank_b = rank_b, rank_a
        suit_a, suit_b = suit_b, suit_a
    if rank_a == rank_b:
        return rank_a + rank_b
    return rank_a + rank_b + ("s" if suit_a == suit_b else "o")
