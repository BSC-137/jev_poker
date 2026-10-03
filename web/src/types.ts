export type Source = "jev" | "math" | "math_error" | string;

export type Player = {
  seat: number;
  stack: number;
  folded: boolean;
  in_hand: boolean;
  all_in: boolean;
  position: string;
  hole_cards?: string[];
  persona_id: string;
  display_name: string;
  color: string;
};

export type TableSnap = {
  street: string;
  board: string[];
  pot: number;
  to_act: number | null;
  hand_over: boolean;
  players: Player[];
};

export type ChoiceAnswer = {
  choice?: string;
  confidence?: number;
  probabilities?: Record<string, number>;
};

export type NoulAnswer = {
  noul?: number;
};

export type ScoreAnswer = {
  score?: number;
  confidence?: number;
  probabilities?: Record<string, number>;
  legend?: Record<string, string>;
};

export type Answers = {
  action?: ChoiceAnswer;
  bluff_spot?: NoulAnswer;
  range_advantage?: ScoreAnswer;
} | null;

export type Decision = {
  seat: number;
  persona_id: string;
  street: string;
  action: string;
  source: Source;
  cost_usd: number;
  answers: Answers;
  state: {
    hero_equity_vs_random?: number;
    hero_equity_vs_continuing?: number;
    pot_odds?: number;
    spr?: number | null;
  };
};

export type Summary = {
  hands_played: number;
  stacks: number[];
  hands_won: Record<string, number>;
  decisions: Record<string, number>;
  mean_jev_confidence: number | null;
  total_usd: number;
  path?: string;
  error?: string;
};

export type StreamEvent = {
  seq: number;
  generation: number;
  type: "decision" | "street" | "showdown" | "finished";
  hand_number?: number;
  decision?: Decision;
  table?: TableSnap;
  board?: string[];
  street?: string;
  showdown_hole_cards?: { seat: number; persona_id: string; hole_cards: string[] }[] | null;
  pot_results?: { seat: number; amount: number }[];
  stacks?: number[];
  summary?: Summary;
};

export type StackPoint = {
  hand: number;
  stacks: number[];
};

export type ViewState = {
  generation: number | null;
  lastSeq: number;
  table: TableSnap | null;
  decision: Decision | null;
  ticker: { seat: number; persona: string; action: string; source: Source }[];
  history: StackPoint[];
  summary: Summary | null;
  handNumber: number | null;
};
