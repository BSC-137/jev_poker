# jev_poker

Local play-money 4-handed No-Limit Texas Hold'em for simulating our own bots against each other.

The package deals cards, runs betting, awards pots, and builds the numbers a later decision model would read. It does not connect to poker sites, create accounts, or handle real money.

## Requirements

- Python 3.12 or newer
- [treys](https://github.com/ihendley/treys) for 7-card hand ranks (a lower score is a better hand)

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Tests

```powershell
pytest
```

## Engine

`Game` in `jev_poker.engine.game` runs one table of four seats.

```python
from jev_poker.engine.actions import Action
from jev_poker.engine.game import Game

game = Game(seed=1)
game.new_hand()
seat = game.public_state()["to_act"]
game.apply(seat, Action.CALL)
```

Each hand the seats are BTN, SB, BB, and UTG. The button moves clockwise after the hand. Blinds are 10/20 and every seat starts at 2000. A player who cannot post a full blind posts what they have and is all-in.

Streets are preflop, flop (3), turn (1), and river (1), then showdown. One card is burned before the flop, the turn, and the river. Preflop action starts at UTG. Later streets start with the first active player left of the button.

Legal actions are only `fold`, `check`, `call`, `raise_half_pot`, `raise_pot`, and `all_in`.

- Check is legal only when nothing is owed. Fold is legal only when something is owed.
- A call puts in `min(to_call, stack)`.
- Half-pot and pot raises set the street commitment to `current bet + pot // 2` or `current bet + pot`, using the pot before the raise. A target below the minimum raise is raised up to that minimum. A target the player cannot cover becomes an all-in.
- The minimum raise is the previous full raise, or one big blind if nobody has raised on this street. An all-in smaller than a full raise does not reopen raising for players who have already acted.

At showdown each pot, including side pots, goes to the best eligible hand. Exact ties split. Any leftover chip goes to the earliest winning seat left of the button. Folded hands do not win. If everyone else folds, the remaining player takes the pot without a showdown.

`Game(seed=...)` shuffles deterministically. `public_state()` hides hole cards. `private_state(seat)` adds that seat's hole cards only.

`Game.action_log` records every voluntary decision across hands: street, seat, position, action, chips added, and whether the player was facing a bet. Blinds are not decisions.

## Math

Everything under `jev_poker.math` is local arithmetic. It does not call a network API.

### Equity

`monte_carlo_equity` estimates hero's share of the pot against one or more opponents dealt uniformly from the cards that are still unknown. The default is 300 iterations. Ties count as a split. Hero cards, board cards, and any dead cards are never dealt again.

`equity_vs_top_fraction` is the same estimate, except each opponent is restricted to the strongest `fraction` of remaining hole-card combos. On the flop, turn, and river those combos are ordered by their current treys score. Preflop, treys cannot rank two cards, so the 169 starting-hand classes use a fixed order checked into `jev_poker.math.preflop_order`. That order was generated offline (5,000 runouts per class against a random hand, ties counting half). It starts at AA. In that sample the weakest class is 42o; 72o is in the same bottom group, a little above 32o and 42o. **This is a strength filter, not a GTO range.** It ignores position, stack depth, and balanced strategy.

### Board texture

`board_texture` reports whether the board is paired, monotone, or two-tone, plus the high-card rank. `connectedness` is 0, 1, or 2: one point if a single missing rank would complete a straight, and one point if two board ranks are at most four apart.

### Stats

`stats_by_seat` reads `Game.action_log`.

| Stat | Meaning |
| --- | --- |
| `vpip` | Share of preflop decisions in which the player voluntarily put chips in |
| `pfr` | Share of those hands in which the player raised preflop |
| `fold_to_bet` | Folds divided by decisions made while facing a bet |
| `aggression_factor` | Raises and bets divided by calls |

If a seat has no sample for a stat, the value is `null`. It is not reported as `0`, because zero would look like a measured tendency. A player who has faced bets and never folded really does have `fold_to_bet` of `0.0`.

### Decision state

`decision_state(game, hero_seat)` builds the dict a later model will read: street, hero (including hole cards), board, pot, amount to call, pot odds, stack-to-pot ratio, equity versus random opponents, equity versus the continuing strength filter, board texture, legal actions, this hand's action history, and each opponent's stack and running stats.

```text
pot_odds = to_call / (pot + to_call)    # 0 when checking is free
spr      = hero_stack / pot              # when the pot is positive
```

Only the hero's hole cards appear. Other players' hole cards are not part of the object, and equity is not given those cards either.
