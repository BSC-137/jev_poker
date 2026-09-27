"""7-card hand scoring. A lower treys score is a better hand."""

from __future__ import annotations

from treys import Card
from treys import Evaluator

_EVALUATOR: Evaluator | None = None


class HandEvaluator:
    def __init__(self) -> None:
        self._evaluator = self._shared()

    @staticmethod
    def _shared() -> Evaluator:
        global _EVALUATOR
        if _EVALUATOR is None:
            _EVALUATOR = Evaluator()
        return _EVALUATOR

    def score(self, hole: list[str], board: list[str]) -> int:
        if len(hole) != 2 or len(board) != 5:
            raise ValueError("score expects 2 hole cards and 5 board cards")
        return self.score_best(hole, board)

    def score_best(self, hole: list[str], board: list[str]) -> int:
        """Best treys score for a 3, 4, or 5 card board. Lower is better."""
        if len(hole) != 2 or len(board) not in (3, 4, 5):
            raise ValueError("score_best expects 2 hole cards and a 3, 4, or 5 card board")
        return int(
            self._evaluator.evaluate(
                [Card.new(card) for card in hole],
                [Card.new(card) for card in board],
            )
        )
