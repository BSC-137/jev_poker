"""Four hold'em personas. Criteria are rebuilt from the legal actions each decision."""

from __future__ import annotations

from dataclasses import dataclass, field

_ACTIONS = ("fold", "check", "call", "raise_half_pot", "raise_pot", "all_in")


@dataclass(frozen=True)
class Persona:
    id: str
    display_name: str
    color: str
    continuing_fraction: float
    fallback_equity_margin: float
    _action_lines: dict[str, str] = field(repr=False)
    _bluff_true: str = field(repr=False)
    _bluff_false: str = field(repr=False)

    def __post_init__(self) -> None:
        if set(self._action_lines) != set(_ACTIONS):
            raise ValueError(f"{self.id} must define criteria for every action")

    def action_criteria(self, legal_actions: list[str]) -> dict[str, str]:
        """Criteria for this decision only. Illegal actions are omitted."""
        missing = [action for action in legal_actions if action not in self._action_lines]
        if missing:
            raise ValueError(f"no criteria for actions: {missing}")
        return {action: self._action_lines[action] for action in legal_actions}

    def bluff_criteria(self) -> dict[str, str]:
        return {"false": self._bluff_false, "true": self._bluff_true}

    def to_state(self) -> dict:
        return {
            "id": self.id,
            "display_name": self.display_name,
            "color": self.color,
            "continuing_fraction": self.continuing_fraction,
            "fallback_equity_margin": self.fallback_equity_margin,
        }


def _persona(
    persona_id: str,
    display_name: str,
    color: str,
    continuing_fraction: float,
    fallback_equity_margin: float,
    lines: dict[str, str],
    bluff_true: str,
    bluff_false: str,
) -> Persona:
    return Persona(
        persona_id,
        display_name,
        color,
        continuing_fraction,
        fallback_equity_margin,
        lines,
        bluff_true,
        bluff_false,
    )


ROCK = _persona(
    "rock",
    "Rock",
    "#94a3b8",
    0.25,
    0.12,
    {
        "fold": "to_call is greater than 0 and hero_equity_vs_continuing is below pot_odds plus a wide margin, or the board texture is monotone.",
        "check": "to_call is 0 and hero_equity_vs_continuing is below 0.70, or spr is high on a connected board texture.",
        "call": "to_call is greater than 0 and hero_equity_vs_continuing clears pot_odds by a wide margin while spr stays above 3.",
        "raise_half_pot": "to_call is 0, hero_equity_vs_continuing is at least 0.70, and board texture connectedness is 0.",
        "raise_pot": "hero_equity_vs_continuing is at least 0.80 and the board texture is dry or paired.",
        "all_in": "spr is below 3, the remaining stack is short, and hero_equity_vs_continuing is at least 0.92.",
    },
    "hero_equity_vs_continuing is below 0.5, the board texture is dry (connectedness 0 and not monotone), and an opponent fold_to_bet is high enough to bluff at a continuing fraction of 0.25.",
    "hero_equity_vs_continuing is below 0.5 but the board texture is monotone, paired, or connected, or no opponent fold_to_bet supports a bluff at a continuing fraction of 0.25.",
)

SHARK = _persona(
    "shark",
    "Shark",
    "#14b8a6",
    0.40,
    0.04,
    {
        "fold": "to_call is greater than 0 and hero_equity_vs_continuing is below pot_odds plus a small margin, with opponent fold_to_bet too low to bluff.",
        "check": "to_call is 0 and hero_equity_vs_continuing is below 0.55 on a wet board texture.",
        "call": "to_call is greater than 0 and hero_equity_vs_continuing meets pot_odds plus a small margin.",
        "raise_half_pot": "to_call is 0 and hero_equity_vs_continuing is at least 0.55, or the board texture is dry and an opponent fold_to_bet is high.",
        "raise_pot": "hero_equity_vs_continuing is at least 0.80, or spr is moderate and the board texture favors a value bet.",
        "all_in": "spr is below 3 and hero_equity_vs_continuing is at least 0.92.",
    },
    "hero_equity_vs_continuing is below 0.5, the board texture is dry or an opponent fold_to_bet is high, and a bluff fits a continuing fraction of 0.40.",
    "hero_equity_vs_continuing is below 0.5 and the board texture is wet or monotone, so a bluff does not fit a continuing fraction of 0.40.",
)

CALLER = _persona(
    "caller",
    "Caller",
    "#38bdf8",
    0.55,
    0.00,
    {
        "fold": "to_call is greater than 0 and hero_equity_vs_continuing is below pot_odds.",
        "check": "to_call is 0 and hero_equity_vs_continuing is below 0.80.",
        "call": "to_call is greater than 0 and hero_equity_vs_continuing is at least pot_odds, including a close price.",
        "raise_half_pot": "to_call is 0, hero_equity_vs_continuing is at least 0.70, and the board texture is dry.",
        "raise_pot": "hero_equity_vs_continuing is at least 0.80 and spr is not already tiny.",
        "all_in": "spr is below 3 and hero_equity_vs_continuing is at least 0.92.",
    },
    "hero_equity_vs_continuing is below 0.5, the board texture is dry, and an opponent fold_to_bet is extremely high for a continuing fraction of 0.55.",
    "hero_equity_vs_continuing is below 0.5 and the board texture is not extremely dry, so a bluff does not fit a continuing fraction of 0.55.",
)

MANIAC = _persona(
    "maniac",
    "Maniac",
    "#f43f5e",
    0.70,
    -0.06,
    {
        "fold": "to_call is greater than 0, spr is high, hero_equity_vs_continuing is far below pot_odds, and the board texture is monotone with no fold equity.",
        "check": "to_call is 0, hero_equity_vs_continuing is very low, and the board texture is monotone.",
        "call": "to_call is greater than 0 and hero_equity_vs_continuing is within a small deficit of pot_odds.",
        "raise_half_pot": "to_call is 0, or an opponent fold_to_bet is elevated, even when hero_equity_vs_continuing is below 0.55.",
        "raise_pot": "the board texture is dry or an opponent aggression_factor is low, even at a moderate hero_equity_vs_continuing.",
        "all_in": "spr is below 3, or the stack is short relative to the pot on a dry board texture.",
    },
    "hero_equity_vs_continuing is below 0.5 and the board texture still offers fold equity, which fits a continuing fraction of 0.70.",
    "hero_equity_vs_continuing is below 0.5 and the board texture is monotone with no opponent fold_to_bet, so a bluff does not fit a continuing fraction of 0.70.",
)

PERSONAS = (ROCK, SHARK, CALLER, MANIAC)
PERSONAS_BY_ID = {persona.id: persona for persona in PERSONAS}
