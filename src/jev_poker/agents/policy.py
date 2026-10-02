"""Pure action selection. Jev plays when it is confident and legal; otherwise math does."""

from __future__ import annotations

JEV_CONFIDENCE_MIN = 0.45
_BET_EQUITY = 0.55
_POT_RAISE_EQUITY = 0.80
_SHOVE_EQUITY = 0.92
_SHOVE_SPR = 3.0
_DRY_BOARD_BONUS = 0.03
_HALF_POT_PERSONAS = frozenset({"shark", "maniac"})
_CLAMP_ORDER = ("check", "call", "fold", "raise_half_pot", "raise_pot", "all_in")


def board_bonus_from_texture(texture: dict) -> float:
    """Small equity bump used only when deciding to bet with nothing owed."""
    if texture.get("monotone") or texture.get("connectedness", 0) >= 2:
        return 0.0
    return _DRY_BOARD_BONUS


def decide(
    legal_actions: list[str],
    pot_odds: float,
    equity: float,
    margin: float,
    jev_action: str | None,
    jev_confidence: float | None,
    *,
    to_call: float | None = None,
    spr: float | None = None,
    persona_id: str = "caller",
    board_bonus: float = 0.0,
) -> dict[str, str]:
    """Return ``{action, source}`` with ``source`` of ``jev`` or ``math``.

    ``source`` is ``jev`` when ``jev_action`` is legal and ``jev_confidence``
    is at least 0.45. Otherwise the math policy chooses and the result is
    clamped to ``legal_actions``. ``pot_odds`` of 0 means nothing is owed
    when ``to_call`` is omitted.
    """
    if not legal_actions:
        raise ValueError("no legal actions")
    confident = (
        isinstance(jev_confidence, (int, float))
        and not isinstance(jev_confidence, bool)
        and jev_confidence >= JEV_CONFIDENCE_MIN
    )
    if isinstance(jev_action, str) and jev_action in legal_actions and confident:
        return {"action": jev_action, "source": "jev"}
    preferred = _math_action(
        legal_actions,
        pot_odds,
        equity,
        margin,
        to_call=to_call,
        spr=spr,
        persona_id=persona_id,
        board_bonus=board_bonus,
    )
    return {"action": _clamp(preferred, legal_actions), "source": "math"}


def _math_action(
    legal_actions: list[str],
    pot_odds: float,
    equity: float,
    margin: float,
    *,
    to_call: float | None,
    spr: float | None,
    persona_id: str,
    board_bonus: float,
) -> str:
    nothing_owed = to_call == 0 if to_call is not None else pot_odds == 0
    if nothing_owed:
        if equity + board_bonus >= _BET_EQUITY and persona_id in _HALF_POT_PERSONAS:
            action = "raise_half_pot"
        else:
            action = "check"
    elif equity >= pot_odds + margin:
        action = "call"
    else:
        action = "fold"
    if equity >= _POT_RAISE_EQUITY and "raise_pot" in legal_actions:
        action = "raise_pot"
    if (
        equity >= _SHOVE_EQUITY
        and "all_in" in legal_actions
        and spr is not None
        and spr < _SHOVE_SPR
    ):
        action = "all_in"
    return action


def _clamp(action: str, legal_actions: list[str]) -> str:
    if action in legal_actions:
        return action
    for candidate in _CLAMP_ORDER:
        if candidate in legal_actions:
            return candidate
    return legal_actions[0]
