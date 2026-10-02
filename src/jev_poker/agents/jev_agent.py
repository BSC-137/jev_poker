"""One Jev request per decision. The action choice is played; the other two are stored."""

from __future__ import annotations

import random
from typing import Protocol

from jev_poker.agents.personas import Persona
from jev_poker.agents.policy import board_bonus_from_texture, decide as select_action
from jev_poker.engine.game import Game
from jev_poker.jev.client import JevClient, JevResult
from jev_poker.math.state import decision_state

_ACTION_INSTRUCTIONS = (
    "Pick the legal action that best matches this persona given the numeric state. "
    "Use only the provided actions."
)
_BLUFF_INSTRUCTIONS = (
    "Is betting or raising as a bluff aligned with this persona on this street, "
    "given hero_equity_vs_continuing is below 0.5?"
)
_RANGE_INSTRUCTIONS = "How strong is hero's range advantage for value betting on this board?"
_RANGE_CRITERIA = [
    "Clear disadvantage",
    "Slight disadvantage",
    "Neutral",
    "Slight advantage",
    "Clear advantage",
]


class DecisionClient(Protocol):
    def submit(self, state: dict, questions: dict) -> JevResult: ...


class JevAgent:
    """Ask Jev three independent questions, then play the action choice or the math fallback."""

    def __init__(self, persona: Persona, client: DecisionClient | None = None) -> None:
        self.persona = persona
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
        questions = build_questions(self.persona, state["legal_actions"])
        result = self._client.submit(state, questions)
        action_answer = result.answers["action"]
        chosen = select_action(
            state["legal_actions"],
            state["pot_odds"],
            state["hero_equity_vs_continuing"],
            self.persona.fallback_equity_margin,
            action_answer["choice"],
            action_answer["confidence"],
            to_call=state["to_call"],
            spr=state["spr"],
            persona_id=self.persona.id,
            board_bonus=board_bonus_from_texture(state["board_texture"]),
        )
        return {
            "seat": seat,
            "persona_id": self.persona.id,
            "street": state["street"],
            "state": state,
            "answers": result.answers,
            "action": chosen["action"],
            "source": chosen["source"],
            "cost_usd": result.cost,
        }


def build_questions(persona: Persona, legal_actions: list[str]) -> dict:
    """Three questions about the same state. They are not chained."""
    return {
        "action": {
            "type": "choice",
            "instructions": _ACTION_INSTRUCTIONS,
            "criteria": persona.action_criteria(legal_actions),
        },
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
