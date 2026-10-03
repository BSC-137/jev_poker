import { useEffect, useReducer, useRef, useState } from "react";
import type { FormEvent } from "react";
import { emptyHistory, isFallback, playersInSeatOrder, stacksFromTable, withHandStacks } from "./format";
import type { StreamEvent, ViewState } from "./types";
import { ChipChart, DecisionPanel, Felt, SummaryBlock } from "./view";

const initialView: ViewState = {
  generation: null,
  lastSeq: -1,
  table: null,
  decision: null,
  ticker: [],
  history: emptyHistory(),
  summary: null,
  handNumber: null,
};

function reduceView(state: ViewState, event: StreamEvent): ViewState {
  if (state.generation !== event.generation) {
    state = { ...initialView, generation: event.generation, history: emptyHistory() };
  }
  if (event.seq <= state.lastSeq) {
    return state;
  }
  const next: ViewState = { ...state, lastSeq: event.seq };
  if (event.table) {
    next.table = event.table;
  }
  if (event.type === "street") {
    if (event.hand_number !== state.handNumber) {
      next.ticker = [];
    }
    next.handNumber = event.hand_number ?? next.handNumber;
  }
  if (event.type === "decision" && event.decision) {
    next.decision = event.decision;
    next.handNumber = event.hand_number ?? next.handNumber;
    const player = event.table?.players.find((seat) => seat.seat === event.decision?.seat);
    next.ticker = [
      ...next.ticker,
      {
        seat: event.decision.seat,
        persona: player?.display_name ?? event.decision.persona_id,
        action: event.decision.action,
        source: event.decision.source,
      },
    ];
  }
  if (event.type === "showdown") {
    next.handNumber = event.hand_number ?? next.handNumber;
    if (event.hand_number !== undefined && event.stacks) {
      next.history = withHandStacks(next.history, event.hand_number, event.stacks);
    }
  }
  if (event.table?.hand_over && event.hand_number !== undefined) {
    const stacks = event.stacks ?? stacksFromTable(event.table);
    next.history = withHandStacks(next.history, event.hand_number, stacks);
  }
  if (event.type === "finished" && event.summary) {
    next.summary = event.summary;
    if (event.summary.stacks.length === 4) {
      const hand = next.handNumber ?? next.history.length - 1;
      next.history = withHandStacks(next.history, hand, event.summary.stacks);
    }
  }
  return next;
}

export function App() {
  const [view, dispatch] = useReducer(
    (state: ViewState, event: StreamEvent) => reduceView(state, event),
    initialView,
  );
  const [seed, setSeed] = useState("1");
  const [hands, setHands] = useState("10");
  const [pause, setPause] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pauseRef = useRef(false);
  const sourceRef = useRef<EventSource | null>(null);

  function openStream() {
    sourceRef.current?.close();
    const source = new EventSource("/api/tournament/stream");
    sourceRef.current = source;
    const onEvent = (message: Event) => {
      const payload = JSON.parse((message as MessageEvent).data) as StreamEvent;
      dispatch(payload);
      if (payload.type === "finished") {
        setRunning(false);
        source.close();
      }
    };
    for (const name of ["decision", "street", "showdown", "finished"]) {
      source.addEventListener(name, onEvent);
    }
  }

  useEffect(() => {
    openStream();
    return () => sourceRef.current?.close();
  }, []);

  const players = playersInSeatOrder(view.table);
  const actor = players.find((player) => player.seat === view.decision?.seat);
  const fallbackSeat =
    view.decision && isFallback(view.decision.source) ? view.decision.seat : null;
  const waiting = pause && running && Boolean(view.table?.hand_over) && !view.summary;

  async function start(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setRunning(true);
    if (!sourceRef.current || sourceRef.current.readyState !== EventSource.OPEN) {
      openStream();
    }
    const response = await fetch("/api/tournament", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        hands: Number(hands),
        seed: Number(seed),
        pause_between_hands: pauseRef.current,
      }),
    });
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as { detail?: string };
      setError(typeof body.detail === "string" ? body.detail : "Could not start the tournament");
      setRunning(false);
    }
  }

  async function resume() {
    await fetch("/api/tournament/pause", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resume: true }),
    });
  }

  function onPauseChange(checked: boolean) {
    pauseRef.current = checked;
    setPause(checked);
    if (running) {
      void fetch("/api/tournament/pause", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pause_between_hands: checked, resume: !checked }),
      });
    }
  }

  return (
    <main className="app">
      <header className="topbar">
        <h1 className="brand">
          Jev <span>Poker</span>
        </h1>
        <form className="controls" onSubmit={(event) => void start(event)}>
          <label>
            Seed
            <input
              type="number"
              value={seed}
              onChange={(event) => setSeed(event.target.value)}
              required
            />
          </label>
          <label>
            Hands
            <input
              type="number"
              min={1}
              value={hands}
              onChange={(event) => setHands(event.target.value)}
              required
            />
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={pause}
              onChange={(event) => onPauseChange(event.target.checked)}
            />
            Pause between hands
          </label>
          <button type="submit" disabled={running}>
            Start
          </button>
          {waiting ? (
            <button type="button" onClick={() => void resume()}>
              Next hand
            </button>
          ) : null}
        </form>
      </header>
      {error ? <p className="error">{error}</p> : null}
      <div className="layout">
        <Felt table={view.table} fallbackSeat={fallbackSeat} />
        <DecisionPanel decision={view.decision} player={actor} />
      </div>
      <section className="bottom">
        <div>
          <h2>This hand</h2>
          <ul className="ticker">
            {view.ticker.map((item, index) => (
              <li key={`${item.seat}-${index}`}>
                <span>{item.persona}</span>
                <span>{item.action.replaceAll("_", " ")}</span>
              </li>
            ))}
          </ul>
        </div>
        <ChipChart history={view.history} players={players} />
      </section>
      {view.summary ? <SummaryBlock summary={view.summary} /> : null}
    </main>
  );
}
