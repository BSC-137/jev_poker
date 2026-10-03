import type { CSSProperties } from "react";
import type { Decision, Player, StackPoint, Summary, TableSnap } from "./types";
import { actionWord, percent, playersInSeatOrder, rangeRows, sprText } from "./format";

const SUITS: Record<string, string> = { s: "♠", h: "♥", d: "♦", c: "♣" };

export function CardFace({ card }: { card: string }) {
  const rank = card[0] === "T" ? "10" : card[0];
  const suit = card[1] ?? "";
  const red = suit === "h" || suit === "d";
  return (
    <div className={red ? "card red" : "card"}>
      {rank}
      {SUITS[suit] ?? suit}
    </div>
  );
}

export function Seat({
  player,
  toAct,
  fallback,
}: {
  player: Player;
  toAct: boolean;
  fallback: boolean;
}) {
  const folded = player.folded;
  const out = !player.in_hand && player.stack <= 0;
  const className = ["seat", `seat-${player.seat}`, toAct ? "to-act" : "", folded ? "folded" : "", out ? "out" : ""]
    .filter(Boolean)
    .join(" ");
  return (
    <article className={className} style={{ "--persona": player.color } as CSSProperties}>
      {fallback ? <span className="badge">math fallback</span> : null}
      <div className="seat-head">
        <strong className="persona" style={{ color: player.color }}>
          {player.display_name}
        </strong>
        <span className="position">{player.position}</span>
      </div>
      <p className="chips">{player.stack.toLocaleString("en-US")} chips</p>
      <div className="holes">
        {(player.hole_cards ?? []).map((card) => (
          <CardFace key={card} card={card} />
        ))}
      </div>
      {folded ? <p className="mark">Folded</p> : null}
      {out ? <p className="mark">Out</p> : null}
    </article>
  );
}

export function Felt({ table, fallbackSeat }: { table: TableSnap | null; fallbackSeat: number | null }) {
  const players = playersInSeatOrder(table);
  const board = table?.board ?? [];
  return (
    <div className="table-stage">
      {players.map((player) => (
        <Seat
          key={player.seat}
          player={player}
          toAct={table?.to_act === player.seat && !table.hand_over}
          fallback={fallbackSeat === player.seat}
        />
      ))}
      <div className="felt">
        <p className="street-name">{table?.street ?? "waiting"}</p>
        <div className="board" aria-label="Community cards">
          {board.map((card) => (
            <CardFace key={card} card={card} />
          ))}
          {Array.from({ length: Math.max(0, 5 - board.length) }, (_, index) => (
            <div key={`empty-${index}`} className="card-slot" />
          ))}
        </div>
        <p className="pot">Pot {table ? table.pot.toLocaleString("en-US") : "0"}</p>
      </div>
    </div>
  );
}

function Bars({ rows }: { rows: { label: string; value: number }[] }) {
  if (rows.length === 0) {
    return <p className="quiet">No probabilities returned</p>;
  }
  return (
    <div className="bars">
      {rows.map((row) => (
        <div className="bar-row" key={row.label}>
          <span>{row.label.replaceAll("_", " ")}</span>
          <div className="bar-track">
            <div className="bar-fill" style={{ width: `${Math.max(0, Math.min(1, row.value)) * 100}%` }} />
          </div>
          <span className="bar-value">{percent(row.value)}</span>
        </div>
      ))}
    </div>
  );
}

export function DecisionPanel({
  decision,
  player,
}: {
  decision: Decision | null;
  player: Player | undefined;
}) {
  const answers = decision?.answers;
  const actionRows = Object.entries(answers?.action?.probabilities ?? {}).map(([label, value]) => ({
    label,
    value,
  }));
  return (
    <aside className="panel">
      <h2>Last decision</h2>
      {decision && player ? (
        <>
          <strong className="persona" style={{ color: player.color }}>
            {player.display_name}
          </strong>
          <p>
            {actionWord(decision.action)} on the {decision.street}
          </p>
          <span className="source">{decision.source}</span>
          <h3>Action</h3>
          <Bars rows={actionRows} />
          <h3>Bluff spot</h3>
          <p className="bluff">
            {answers?.bluff_spot?.noul === undefined ? "—" : percent(answers.bluff_spot.noul)}
          </p>
          <h3>Range advantage</h3>
          <p>
            Score{" "}
            {answers?.range_advantage?.score === undefined
              ? "—"
              : answers.range_advantage.score.toFixed(2)}
          </p>
          <Bars rows={rangeRows(answers?.range_advantage)} />
          <dl className="strip">
            <div>
              <dt>Equity vs random</dt>
              <dd>{percent(decision.state.hero_equity_vs_random)}</dd>
            </div>
            <div>
              <dt>Equity vs continuing</dt>
              <dd>{percent(decision.state.hero_equity_vs_continuing)}</dd>
            </div>
            <div>
              <dt>Pot odds</dt>
              <dd>{percent(decision.state.pot_odds)}</dd>
            </div>
            <div>
              <dt>SPR</dt>
              <dd>{sprText(decision.state.spr)}</dd>
            </div>
          </dl>
        </>
      ) : (
        <p className="quiet">Waiting for a decision.</p>
      )}
    </aside>
  );
}

export function ChipChart({ history, players }: { history: StackPoint[]; players: Player[] }) {
  const width = 560;
  const height = 160;
  const pad = 16;
  const values = history.flatMap((point) => point.stacks);
  const peak = Math.max(2000, ...values);
  const colors = players.length
    ? playersInSeatOrder({ players, street: "", board: [], pot: 0, to_act: null, hand_over: false }).map(
        (player) => player.color,
      )
    : ["#94a3b8", "#14b8a6", "#38bdf8", "#f43f5e"];
  const names = players.length
    ? playersInSeatOrder({ players, street: "", board: [], pot: 0, to_act: null, hand_over: false }).map(
        (player) => player.display_name,
      )
    : ["Rock", "Shark", "Caller", "Maniac"];

  function x(index: number): number {
    if (history.length <= 1) {
      return pad;
    }
    return pad + (index / (history.length - 1)) * (width - pad * 2);
  }

  function y(stack: number): number {
    return height - pad - (stack / peak) * (height - pad * 2);
  }

  return (
    <div>
      <h2>Chips</h2>
      <svg className="chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Chip counts across hands">
        {[0, 1, 2, 3].map((seat) => {
          const points = history
            .map((point, index) => `${x(index)},${y(point.stacks[seat] ?? 0)}`)
            .join(" ");
          return (
            <polyline
              key={seat}
              fill="none"
              stroke={colors[seat] ?? "#d7b56d"}
              strokeWidth="2.5"
              points={points}
            />
          );
        })}
      </svg>
      <div className="legend">
        {names.map((name, index) => (
          <span key={name}>
            <i className="swatch" style={{ background: colors[index] }} />
            {name}
          </span>
        ))}
      </div>
    </div>
  );
}

export function SummaryBlock({ summary }: { summary: Summary }) {
  const total = summary.stacks.reduce((sum, stack) => sum + stack, 0);
  const mean =
    summary.mean_jev_confidence === null ? "n/a" : summary.mean_jev_confidence.toFixed(3);
  const won = Object.entries(summary.hands_won)
    .map(([name, count]) => `${name} ${count}`)
    .join(", ");
  return (
    <div className="summary">
      <h2>Tournament finished</h2>
      {summary.error ? <p className="error">{summary.error}</p> : null}
      <p>Hands played: {summary.hands_played}</p>
      <p>Final stacks: {summary.stacks.join(", ")}</p>
      <p>Total chips: {total.toLocaleString("en-US")}</p>
      <p>Hands won: {won || "—"}</p>
      <p>
        Decisions: jev {summary.decisions.jev ?? 0}, math {summary.decisions.math ?? 0}, math_error{" "}
        {summary.decisions.math_error ?? 0}
      </p>
      <p>Mean Jev confidence: {mean}</p>
      <p>Total USD: {summary.total_usd.toFixed(6)}</p>
    </div>
  );
}
