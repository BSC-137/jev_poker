import { useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { actionWord, percent } from "./format";
import { CardFace } from "./view";

type PersonaVote = {
  id: string;
  display_name: string;
  color: string;
  action: string;
  confidence: number | null;
  probabilities: Record<string, number> | null;
  bluff: number | null;
  range_score: number | null;
  math_action: string;
};

type BluffVote = {
  bluff_spot: number;
  action: string;
  confidence: number | null;
  probabilities: Record<string, number> | null;
  range_score: number | null;
};

type VotesPayload = {
  street: string;
  hole_cards: string[];
  board: string[];
  pot: number;
  legal_actions: string[];
  personas: PersonaVote[];
  maniac_bluff: BluffVote[];
};

export function Votes() {
  const [votes, setVotes] = useState<VotesPayload | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let live = true;
    fetch("/api/votes")
      .then((response) => {
        if (!response.ok) {
          throw new Error(String(response.status));
        }
        return response.json();
      })
      .then((payload: VotesPayload) => {
        if (live) {
          setVotes(payload);
        }
      })
      .catch(() => {
        if (live) {
          setFailed(true);
        }
      });
    return () => {
      live = false;
    };
  }, []);

  if (!votes) {
    return <p className="quiet votes-wait">{failed ? "Votes are not loaded." : "Loading votes."}</p>;
  }

  return (
    <main className="votes" data-votes-ready="true">
      <h1>River votes</h1>
      <div className="votes-spot">
        <div>
          <p className="street-name">Hole cards</p>
          <div className="board">
            {votes.hole_cards.map((card, index) => (
              <CardFace key={`${card}-${index}`} card={card} />
            ))}
          </div>
        </div>
        <div>
          <p className="street-name">{votes.street}</p>
          <div className="board" data-votes-board="true" aria-label="Community cards">
            {votes.board.map((card, index) => (
              <CardFace key={`${card}-${index}`} card={card} />
            ))}
          </div>
        </div>
        <p className="pot">Pot {votes.pot.toLocaleString("en-US")}</p>
      </div>
      <div className="vote-grid">
        {votes.personas.map((persona) => (
          <article
            key={persona.id}
            className="vote-col"
            style={{ "--persona": persona.color } as CSSProperties}
          >
            <h2 style={{ color: persona.color }}>{persona.display_name}</h2>
            <p>Played: {actionWord(persona.action)}</p>
            <p>Confidence {persona.confidence === null ? "—" : percent(persona.confidence)}</p>
            <h3>Action</h3>
            <Bars rows={bars(votes.legal_actions, persona.probabilities)} />
            <h3>Bluff spot</h3>
            <p className="bluff">{persona.bluff === null ? "—" : percent(persona.bluff)}</p>
            <h3>Range advantage</h3>
            <p>Score {persona.range_score === null ? "—" : persona.range_score.toFixed(2)}</p>
            <p className="equity-rule">Equity rule: {persona.math_action}</p>
            {persona.id === "maniac"
              ? votes.maniac_bluff.map((row) => (
                  <section key={row.bluff_spot} className="bluff-bars">
                    <h3>Bluff {row.bluff_spot.toFixed(1)}</h3>
                    <p>Played: {actionWord(row.action)}</p>
                    <Bars rows={bars(votes.legal_actions, row.probabilities)} />
                  </section>
                ))
              : null}
          </article>
        ))}
      </div>
    </main>
  );
}

function bars(legal: string[], probabilities: Record<string, number> | null): { label: string; value: number }[] {
  if (!probabilities) {
    return [];
  }
  const order = legal.length > 0 ? legal : Object.keys(probabilities);
  return order.map((label) => ({ label, value: probabilities[label] ?? 0 }));
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
