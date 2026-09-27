"""Four-handed no-limit hold'em hand flow, betting, and pot award."""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass, field

from jev_poker.engine.actions import Action
from jev_poker.engine.cards import Deck, standard_deck, validate_deck
from jev_poker.engine.evaluator import HandEvaluator

SEATS = 4
STARTING_STACK = 2000
SMALL_BLIND = 10
BIG_BLIND = 20
_POSITIONS = ("BTN", "SB", "BB", "UTG")


@dataclass
class Player:
    seat: int
    stack: int
    hole: list[str] = field(default_factory=list)
    folded: bool = False
    all_in: bool = False
    street_commit: int = 0
    total_commit: int = 0
    acted: bool = False
    can_raise: bool = True
    in_hand: bool = True


class Game:
    """One table of four seats playing successive play-money hands.

    ``raise_half_pot`` and ``raise_pot`` raise to
    ``current street bet + pot // 2`` or ``current street bet + pot``,
    using the pot before the raise. Targets below the minimum raise-to
    are clamped up. Targets above the player's stack become an all-in.
    An all-in smaller than a full raise does not reopen raising for
    players who have already acted.
    """

    def __init__(
        self,
        stacks: list[int] | None = None,
        seed: int | None = None,
        deck: list[str] | None = None,
    ) -> None:
        if stacks is None:
            stacks = [STARTING_STACK] * SEATS
        if len(stacks) != SEATS or any(type(stack) is not int or stack < 0 for stack in stacks):
            raise ValueError("stacks must be four non-negative integers")
        self.players = [Player(seat=seat, stack=stacks[seat]) for seat in range(SEATS)]
        self._rng = random.Random(seed)
        self._fixed_deck = validate_deck(deck) if deck is not None else None
        self._evaluator = HandEvaluator()
        self._started = False
        self.hand_over = False
        self.button = 0
        self.board: list[str] = []
        self.street = "preflop"
        self.current_bet = 0
        self.min_raise = BIG_BLIND
        self.to_act: int | None = None
        self._deck: Deck | None = None
        self._winners: list[dict[str, int]] = []

    def new_hand(self) -> None:
        if self._started and not self.hand_over:
            raise RuntimeError("hand still in progress")
        if sum(player.stack > 0 for player in self.players) < 2:
            raise RuntimeError("at least two players need chips")
        self.button = 0 if not self._started else (self.button + 1) % SEATS
        self._started = True
        self.hand_over = False
        self.board = []
        self.street = "preflop"
        self.current_bet = 0
        self.min_raise = BIG_BLIND
        self.to_act = None
        self._winners = []
        for player in self.players:
            player.in_hand = player.stack > 0
            player.hole = []
            player.folded = not player.in_hand
            player.all_in = False
            player.street_commit = 0
            player.total_commit = 0
            player.acted = False
            player.can_raise = True
        self._deck = self._make_deck()
        self._deal_hole_cards()
        self._post_blinds()
        self.current_bet = max(player.street_commit for player in self.players)
        self.to_act = self._first_actor()
        if self.to_act is None:
            self._end_betting_round()

    def legal_actions(self, seat: int) -> list[Action]:
        self._require_seat(seat)
        if not self._started:
            raise ValueError("no hand in progress")
        if self.hand_over or seat != self.to_act:
            return []
        return self._options(self.players[seat])

    def apply(self, seat: int, action: Action | str) -> None:
        chosen = Action(action)
        self._require_seat(seat)
        if not self._started:
            raise ValueError("no hand in progress")
        if self.hand_over:
            raise ValueError("hand is over")
        if seat != self.to_act:
            raise ValueError(f"it is seat {self.to_act}'s turn")
        if chosen not in self._options(self.players[seat]):
            raise ValueError(f"{chosen.value} is not legal")
        player = self.players[seat]
        if chosen is Action.FOLD:
            player.folded = True
            player.acted = True
        elif chosen is Action.CHECK:
            player.acted = True
        elif chosen is Action.CALL:
            self._call(player)
        elif chosen is Action.ALL_IN:
            self._shove(player)
        elif chosen is Action.RAISE_HALF_POT:
            self._raise_sized(player, half=True)
        elif chosen is Action.RAISE_POT:
            self._raise_sized(player, half=False)
        self._proceed(seat)

    def public_state(self) -> dict:
        if not self._started:
            raise ValueError("no hand in progress")
        return copy.deepcopy(self._snapshot())

    def private_state(self, seat: int) -> dict:
        self._require_seat(seat)
        state = self.public_state()
        state["hole_cards"] = list(self.players[seat].hole)
        return state

    def is_hand_over(self) -> bool:
        return self._started and self.hand_over

    def winners(self) -> list[dict[str, int]]:
        if not self.is_hand_over():
            raise ValueError("hand is not over")
        return [dict(item) for item in self._winners]

    def _make_deck(self) -> Deck:
        if self._fixed_deck is not None:
            return Deck(self._fixed_deck)
        cards = standard_deck()
        self._rng.shuffle(cards)
        return Deck(cards)

    def _snapshot(self) -> dict:
        return {
            "button": self.button,
            "street": self.street,
            "board": list(self.board),
            "pot": self._pot(),
            "current_bet": self.current_bet,
            "min_raise": self.min_raise,
            "to_act": self.to_act,
            "hand_over": self.hand_over,
            "players": [
                {
                    "seat": player.seat,
                    "stack": player.stack,
                    "street_commit": player.street_commit,
                    "total_commit": player.total_commit,
                    "folded": player.folded,
                    "all_in": player.all_in,
                    "in_hand": player.in_hand,
                    "position": _POSITIONS[(player.seat - self.button) % SEATS],
                    "to_call": max(0, self.current_bet - player.street_commit),
                }
                for player in self.players
            ],
        }

    def _options(self, player: Player) -> list[Action]:
        if player.folded or player.all_in or not player.in_hand:
            return []
        to_call = max(0, self.current_bet - player.street_commit)
        actions: list[Action] = []
        if to_call == 0:
            actions.append(Action.CHECK)
        else:
            actions.append(Action.FOLD)
            actions.append(Action.CALL)
        if player.can_raise and player.stack > to_call:
            actions.extend((Action.RAISE_HALF_POT, Action.RAISE_POT, Action.ALL_IN))
        elif to_call > 0 and 0 < player.stack <= to_call:
            actions.append(Action.ALL_IN)
        return actions

    def _call(self, player: Player) -> None:
        self._commit(player, self.current_bet - player.street_commit)
        player.acted = True

    def _shove(self, player: Player) -> None:
        target = player.street_commit + player.stack
        if target <= self.current_bet:
            self._call(player)
            return
        self._apply_aggression(player, target)

    def _raise_sized(self, player: Player, half: bool) -> None:
        pot = self._pot()
        target = self.current_bet + (pot // 2 if half else pot)
        minimum = self.current_bet + self.min_raise
        if target < minimum:
            target = minimum
        affordable = player.street_commit + player.stack
        if target > affordable:
            target = affordable
        if target <= self.current_bet:
            self._call(player)
            return
        self._apply_aggression(player, target)

    def _apply_aggression(self, player: Player, target: int) -> None:
        previous = self.current_bet
        self._commit(player, target - player.street_commit)
        if player.street_commit <= previous:
            player.acted = True
            return
        increase = player.street_commit - previous
        self.current_bet = player.street_commit
        full_raise = increase >= self.min_raise
        if full_raise:
            self.min_raise = increase
        for other in self.players:
            if other.seat == player.seat or other.folded or other.all_in or not other.in_hand:
                continue
            if full_raise:
                other.acted = False
                other.can_raise = True
            elif other.street_commit < self.current_bet:
                if other.acted:
                    other.can_raise = False
                other.acted = False
        player.acted = True

    def _commit(self, player: Player, amount: int) -> None:
        if amount < 0:
            raise RuntimeError("cannot commit a negative amount")
        amount = min(amount, player.stack)
        player.stack -= amount
        player.street_commit += amount
        player.total_commit += amount
        if player.stack == 0 and player.in_hand:
            player.all_in = True

    def _proceed(self, actor: int) -> None:
        if len(self._alive()) <= 1:
            self._finish(showdown=False)
            return
        nxt = self._next_actor(actor)
        if nxt is None:
            self._end_betting_round()
            return
        self.to_act = nxt

    def _end_betting_round(self) -> None:
        alive = self._alive()
        if len(alive) <= 1:
            self._finish(showdown=False)
            return
        can_bet = sum(not player.all_in for player in alive)
        if self.street != "river" and can_bet > 1:
            self._advance_street()
            return
        self._deal_remaining()
        self._finish(showdown=True)

    def _advance_street(self) -> None:
        if self.street == "preflop":
            self._deal_board(3)
            self.street = "flop"
        elif self.street == "flop":
            self._deal_board(1)
            self.street = "turn"
        elif self.street == "turn":
            self._deal_board(1)
            self.street = "river"
        else:
            raise RuntimeError(f"no street follows {self.street}")
        for player in self.players:
            player.street_commit = 0
            player.acted = False
            player.can_raise = True
        self.current_bet = 0
        self.min_raise = BIG_BLIND
        self.to_act = self._first_actor()
        if self.to_act is None:
            self._deal_remaining()
            self._finish(showdown=True)

    def _deal_hole_cards(self) -> None:
        start = self._next_in_hand(self.button + 1)
        if start is None or self._deck is None:
            raise RuntimeError("cannot deal")
        order = []
        for offset in range(SEATS):
            seat = (start + offset) % SEATS
            if self.players[seat].in_hand:
                order.append(seat)
        for _ in range(2):
            for seat in order:
                self.players[seat].hole.extend(self._deck.draw(1))

    def _deal_board(self, count: int) -> None:
        if self._deck is None:
            raise RuntimeError("cannot deal")
        self._deck.draw(1)
        self.board.extend(self._deck.draw(count))

    def _deal_remaining(self) -> None:
        if len(self.board) == 0:
            self._deal_board(3)
        if len(self.board) == 3:
            self._deal_board(1)
        if len(self.board) == 4:
            self._deal_board(1)

    def _post_blinds(self) -> None:
        sb_seat = self._next_in_hand(self.button + 1)
        if sb_seat is None:
            raise RuntimeError("cannot post blinds")
        bb_seat = self._next_in_hand(sb_seat + 1)
        if bb_seat is None or bb_seat == sb_seat:
            raise RuntimeError("cannot post blinds")
        self._commit(self.players[sb_seat], min(SMALL_BLIND, self.players[sb_seat].stack))
        self._commit(self.players[bb_seat], min(BIG_BLIND, self.players[bb_seat].stack))

    def _finish(self, showdown: bool) -> None:
        if self.hand_over:
            return
        winnings = self._winnings(showdown)
        committed = self._pot()
        if sum(winnings) != committed:
            raise RuntimeError(f"pot did not balance: awarded {sum(winnings)} of {committed}")
        for player, amount in zip(self.players, winnings, strict=True):
            player.stack += amount
        self._winners = [
            {"seat": seat, "amount": amount}
            for seat, amount in enumerate(winnings)
            if amount > 0
        ]
        self.hand_over = True
        self.to_act = None
        if showdown:
            self.street = "showdown"

    def _winnings(self, showdown: bool) -> list[int]:
        alive = self._alive()
        if showdown and len(self.board) != 5:
            raise RuntimeError("showdown requires a full board")
        scores = {
            player.seat: self._evaluator.score(player.hole, self.board) for player in alive
        } if showdown else {}
        winnings = [0] * SEATS
        alive_seats = {player.seat for player in alive}
        previous = 0
        levels = sorted({player.total_commit for player in self.players if player.total_commit > 0})
        for level in levels:
            contributors = [player.seat for player in self.players if player.total_commit >= level]
            amount = (level - previous) * len(contributors)
            eligible = [seat for seat in contributors if seat in alive_seats]
            if amount > 0 and not eligible:
                if len(alive_seats) != 1:
                    raise RuntimeError("pot layer has no eligible player")
                eligible = list(alive_seats)
            if amount > 0 and len(eligible) == 1:
                winnings[eligible[0]] += amount
            elif amount > 0:
                if not showdown:
                    raise RuntimeError("contested pot ended without showdown")
                best = min(scores[seat] for seat in eligible)
                tied = [seat for seat in eligible if scores[seat] == best]
                self._pay_split(amount, tied, winnings)
            previous = level
        return winnings

    def _pay_split(self, amount: int, seats: list[int], winnings: list[int]) -> None:
        wanted = set(seats)
        ordered = [
            seat
            for offset in range(1, SEATS + 1)
            if (seat := (self.button + offset) % SEATS) in wanted
        ]
        if len(ordered) != len(wanted):
            raise RuntimeError("winner seats were not seated")
        share, remainder = divmod(amount, len(ordered))
        for seat in ordered:
            winnings[seat] += share
        if remainder:
            winnings[ordered[0]] += remainder

    def _first_actor(self) -> int | None:
        opening = self.button + (3 if self.street == "preflop" else 1)
        return self._next_actor(opening - 1)

    def _next_actor(self, after: int) -> int | None:
        for offset in range(1, SEATS + 1):
            seat = (after + offset) % SEATS
            if self._must_act(self.players[seat]):
                return seat
        return None

    def _must_act(self, player: Player) -> bool:
        if not player.in_hand or player.folded or player.all_in:
            return False
        if player.street_commit < self.current_bet:
            return True
        return not player.acted

    def _alive(self) -> list[Player]:
        return [player for player in self.players if player.in_hand and not player.folded]

    def _next_in_hand(self, start: int) -> int | None:
        for offset in range(SEATS):
            seat = (start + offset) % SEATS
            if self.players[seat].in_hand:
                return seat
        return None

    def _pot(self) -> int:
        return sum(player.total_commit for player in self.players)

    @staticmethod
    def _require_seat(seat: int) -> None:
        if type(seat) is not int or seat not in range(SEATS):
            raise ValueError("seat must be 0, 1, 2, or 3")
