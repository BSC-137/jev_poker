"""One frozen river spot, judged once by each persona, then two Maniac bluff bars."""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from jev_poker.agents.jev_agent import (
    JevAgent,
    build_action_questions,
    math_action,
    prior_judgments,
    resolve_action,
)
from jev_poker.agents.personas import MANIAC, PERSONAS, Persona
from jev_poker.jev.client import JevClient, JevError, JevTransportError

_PROBE_QUESTIONS = {
    "probe": {
        "type": "noul",
        "instructions": "Is this a probe?",
        "criteria": {"false": "no", "true": "yes"},
    }
}
_FORCED_BLUFFS = (0.1, 0.9)


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "jev_poker").is_dir():
            return parent
    return Path.cwd()


def frozen_log_path() -> Path:
    return repo_root() / "recordings" / "seed2-four-hands.jsonl"


def votes_path() -> Path:
    return repo_root() / "recordings" / "river-votes.json"


def load_frozen(path: Path | str) -> dict:
    """The hand-2 river decision where Maniac raise-half-pots."""
    found = None
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        hand = json.loads(line)
        for action in hand.get("actions") or []:
            if (
                hand.get("hand_number") == 2
                and action.get("street") == "river"
                and action.get("persona_id") == "maniac"
                and action.get("action") == "raise_half_pot"
            ):
                if found is not None:
                    raise ValueError("more than one frozen river decision")
                found = dict(action)
                found["hand_number"] = hand["hand_number"]
    if found is None:
        raise ValueError("frozen river decision was not found")
    return found


def prepare_state(state: dict, persona: Persona) -> dict:
    """Copy the logged spot, name the persona, and drop any prior judgments."""
    prepared = copy.deepcopy(state)
    prepared.pop("prior_judgments", None)
    prepared["persona"] = persona.to_state()
    return prepared


def run_votes(client, decision: dict) -> dict:
    """Four two-call votes, then two Maniac action calls with the bluff forced."""
    state = decision["state"]
    legal = list(state["legal_actions"])
    rows = []
    maniac_answers = None
    for persona in PERSONAS:
        prepared = prepare_state(state, persona)
        if list(prepared["legal_actions"]) != legal:
            raise ValueError("legal actions changed")
        record = JevAgent(persona, client)._ask(
            prepared,
            prepared["hero"]["seat"],
            math_action(persona, prepared),
        )
        rows.append(_persona_row(persona, record))
        if persona.id == "maniac":
            maniac_answers = record["answers"]
    if maniac_answers is None:
        raise ValueError("maniac did not vote")
    kept = prior_judgments(maniac_answers)
    forced = [
        _forced_bluff(client, state, kept, bluff)
        for bluff in _FORCED_BLUFFS
    ]
    hero = state["hero"]
    return {
        "hand_number": decision.get("hand_number"),
        "street": state["street"],
        "hole_cards": list(hero["hole_cards"]),
        "board": list(state["board"]),
        "pot": state["pot"],
        "legal_actions": legal,
        "personas": rows,
        "maniac_bluff": forced,
    }


def probe(client) -> int:
    """One systemone call. A returned result is HTTP 200."""
    try:
        client.submit({"probe": True}, _PROBE_QUESTIONS)
    except JevTransportError as exc:
        print(f"probe HTTP {exc.status}")
        return exc.status if exc.status != 200 else 0
    except JevError:
        print("probe failed")
        return 0
    return 200


def main() -> None:
    client = JevClient()
    if probe(client) != 200:
        raise SystemExit(1)
    payload = run_votes(client, load_frozen(frozen_log_path()))
    path = votes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    for row in payload["personas"]:
        print(f"{row['id']} {row['action']}")


def _persona_row(persona: Persona, record: dict) -> dict:
    answers = record.get("answers") if isinstance(record.get("answers"), dict) else {}
    action = answers.get("action") if isinstance(answers.get("action"), dict) else {}
    bluff = answers.get("bluff_spot") if isinstance(answers.get("bluff_spot"), dict) else {}
    advantage = answers.get("range_advantage") if isinstance(answers.get("range_advantage"), dict) else {}
    return {
        "id": persona.id,
        "display_name": persona.display_name,
        "color": persona.color,
        "action": record["action"],
        "confidence": record["confidence"],
        "probabilities": action.get("probabilities"),
        "bluff": bluff.get("noul"),
        "range_score": advantage.get("score"),
        "math_action": record["math_action"],
    }


def _forced_bluff(client, state: dict, kept: dict, bluff: float) -> dict:
    judged = prepare_state(state, MANIAC)
    judged["prior_judgments"] = {
        "bluff_spot": bluff,
        "range_advantage_score": kept["range_advantage_score"],
        "range_advantage_label": kept["range_advantage_label"],
    }
    result = client.submit(judged, build_action_questions(MANIAC, judged["legal_actions"]))
    played, confidence, _source = resolve_action(
        judged["legal_actions"],
        result.answers.get("action"),
        math_action(MANIAC, judged),
    )
    action = result.answers.get("action") if isinstance(result.answers.get("action"), dict) else {}
    return {
        "bluff_spot": bluff,
        "action": played,
        "confidence": confidence,
        "probabilities": action.get("probabilities"),
        "range_score": kept["range_advantage_score"],
    }


if __name__ == "__main__":
    main()
    sys.exit(0)
