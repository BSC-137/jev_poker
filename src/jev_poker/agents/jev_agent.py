"""Two Jev requests per decision. Prior judgments are evidence for the action choice."""

from __future__ import annotations

import copy
import random
from typing import Protocol

from jev_poker.agents.personas import Persona
from jev_poker.agents.policy import board_bonus_from_texture, decide as select_action
from jev_poker.engine.game import Game
from jev_poker.jev.client import JevClient, JevResult
from jev_poker.math.state import decision_state

_ACTION_INSTRUCTIONS = (
    "Pick the legal action for this persona. "
    "prior_judgments are evidence, not orders. "
    "Use only the provided actions."
)
_BLUFF_INSTRUCTIONS = (
    "Is a bluff bet or raise aligned with this persona on this street? "
    "Use hero_equity_vs_continuing, pot_odds, board_texture, opponent fold_to_bet, and spr from the state."
)
_RANGE_INSTRUCTIONS = "How strong is hero's range advantage for value betting on this board?"
_RANGE_CRITERIA = [
    "Clear disadvantage",
    "Slight disadvantage",
    "Neutral",
    "Slight advantage",
    "Clear advantage",
]
_ERROR_LIMIT = 300


class DecisionClient(Protocol):
    def submit(self, state: dict, questions: dict) -> JevResult: ...


class JevAgent:
    """Ask Jev for prior judgments, then for an action. Math plays only when Jev cannot."""

    def __init__(
        self,
        persona: Persona,
        client: DecisionClient | None = None,
        *,
        math_only: bool = False,
    ) -> None:
        self.persona = persona
        self._math_only = math_only
        if math_only:
            self._client = None
            return
        self._client = client if client is not None else JevClient()

    def decide(
        self,
        game: Game,
        seat: int,
        *,
        iterations: int = 300,
        rng: random.Random | None = None,
    ) -> dict:
        state = decision_state(
            game,
            seat,
            continuing_fraction=self.persona.continuing_fraction,
            iterations=iterations,
            rng=rng,
        )
        if not state["legal_actions"]:
            raise ValueError(f"seat {seat} has no legal actions")
        state["persona"] = self.persona.to_state()
        math_choice = math_action(self.persona, state)
        if self._math_only:
            return decision_record(
                seat=seat,
                persona_id=self.persona.id,
                street=state["street"],
                state=state,
                answers=None,
                action=math_choice,
                math_action=math_choice,
                source="math",
                confidence=None,
                cost_usd=0.0,
                elapsed_seconds=0.0,
            )
        try:
            return self._ask(state, seat, math_choice)
        except Exception as exc:
            return decision_record(
                seat=seat,
                persona_id=self.persona.id,
                street=state["street"],
                state=state,
                answers=None,
                action=math_choice,
                math_action=math_choice,
                source="math_error",
                confidence=None,
                cost_usd=0.0,
                elapsed_seconds=0.0,
                error=format_error(exc),
            )

    def _ask(self, state: dict, seat: int, math_choice: str) -> dict:
        if self._client is None:
            raise RuntimeError("Jev client is not configured")
        prior = self._client.submit(state, build_prior_questions(self.persona))
        judged = copy.deepcopy(state)
        judged["prior_judgments"] = prior_judgments(prior.answers)
        action_result = self._client.submit(
            judged,
            build_action_questions(self.persona, state["legal_actions"]),
        )
        played, confidence, source = resolve_action(
            state["legal_actions"],
            action_result.answers.get("action"),
            math_choice,
        )
        answers = {
            "bluff_spot": prior.answers.get("bluff_spot"),
            "range_advantage": prior.answers.get("range_advantage"),
            "action": action_result.answers.get("action"),
        }
        return decision_record(
            seat=seat,
            persona_id=self.persona.id,
            street=state["street"],
            state=state,
            answers=answers,
            action=played,
            math_action=math_choice,
            source=source,
            confidence=confidence,
            cost_usd=prior.cost + action_result.cost,
            elapsed_seconds=prior.elapsed_seconds + action_result.elapsed_seconds,
            input_tokens=_add_tokens(prior.input_tokens, action_result.input_tokens),
            output_tokens=_add_tokens(prior.output_tokens, action_result.output_tokens),
        )


def math_action(persona: Persona, state: dict) -> str:
    """Equity-rule action. ``decide`` is called with no Jev choice."""
    chosen = select_action(
        state["legal_actions"],
        state["pot_odds"],
        state["hero_equity_vs_continuing"],
        persona.fallback_equity_margin,
        None,
        None,
        to_call=state["to_call"],
        spr=state["spr"],
        persona_id=persona.id,
        board_bonus=board_bonus_from_texture(state["board_texture"]),
    )
    return chosen["action"]


def decision_record(
    *,
    seat: int,
    persona_id: str,
    street: str,
    state: dict,
    answers: dict | None,
    action: str,
    math_action: str,
    source: str,
    confidence: float | None,
    cost_usd: float,
    elapsed_seconds: float,
    error: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> dict:
    record = {
        "seat": seat,
        "persona_id": persona_id,
        "street": street,
        "state": state,
        "answers": answers,
        "action": action,
        "math_action": math_action,
        "source": source,
        "confidence": confidence,
        "cost_usd": cost_usd,
        "elapsed_seconds": elapsed_seconds,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    if error is not None:
        record["error"] = error
    return record


def format_error(exc: BaseException) -> str:
    """Exception type plus message, truncated at 300 characters."""
    name = type(exc).__name__
    detail = str(exc).strip()
    text = f"{name}: {detail}" if detail else name
    return text[:_ERROR_LIMIT]


def prior_judgments(answers: dict) -> dict:
    """Map call A's noul and score onto the labels call B will read."""
    bluff = answers.get("bluff_spot") if isinstance(answers, dict) else None
    advantage = answers.get("range_advantage") if isinstance(answers, dict) else None
    if not isinstance(bluff, dict) or not isinstance(advantage, dict):
        raise ValueError("missing bluff_spot or range_advantage")
    noul = bluff.get("noul")
    score = advantage.get("score")
    if not _is_number(noul) or not _is_number(score):
        raise ValueError("missing bluff_spot or range_advantage")
    rounded = int(round(float(score)))
    index = min(4, max(0, rounded))
    return {
        "bluff_spot": float(noul),
        "range_advantage_score": float(score),
        "range_advantage_label": _RANGE_CRITERIA[index],
    }


def build_prior_questions(persona: Persona) -> dict:
    """Call A. Questions only, with no action choice."""
    return {
        "bluff_spot": {
            "type": "noul",
            "instructions": _BLUFF_INSTRUCTIONS,
            "criteria": persona.bluff_criteria(),
        },
        "range_advantage": {
            "type": "score",
            "instructions": _RANGE_INSTRUCTIONS,
            "criteria": list(_RANGE_CRITERIA),
        },
    }


def build_action_questions(persona: Persona, legal_actions: list[str]) -> dict:
    """Call B. The only question is the legal action."""
    return {
        "action": {
            "type": "choice",
            "instructions": _ACTION_INSTRUCTIONS,
            "criteria": persona.action_criteria(legal_actions),
        },
    }


def _add_tokens(left: int | None, right: int | None) -> int | None:
    if left is None and right is None:
        return None
    return (left or 0) + (right or 0)


def resolve_action(
    legal_actions: list[str],
    action_answer: object,
    math_choice: str,
) -> tuple[str, float | None, str]:
    """Play Jev when the choice is legal and confidence is in range. Otherwise math."""
    choice, confidence = _choice_and_confidence(action_answer)
    if isinstance(choice, str) and choice in legal_actions and confidence is not None:
        return choice, confidence, "jev"
    return math_choice, confidence, "math"


def _choice_and_confidence(action: object) -> tuple[str | None, float | None]:
    if not isinstance(action, dict):
        return None, None
    choice = action.get("choice")
    confidence = action.get("confidence")
    if not _is_number(confidence) or not 0 <= float(confidence) <= 1:
        return choice if isinstance(choice, str) else None, None
    return choice if isinstance(choice, str) else None, float(confidence)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
