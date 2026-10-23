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
        "fold": "Facing a bet, fold unless hero_equity_vs_continuing clearly beats pot_odds on a dry board_texture.",
        "check": "Check when nothing is owed unless hero_equity_vs_continuing and prior_judgments.range_advantage_score are both strong.",
        "call": "Call a bet only when hero_equity_vs_continuing clearly beats pot_odds on a dry board_texture.",
        "raise_half_pot": "Raise only from strength when hero_equity_vs_continuing and prior_judgments.range_advantage_score are both strong.",
        "raise_pot": "Raise only from strength when hero_equity_vs_continuing is dominant and prior_judgments.range_advantage_score is strong.",
        "all_in": "All-in only when spr is short and hero_equity_vs_continuing is dominant.",
    },
    "A bluff bet or raise is never aligned for this persona, even when fold_to_bet is high on a dry board_texture.",
    "This persona does not bluff, so hero_equity_vs_continuing, pot_odds, spr, board_texture, and fold_to_bet leave a bluff unaligned.",
)

SHARK = _persona(
    "shark",
    "Shark",
    "#14b8a6",
    0.40,
    0.04,
    {
        "fold": "Fold when facing a bet, hero_equity_vs_continuing loses to pot_odds, and prior_judgments.bluff_spot is low.",
        "check": "Check when nothing is owed unless prior_judgments.range_advantage_score is high enough to value-bet.",
        "call": "Call when facing a bet and hero_equity_vs_continuing meets pot_odds without a high prior_judgments.range_advantage_score or a high prior_judgments.bluff_spot.",
        "raise_half_pot": "Value-bet when prior_judgments.range_advantage_score is high, or bluff-raise when prior_judgments.bluff_spot is high and fold_to_bet is high.",
        "raise_pot": "Value-bet when prior_judgments.range_advantage_score is high and hero_equity_vs_continuing is strong.",
        "all_in": "All-in when spr is short and hero_equity_vs_continuing is dominant, or when prior_judgments.bluff_spot and fold_to_bet are both high.",
    },
    "A bluff bet or raise is aligned when fold_to_bet is high, especially on a dry board_texture, even when hero_equity_vs_continuing loses to pot_odds.",
    "A bluff is not aligned when fold_to_bet is low or board_texture is monotone while hero_equity_vs_continuing loses to pot_odds.",
)

CALLER = _persona(
    "caller",
    "Caller",
    "#38bdf8",
    0.55,
    0.00,
    {
        "fold": "Fold when facing a bet and hero_equity_vs_continuing fails to meet pot_odds.",
        "check": "Check when nothing is owed unless hero_equity_vs_continuing and prior_judgments.range_advantage_score are both strong.",
        "call": "Call when hero_equity_vs_continuing meets pot_odds, including a close price.",
        "raise_half_pot": "Raise only rarely when hero_equity_vs_continuing and prior_judgments.range_advantage_score are both strong.",
        "raise_pot": "Raise only rarely when hero_equity_vs_continuing is dominant and prior_judgments.range_advantage_score is strong.",
        "all_in": "All-in only when spr is short and hero_equity_vs_continuing is dominant.",
    },
    "A bluff is never aligned for this persona, even when fold_to_bet is high on a dry board_texture.",
    "This persona does not bluff, so hero_equity_vs_continuing, pot_odds, spr, board_texture, and fold_to_bet do not justify a bluff.",
)

MANIAC = _persona(
    "maniac",
    "Maniac",
    "#f43f5e",
    0.70,
    -0.06,
    {
        "fold": "Fold only when facing a bet, hero_equity_vs_continuing is far behind pot_odds, board_texture is monotone, and prior_judgments.bluff_spot is low.",
        "check": "Check only when nothing is owed, board_texture is monotone, hero_equity_vs_continuing is weak, and prior_judgments.bluff_spot is low.",
        "call": "Call when facing a bet and hero_equity_vs_continuing is close to pot_odds.",
        "raise_half_pot": "Raise when prior_judgments.bluff_spot is high or fold_to_bet is high, even when hero_equity_vs_continuing is weak, especially on a dry board_texture.",
        "raise_pot": "Raise when prior_judgments.bluff_spot is high or fold_to_bet is high on a dry board_texture, even when hero_equity_vs_continuing is weak.",
        "all_in": "All-in when prior_judgments.bluff_spot is high or fold_to_bet is high, even when hero_equity_vs_continuing is weak, especially when spr is short on a dry board_texture.",
    },
    "A bluff is aligned when fold_to_bet is high or board_texture is dry, even when hero_equity_vs_continuing is weak against pot_odds.",
    "A bluff is not aligned when hero_equity_vs_continuing is far behind pot_odds, board_texture is monotone, and fold_to_bet is low.",
)

PERSONAS = (ROCK, SHARK, CALLER, MANIAC)
PERSONAS_BY_ID = {persona.id: persona for persona in PERSONAS}
