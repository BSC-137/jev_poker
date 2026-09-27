"""52-card deck. Card text matches treys: rank then suit, ten is T."""

from __future__ import annotations

RANKS = "23456789TJQKA"
SUITS = "cdhs"


def is_card(card: str) -> bool:
    return len(card) == 2 and card[0] in RANKS and card[1] in SUITS


def standard_deck() -> list[str]:
    return [f"{rank}{suit}" for rank in RANKS for suit in SUITS]


def validate_deck(cards: list[str]) -> list[str]:
    if len(cards) != 52 or len(set(cards)) != 52:
        raise ValueError("deck must contain 52 unique cards")
    invalid = [card for card in cards if not is_card(card)]
    if invalid:
        raise ValueError(f"invalid cards: {invalid}")
    return list(cards)


class Deck:
    """Draws from the front of a shuffled or caller-supplied card list."""

    def __init__(self, cards: list[str]) -> None:
        self._cards = validate_deck(cards)
        self._index = 0

    def draw(self, n: int = 1) -> list[str]:
        end = self._index + n
        if n < 1 or end > len(self._cards):
            raise RuntimeError("deck underrun")
        drawn = self._cards[self._index:end]
        self._index = end
        return drawn
