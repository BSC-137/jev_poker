"""Per-seat stats from completed betting decisions.

An empty history leaves every rate null. A measured zero, such as folding
every time a bet was faced, is a real sample and is returned as 0.0.
"""

from __future__ import annotations

_VOLUNTARY = {"call", "raise_half_pot", "raise_pot", "all_in"}
_NAMED_RAISES = {"raise_half_pot", "raise_pot"}


def stats_by_seat(history: list[dict]) -> list[dict]:
    """One stats dict per seat, in seat order, from an action log."""
    tracker = TableStats()
    for event in history:
        tracker.observe(event)
    return [tracker.for_seat(seat) for seat in range(4)]


class TableStats:
    def __init__(self) -> None:
        self._preflop_hands: list[set[int]] = [set() for _ in range(4)]
        self._vpip_hands: list[set[int]] = [set() for _ in range(4)]
        self._pfr_hands: list[set[int]] = [set() for _ in range(4)]
        self._faced = [0, 0, 0, 0]
        self._folds = [0, 0, 0, 0]
        self._aggressive = [0, 0, 0, 0]
        self._calls = [0, 0, 0, 0]

    def observe(self, event: dict) -> None:
        seat = event["seat"]
        action = event["action"]
        amount = event["amount"]
        to_call = event["to_call"]
        hand_id = event["hand_id"]
        faced_bet = bool(event["faced_bet"])
        raised = _is_raise(action, amount, to_call)
        called = _is_call(action, amount, to_call)
        if event["street"] == "preflop":
            self._preflop_hands[seat].add(hand_id)
            if action in _VOLUNTARY:
                self._vpip_hands[seat].add(hand_id)
            if raised:
                self._pfr_hands[seat].add(hand_id)
        if faced_bet:
            self._faced[seat] += 1
            if action == "fold":
                self._folds[seat] += 1
        if raised:
            self._aggressive[seat] += 1
        elif called:
            self._calls[seat] += 1

    def for_seat(self, seat: int) -> dict:
        hands = len(self._preflop_hands[seat])
        calls = self._calls[seat]
        return {
            "vpip": None if hands == 0 else len(self._vpip_hands[seat]) / hands,
            "pfr": None if hands == 0 else len(self._pfr_hands[seat]) / hands,
            "fold_to_bet": None if self._faced[seat] == 0 else self._folds[seat] / self._faced[seat],
            "aggression_factor": None if calls == 0 else self._aggressive[seat] / calls,
        }


def _is_raise(action: str, amount: int, to_call: int) -> bool:
    if action in _NAMED_RAISES:
        return True
    return action == "all_in" and amount > to_call


def _is_call(action: str, amount: int, to_call: int) -> bool:
    if action == "call":
        return True
    return action == "all_in" and amount <= to_call
