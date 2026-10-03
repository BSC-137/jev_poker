"""Play rock, shark, caller, and maniac against each other and log each hand."""

from __future__ import annotations

import copy
import json
import random
from datetime import datetime
from pathlib import Path

from jev_poker.agents.jev_agent import JevAgent
from jev_poker.agents.personas import PERSONAS
from jev_poker.agents.policy import board_bonus_from_texture, decide as select_action
from jev_poker.engine.game import SEATS, STARTING_STACK, Game
from jev_poker.math.state import decision_state

SEAT_PERSONAS = PERSONAS
PERSONA_IDS = tuple(persona.id for persona in SEAT_PERSONAS)
_SOURCES = ("jev", "math", "math_error")
_ACTION_LIMIT = 200


def play_hand(
    seed: int,
    *,
    client=None,
    game: Game | None = None,
    agents: list[JevAgent] | None = None,
    iterations: int = 300,
    rng: random.Random | None = None,
) -> dict:
    """Play one hand. ``seed`` labels the hand and builds a table when ``game`` is omitted."""
    table = Game(seed=seed) if game is None else game
    seats = agents if agents is not None else _agents(client)
    stream = rng if rng is not None else random.Random(seed)
    return _play_hand(table, seats, seed=seed, iterations=iterations, rng=stream)


def play_tournament(
    hands: int,
    seed: int,
    *,
    client=None,
    iterations: int = 300,
    runs_root: Path | str = "runs",
    run_dir: Path | str | None = None,
    on_event=None,
    between_hands=None,
) -> dict:
    """Play up to ``hands`` hands, or stop when only one seat still has chips.

    Writes ``runs/<timestamp>/hands.jsonl`` under ``runs_root``. ``on_event``
    receives street, decision, showdown, and finished payloads for a spectator.
    ``between_hands`` runs after a hand when another hand is still going to be dealt.
    """
    if hands < 1:
        raise ValueError("hands must be at least 1")
    table = Game(seed=seed)
    agents = _agents(client)
    rng = random.Random(seed)
    path = _log_path(Path(runs_root), Path(run_dir) if run_dir is not None else None)
    played: list[dict] = []
    with path.open("w", encoding="utf-8") as handle:
        while len(played) < hands and _seats_with_chips(table) >= 2:
            record = _play_hand(
                table,
                agents,
                seed=seed,
                iterations=iterations,
                rng=rng,
                on_event=on_event,
            )
            played.append(record)
            handle.write(json.dumps(record) + "\n")
            handle.flush()
            another = len(played) < hands and _seats_with_chips(table) >= 2
            if another and between_hands is not None:
                between_hands()
    summary = _summary(played, path)
    _emit(
        on_event,
        {"type": "finished", "id": path.parent.name, "summary": summary},
    )
    return {"hands": played, "summary": summary, "path": path}


def format_summary(summary: dict) -> str:
    """Console summary for a finished tournament."""
    stacks = ", ".join(
        f"{persona_id} {summary['stacks'][index]}"
        for index, persona_id in enumerate(PERSONA_IDS)
    )
    won = ", ".join(f"{persona_id} {summary['hands_won'][persona_id]}" for persona_id in PERSONA_IDS)
    decisions = summary["decisions"]
    counted = ", ".join(f"{source} {decisions[source]}" for source in _SOURCES)
    mean = summary["mean_jev_confidence"]
    mean_text = "n/a" if mean is None else f"{mean:.3f}"
    return "\n".join(
        [
            f"Hands played: {summary['hands_played']}",
            f"Final stacks: {stacks}",
            f"Hands won: {won}",
            f"Decisions: {counted}",
            f"Mean Jev confidence: {mean_text}",
            f"Total USD: {summary['total_usd']:.6f}",
            f"Log: {summary['path']}",
        ]
    )


def _agents(client) -> list[JevAgent]:
    return [JevAgent(persona, client) for persona in SEAT_PERSONAS]


def _play_hand(
    game: Game,
    agents: list[JevAgent],
    *,
    seed: int,
    iterations: int,
    rng: random.Random,
    on_event=None,
) -> dict:
    if len(agents) != SEATS:
        raise ValueError("the table needs one agent per seat")
    game.new_hand()
    _emit(on_event, _street_event(game))
    seen_board = len(game.board)
    actions: list[dict] = []
    for _ in range(_ACTION_LIMIT):
        if game.is_hand_over():
            break
        seat = game.to_act
        if seat is None:
            raise RuntimeError("hand has no player to act")
        decision = _decide(agents[seat], game, seat, iterations, rng)
        legal = [action.value for action in game.legal_actions(seat)]
        if decision["action"] not in legal:
            decision["action"] = legal[0]
            decision["source"] = "math_error"
        game.apply(seat, decision["action"])
        logged = _public_decision(decision)
        actions.append(logged)
        _emit(
            on_event,
            {
                "type": "decision",
                "hand_number": game.hand_number,
                "decision": logged,
                "table": _spectator_table(game),
            },
        )
        if len(game.board) != seen_board:
            seen_board = len(game.board)
            _emit(on_event, _street_event(game))
    else:
        raise RuntimeError("hand exceeded the action limit")
    if not game.is_hand_over():
        raise RuntimeError("hand did not finish")
    record = {
        "seed": seed,
        "hand_number": game.hand_number,
        "board": list(game.board),
        "actions": actions,
        "showdown_hole_cards": _showdown_holes(game),
        "pot_results": game.winners(),
        "stacks": [player.stack for player in game.players],
        "cost_usd": sum(action["cost_usd"] for action in actions),
    }
    if game.street == "showdown":
        _emit(
            on_event,
            {
                "type": "showdown",
                "hand_number": game.hand_number,
                "board": record["board"],
                "showdown_hole_cards": record["showdown_hole_cards"],
                "pot_results": record["pot_results"],
                "stacks": record["stacks"],
                "table": _spectator_table(game),
            },
        )
    return record


def _emit(on_event, event: dict) -> None:
    if on_event is not None:
        on_event(event)


def _spectator_table(game: Game) -> dict:
    """Public table plus every seat's hole cards, for the local spectator only."""
    public = game.public_state()
    rows = {row["seat"]: row for row in public["players"]}
    for player in game.players:
        persona = SEAT_PERSONAS[player.seat]
        row = rows[player.seat]
        row["hole_cards"] = list(player.hole)
        row["persona_id"] = persona.id
        row["display_name"] = persona.display_name
        row["color"] = persona.color
    return public


def _street_event(game: Game) -> dict:
    return {
        "type": "street",
        "hand_number": game.hand_number,
        "street": game.street,
        "board": list(game.board),
        "table": _spectator_table(game),
    }


def _log_path(runs_root: Path, run_dir: Path | None) -> Path:
    if run_dir is None:
        return _jsonl_path(runs_root)
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / "hands.jsonl"


def _decide(agent: JevAgent, game: Game, seat: int, iterations: int, rng: random.Random) -> dict:
    try:
        return agent.decide(game, seat, iterations=iterations, rng=rng)
    except Exception:
        return _math_error(agent, game, seat, iterations, rng)


def _math_error(agent: JevAgent, game: Game, seat: int, iterations: int, rng: random.Random) -> dict:
    state = decision_state(
        game,
        seat,
        continuing_fraction=agent.persona.continuing_fraction,
        iterations=iterations,
        rng=rng,
    )
    state["persona"] = agent.persona.to_state()
    chosen = select_action(
        state["legal_actions"],
        state["pot_odds"],
        state["hero_equity_vs_continuing"],
        agent.persona.fallback_equity_margin,
        None,
        None,
        to_call=state["to_call"],
        spr=state["spr"],
        persona_id=agent.persona.id,
        board_bonus=board_bonus_from_texture(state["board_texture"]),
    )
    return {
        "seat": seat,
        "persona_id": agent.persona.id,
        "street": state["street"],
        "state": state,
        "answers": None,
        "action": chosen["action"],
        "source": "math_error",
        "cost_usd": 0.0,
    }


def _public_decision(record: dict) -> dict:
    """Decision record with every seat's hole cards except the actor's removed."""
    logged = copy.deepcopy(record)
    state = logged.get("state")
    if not isinstance(state, dict):
        return logged
    for opponent in state.get("opponents") or []:
        if isinstance(opponent, dict):
            opponent.pop("hole_cards", None)
            opponent.pop("hole", None)
    state.pop("hole_cards", None)
    return logged


def _showdown_holes(game: Game) -> list[dict] | None:
    if game.street != "showdown":
        return None
    holes = []
    for player in game.players:
        if player.in_hand and not player.folded and player.hole:
            holes.append(
                {
                    "seat": player.seat,
                    "persona_id": PERSONA_IDS[player.seat],
                    "hole_cards": list(player.hole),
                }
            )
    return holes


def _seats_with_chips(game: Game) -> int:
    return sum(player.stack > 0 for player in game.players)


def _jsonl_path(root: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    directory = root / stamp
    counter = 0
    while directory.exists():
        counter += 1
        directory = root / f"{stamp}-{counter}"
    directory.mkdir(parents=True)
    return directory / "hands.jsonl"


def _summary(hands: list[dict], path: Path) -> dict:
    stacks = list(hands[-1]["stacks"]) if hands else [player_stack for player_stack in _starting_stacks()]
    wins = {persona_id: 0 for persona_id in PERSONA_IDS}
    decisions = {source: 0 for source in _SOURCES}
    confidences: list[float] = []
    total_usd = 0.0
    for hand in hands:
        total_usd += hand["cost_usd"]
        for result in hand["pot_results"]:
            wins[PERSONA_IDS[result["seat"]]] += 1
        for action in hand["actions"]:
            source = action["source"]
            if source not in decisions:
                decisions[source] = 0
            decisions[source] += 1
            confidence = _confidence(action)
            if confidence is not None:
                confidences.append(confidence)
    mean = sum(confidences) / len(confidences) if confidences else None
    return {
        "hands_played": len(hands),
        "stacks": stacks,
        "hands_won": wins,
        "decisions": {source: decisions[source] for source in _SOURCES},
        "mean_jev_confidence": mean,
        "total_usd": total_usd,
        "path": str(path),
    }


def _confidence(action: dict) -> float | None:
    answers = action.get("answers")
    if not isinstance(answers, dict):
        return None
    choice = answers.get("action")
    if not isinstance(choice, dict):
        return None
    value = choice.get("confidence")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _starting_stacks() -> list[int]:
    return [STARTING_STACK] * SEATS
