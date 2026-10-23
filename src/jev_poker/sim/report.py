"""Read tournament logs and write a markdown report. No network."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

_ACTIONS = ("fold", "check", "call", "raise_half_pot", "raise_pot", "all_in")
_PERSONAS = ("rock", "shark", "caller", "maniac")
_PASSIVE = frozenset({"fold", "check"})
_NO_RAISE = frozenset({"fold", "check", "call"})
_SPOTS = 8
_DISCLAIMER = (
    "Equity is Monte Carlo, the continuing range is a strength filter, "
    "and this is not a Nash equilibrium."
)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Summarize a Jev tournament log without using the network.")
    parser.add_argument("jev_jsonl", type=Path)
    parser.add_argument("math_jsonl", nargs="?", type=Path)
    args = parser.parse_args(argv)
    path = write_report(args.jev_jsonl, args.math_jsonl)
    print(path)


def write_report(
    jev_jsonl: Path | str,
    math_jsonl: Path | str | None = None,
    *,
    reports_dir: Path | str = "reports",
) -> Path:
    jev_path = Path(jev_jsonl)
    hands = _load(jev_path)
    math_hands = _load(Path(math_jsonl)) if math_jsonl is not None else None
    run_id = jev_path.resolve().parent.name
    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f"{run_id}.md"
    destination.write_text(_render(run_id, hands, math_hands), encoding="utf-8")
    return destination


def _load(path: Path) -> list[dict]:
    hands = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            hands.append(json.loads(line))
    return hands


def _render(run_id: str, hands: list[dict], math_hands: list[dict] | None) -> str:
    rows = [(hand, decision) for hand in hands for decision in hand.get("actions") or []]
    counts = {"jev": 0, "math": 0, "math_error": 0}
    confidences: list[float] = []
    elapsed: list[float] = []
    total_usd = 0.0
    frequencies = {persona: {action: 0 for action in _ACTIONS} for persona in _PERSONAS}
    for _hand, decision in rows:
        source = decision.get("source")
        if source in counts:
            counts[source] += 1
        else:
            counts[str(source)] = counts.get(str(source), 0) + 1
        confidence = _number(decision.get("confidence"))
        if confidence is not None:
            confidences.append(confidence)
        elapsed.append(_number(decision.get("elapsed_seconds")) or 0.0)
        total_usd += _number(decision.get("cost_usd")) or 0.0
        persona = decision.get("persona_id")
        action = decision.get("action")
        if persona in frequencies and action in frequencies[persona]:
            frequencies[persona][action] += 1

    jev_rows = [(hand, decision) for hand, decision in rows if decision.get("source") == "jev"]
    disagreements = [(hand, decision) for hand, decision in jev_rows if _disagrees(decision)]
    bluff_pool = [(hand, decision) for hand, decision in jev_rows if _bluff(decision) is not None and _bluff(decision) >= 0.6]
    bluff_hits = [(hand, decision) for hand, decision in bluff_pool if decision.get("action") in _PASSIVE]
    value_pool = [(hand, decision) for hand, decision in jev_rows if _score(decision) is not None and _score(decision) >= 3]
    value_hits = [(hand, decision) for hand, decision in value_pool if decision.get("action") in _NO_RAISE]
    spots = sorted(disagreements, key=_spot_key)[:_SPOTS]

    lines = [
        f"# {run_id}",
        "",
        _DISCLAIMER,
        "",
        "## Summary",
        "",
        f"Hands: {len(hands)}",
        f"Decisions: {len(rows)}",
        f"Sources: jev {counts['jev']}, math {counts['math']}, math_error {counts['math_error']}",
        f"Mean confidence: {_mean(confidences)}",
        f"Total USD: {total_usd:.6f}",
        f"Mean elapsed seconds: {_mean(elapsed)}",
        "",
        "## Action frequencies",
        "",
        "| Persona | " + " | ".join(_ACTIONS) + " |",
        "| --- | " + " | ".join("---" for _ in _ACTIONS) + " |",
    ]
    for persona in _PERSONAS:
        cells = " | ".join(str(frequencies[persona][action]) for action in _ACTIONS)
        lines.append(f"| {persona} | {cells} |")
    lines.extend(
        [
            "",
            "## Disagreement",
            "",
            "Jev decisions whose action differs from math_action: "
            + _rate(len(disagreements), len(jev_rows))
            + ".",
            "",
            "## Bluff split",
            "",
            "Source jev, bluff_spot >= 0.6, and the action is fold or check: "
            + _rate(len(bluff_hits), len(bluff_pool))
            + " of jev decisions with bluff_spot >= 0.6.",
            "",
            "## Value split",
            "",
            "Source jev, range_advantage_score >= 3, and the action is fold, check, or call: "
            + _rate(len(value_hits), len(value_pool))
            + " of jev decisions with range_advantage_score >= 3.",
            "",
            "## Disagreement spots",
            "",
        ]
    )
    if not spots:
        lines.append("None.")
    for hand, decision in spots:
        lines.extend(_spot(hand, decision))
    if math_hands is not None:
        lines.extend(
            [
                "",
                "## Stacks",
                "",
                "| Run | Seed | Final stacks |",
                "| --- | --- | --- |",
                f"| Jev ({run_id}) | {_seed(hands)} | {_stacks(hands)} |",
                f"| Math | {_seed(math_hands)} | {_stacks(math_hands)} |",
                "",
            ]
        )
    else:
        lines.append("")
    return "\n".join(lines)


def _spot(hand: dict, decision: dict) -> list[str]:
    state = decision.get("state") if isinstance(decision.get("state"), dict) else {}
    hero = state.get("hero") if isinstance(state.get("hero"), dict) else {}
    hole = hero.get("hole_cards") or []
    board = state.get("board") or []
    probabilities = _probabilities(decision)
    return [
        f"### Hand {hand.get('hand_number')} {decision.get('persona_id')} {decision.get('street')}",
        "",
        f"Hole cards: {_cards(hole)}",
        f"Board: {_cards(board)}",
        f"Pot: {state.get('pot')}",
        f"To call: {state.get('to_call')}",
        f"Pot odds: {state.get('pot_odds')}",
        f"Equity vs random: {state.get('hero_equity_vs_random')}",
        f"Equity vs continuing: {state.get('hero_equity_vs_continuing')}",
        f"Fold to bet: {_fold_to_bet(state)}",
        f"Action: {decision.get('action')}",
        f"Math action: {decision.get('math_action')}",
        f"Confidence: {decision.get('confidence')}",
        f"Action probabilities: {probabilities}",
        f"Bluff spot: {_bluff(decision)}",
        f"Range score: {_score(decision)}",
        "",
    ]


def _spot_key(item: tuple[dict, dict]) -> tuple:
    _hand, decision = item
    state = decision.get("state") if isinstance(decision.get("state"), dict) else {}
    pot = _number(state.get("pot")) or 0.0
    hand_number = _hand.get("hand_number")
    if not isinstance(hand_number, int):
        hand_number = 0
    seat = decision.get("seat")
    if not isinstance(seat, int):
        seat = 0
    return (-pot, hand_number, seat)


def _disagrees(decision: dict) -> bool:
    math_choice = decision.get("math_action")
    return isinstance(math_choice, str) and math_choice != decision.get("action")


def _bluff(decision: dict) -> float | None:
    return _nested_number(decision, "bluff_spot", "noul")


def _score(decision: dict) -> float | None:
    return _nested_number(decision, "range_advantage", "score")


def _nested_number(decision: dict, answer: str, key: str) -> float | None:
    answers = decision.get("answers")
    if not isinstance(answers, dict):
        return None
    block = answers.get(answer)
    if not isinstance(block, dict):
        return None
    return _number(block.get(key))


def _probabilities(decision: dict) -> str:
    answers = decision.get("answers")
    action = answers.get("action") if isinstance(answers, dict) else None
    probabilities = action.get("probabilities") if isinstance(action, dict) else None
    if not isinstance(probabilities, dict) or not probabilities:
        return "n/a"
    return ", ".join(f"{name} {value}" for name, value in probabilities.items())


def _fold_to_bet(state: dict) -> str:
    parts = []
    for opponent in state.get("opponents") or []:
        if not isinstance(opponent, dict) or not opponent.get("in_hand"):
            continue
        stats = opponent.get("stats") if isinstance(opponent.get("stats"), dict) else {}
        value = stats.get("fold_to_bet")
        shown = "n/a" if value is None else value
        parts.append(f"seat {opponent.get('seat')}: {shown}")
    return ", ".join(parts) if parts else "n/a"


def _cards(cards: object) -> str:
    if not isinstance(cards, list) or not cards:
        return "none"
    return " ".join(str(card) for card in cards)


def _seed(hands: list[dict]) -> str:
    if not hands:
        return "n/a"
    return str(hands[0].get("seed", "n/a"))


def _stacks(hands: list[dict]) -> str:
    if not hands or not isinstance(hands[-1].get("stacks"), list):
        return "n/a"
    return ", ".join(str(stack) for stack in hands[-1]["stacks"])


def _rate(count: int, total: int) -> str:
    if total == 0:
        return f"{count} / {total} (n/a)"
    return f"{count} / {total} ({count / total:.1%})"


def _mean(values: list[float]) -> str:
    if not values:
        return "n/a"
    return f"{sum(values) / len(values):.3f}"


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


if __name__ == "__main__":
    main()
