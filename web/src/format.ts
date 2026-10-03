import type { Player, ScoreAnswer, StackPoint, TableSnap } from "./types";

export const STARTING_STACKS = [2000, 2000, 2000, 2000];

export const RANGE_LEVELS = [
  "Clear disadvantage",
  "Slight disadvantage",
  "Neutral",
  "Slight advantage",
  "Clear advantage",
];

const ACTION_WORDS: Record<string, string> = {
  fold: "folds",
  check: "checks",
  call: "calls",
  raise_half_pot: "raises half pot",
  raise_pot: "raises pot",
  all_in: "goes all in",
};

export function actionWord(action: string): string {
  return ACTION_WORDS[action] ?? action.replaceAll("_", " ");
}

export function percent(value: number | undefined): string {
  if (value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return `${(value * 100).toFixed(1)}%`;
}

export function sprText(value: number | null | undefined): string {
  if (value === null || value === undefined || Number.isNaN(value)) {
    return "—";
  }
  return value.toFixed(2);
}

export function isFallback(source: string | undefined): boolean {
  return source === "math" || source === "math_error";
}

export function playersInSeatOrder(table: TableSnap | null): Player[] {
  if (!table) {
    return [];
  }
  return [...table.players].sort((left, right) => left.seat - right.seat);
}

export function stacksFromTable(table: TableSnap): number[] {
  return playersInSeatOrder(table).map((player) => player.stack);
}

export function withHandStacks(history: StackPoint[], hand: number, stacks: number[]): StackPoint[] {
  if (history.some((point) => point.hand === hand)) {
    return history;
  }
  return [...history, { hand, stacks: [...stacks] }];
}

export function rangeRows(answer: ScoreAnswer | undefined): { label: string; value: number }[] {
  if (!answer?.probabilities) {
    return [];
  }
  const legend = answer.legend ?? {};
  return Object.keys(answer.probabilities)
    .sort((left, right) => Number(left) - Number(right))
    .map((key) => ({
      label: legend[key] ?? RANGE_LEVELS[Number(key)] ?? key,
      value: answer.probabilities?.[key] ?? 0,
    }));
}

export function emptyHistory(): StackPoint[] {
  return [{ hand: 0, stacks: [...STARTING_STACKS] }];
}
