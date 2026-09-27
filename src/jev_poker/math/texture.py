"""Board texture from the cards already dealt.

Connectedness is the count of two independent features, so it is 0, 1, or 2:

- a straight can be completed by exactly one missing rank
- two board ranks are at most four apart

Ace is high for the high card. The wheel (A-5) is included when checking
whether one card completes a straight.
"""

from __future__ import annotations

from jev_poker.engine.cards import RANKS, is_card

_RANK_INDEX = {rank: index for index, rank in enumerate(RANKS)}
_STRAIGHT_WINDOWS = [set(range(start, start + 5)) for start in range(9)]
_STRAIGHT_WINDOWS.append({12, 0, 1, 2, 3})


def board_texture(board: list[str]) -> dict:
    if len(board) != len(set(board)) or any(not is_card(card) for card in board):
        raise ValueError("board must be unique cards")
    rank_indexes = [_RANK_INDEX[card[0]] for card in board]
    suits = [card[1] for card in board]
    distinct_suits = len(set(suits))
    unique_ranks = set(rank_indexes)
    paired = len(unique_ranks) < len(rank_indexes)
    return {
        "paired": paired,
        "monotone": len(board) >= 3 and distinct_suits == 1,
        "two_tone": len(board) >= 2 and distinct_suits == 2,
        "connectedness": int(_straight_with_one_card(unique_ranks)) + int(_within_four(unique_ranks)),
        "high_card": None if not rank_indexes else RANKS[max(rank_indexes)],
    }


def _straight_with_one_card(ranks: set[int]) -> bool:
    for window in _STRAIGHT_WINDOWS:
        missing = window - ranks
        if len(missing) == 1 and len(window & ranks) == 4:
            return True
    return False


def _within_four(ranks: set[int]) -> bool:
    ordered = sorted(ranks)
    for index, left in enumerate(ordered):
        for right in ordered[index + 1 :]:
            if right - left <= 4:
                return True
    return False
