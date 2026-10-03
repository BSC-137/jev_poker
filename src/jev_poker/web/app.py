"""FastAPI spectator: start a tournament, stream it, and read saved logs."""

from __future__ import annotations

import asyncio
import json
import re
import threading
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from jev_poker.engine.game import SEATS, STARTING_STACK
from jev_poker.jev.client import JevClient, JevError, JevResult
from jev_poker.sim.tournament import play_tournament

_RUN_ID = re.compile(r"[A-Za-z0-9_-]+")
_WEB_ITERATIONS = 24
_DEV_MESSAGE = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>Jev Poker</title></head>
<body style="font-family: Georgia, serif; background:#0c1410; color:#e7efe9; padding:48px;">
<p>The UI dev server is on port 5173.</p>
</body>
</html>
"""


class TournamentRequest(BaseModel):
    hands: int = Field(ge=1, le=5000)
    seed: int
    pause_between_hands: bool = False


class PauseRequest(BaseModel):
    pause_between_hands: bool | None = None
    resume: bool = False


class _OfflineClient:
    """Used when OpenRouter is not configured. Every decision falls back to math."""

    def submit(self, state: dict, questions: dict) -> JevResult:
        raise JevError("OPENROUTER_API_KEY is not set")


class _RunManager:
    def __init__(self, runs_root: Path, iterations: int, client) -> None:
        self.runs_root = runs_root
        self.iterations = iterations
        self.client = client
        self._cond = threading.Condition()
        self.active = False
        self.waiting = False
        self.events: list[dict] = []
        self.generation = 0
        self.pause_between = False
        self._resume = threading.Event()
        self._resume.set()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._waiters: list[asyncio.Event] = []

    def start(self, hands: int, seed: int, pause_between_hands: bool, client=None) -> str:
        with self._cond:
            if self.active:
                raise RuntimeError("a tournament is already running")
            self.events.clear()
            self.generation += 1
            self.active = True
            self.waiting = False
            self.pause_between = pause_between_hands
            self._resume.set()
            run_id = _fresh_id(self.runs_root)
            run_dir = self.runs_root / run_id
            run_dir.mkdir(parents=True)
            generation = self.generation
            self._cond.notify_all()
        self._signal()
        chosen = self.client if client is None else client
        thread = threading.Thread(
            target=self._worker,
            args=(hands, seed, run_dir, generation, chosen),
            name="jev-tournament",
            daemon=True,
        )
        self._thread = thread
        thread.start()
        return run_id

    def pause(self, body: PauseRequest) -> dict:
        if body.pause_between_hands is not None:
            self.pause_between = body.pause_between_hands
            if not body.pause_between_hands:
                self._resume.set()
        if body.resume:
            self._resume.set()
        return {"pause_between_hands": self.pause_between, "waiting": self.waiting}

    def publish(self, event: dict) -> None:
        with self._cond:
            stamped = {"seq": len(self.events), "generation": self.generation, **event}
            self.events.append(stamped)
            self._cond.notify_all()
        self._signal()

    def wait_between_hands(self) -> None:
        if not self.pause_between:
            return
        self.waiting = True
        self._resume.clear()
        while self.pause_between:
            if self._resume.wait(timeout=0.25):
                break
        self.waiting = False

    def _signal(self) -> None:
        loop = self._loop
        if loop is None or not loop.is_running():
            return

        def fire() -> None:
            for waiter in list(self._waiters):
                waiter.set()

        loop.call_soon_threadsafe(fire)

    def _pending(self, index: int, seen_generation: int | None) -> tuple[int | None, int, list[dict]]:
        with self._cond:
            if seen_generation != self.generation:
                seen_generation = self.generation
                index = 0
            if index < len(self.events):
                batch = list(self.events[index:])
                return seen_generation, len(self.events), batch
            return seen_generation, index, []

    async def iter_sse(self, request: Request):
        """Stay open after the run finishes so the browser does not reconnect and replay."""
        self._loop = asyncio.get_running_loop()
        waiter = asyncio.Event()
        self._waiters.append(waiter)
        index = 0
        seen_generation = None
        try:
            # A finished run ends this response. A long retry keeps EventSource from
            # reconnecting in a loop if the page has not closed the stream yet.
            yield "retry: 86400000\n\n"
            while True:
                if await request.is_disconnected():
                    return
                seen_generation, index, batch = self._pending(index, seen_generation)
                if not batch:
                    waiter.clear()
                    seen_generation, index, batch = self._pending(index, seen_generation)
                if not batch:
                    try:
                        await asyncio.wait_for(waiter.wait(), timeout=15)
                    except TimeoutError:
                        yield ": ping\n\n"
                    continue
                finished = False
                for event in batch:
                    yield _sse(event)
                    finished = finished or event.get("type") == "finished"
                if finished:
                    return
        finally:
            if waiter in self._waiters:
                self._waiters.remove(waiter)

    def _worker(self, hands: int, seed: int, run_dir: Path, generation: int, client) -> None:
        try:
            play_tournament(
                hands,
                seed,
                client=client,
                iterations=self.iterations,
                runs_root=self.runs_root,
                run_dir=run_dir,
                on_event=self.publish,
                between_hands=self.wait_between_hands,
            )
        except Exception as exc:
            self.publish(
                {
                    "type": "finished",
                    "id": run_dir.name,
                    "summary": {
                        "hands_played": 0,
                        "stacks": [STARTING_STACK] * SEATS,
                        "hands_won": {},
                        "decisions": {"jev": 0, "math": 0, "math_error": 0},
                        "mean_jev_confidence": None,
                        "total_usd": 0.0,
                        "path": str(run_dir / "hands.jsonl"),
                        "error": str(exc),
                    },
                }
            )
        finally:
            with self._cond:
                if self.generation == generation:
                    self.active = False
                    self.waiting = False
                self._cond.notify_all()
        self._signal()


def create_app(
    *,
    client=None,
    runs_root: Path | str | None = None,
    iterations: int = _WEB_ITERATIONS,
) -> FastAPI:
    root = Path(runs_root) if runs_root is not None else Path.cwd() / "runs"
    manager = _RunManager(root, iterations, client if client is not None else _default_client())
    app = FastAPI(title="Jev Poker")
    app.state.manager = manager
    app.state.runs_root = root

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/api/tournament", status_code=202)
    def start_tournament(body: TournamentRequest) -> dict:
        try:
            run_id = manager.start(body.hands, body.seed, body.pause_between_hands)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail="a tournament is already running") from exc
        return {"id": run_id, "hands": body.hands, "seed": body.seed}

    @app.post("/api/tournament/pause")
    def pause_tournament(body: PauseRequest) -> dict:
        return manager.pause(body)

    @app.get("/api/tournament/stream")
    def stream_tournament(request: Request) -> StreamingResponse:
        return StreamingResponse(
            manager.iter_sse(request),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/runs")
    def list_runs() -> dict:
        runs = []
        if root.is_dir():
            for directory in sorted(root.iterdir(), reverse=True):
                log = directory / "hands.jsonl"
                if directory.is_dir() and log.is_file():
                    runs.append({"id": directory.name, "hands": _count_lines(log)})
        return {"runs": runs}

    @app.get("/api/runs/{run_id}")
    def read_run(run_id: str) -> dict:
        log = _run_log(root, run_id)
        hands = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line.strip()]
        return {"id": run_id, "hands": hands}

    dist = _frontend_dist()
    index = dist / "index.html"
    if index.is_file():
        app.mount("/", StaticFiles(directory=dist, html=True), name="ui")
    else:

        @app.get("/")
        def dev_server_message() -> HTMLResponse:
            return HTMLResponse(_DEV_MESSAGE)

    return app


def _default_client():
    try:
        return JevClient()
    except JevError:
        return _OfflineClient()


def _fresh_id(root: Path) -> str:
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    directory = root / stamp
    counter = 0
    while directory.exists():
        counter += 1
        directory = root / f"{stamp}-{counter}"
    return directory.name


def _run_log(root: Path, run_id: str) -> Path:
    if not _RUN_ID.fullmatch(run_id):
        raise HTTPException(status_code=404, detail="run not found")
    path = (root / run_id / "hands.jsonl").resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise HTTPException(status_code=404, detail="run not found")
    return path


def _count_lines(path: Path) -> int:
    return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())


def _sse(event: dict) -> str:
    return f"event: {event['type']}\ndata: {json.dumps(event)}\n\n"


def _frontend_dist() -> Path:
    here = Path(__file__).resolve()
    candidate = here.parents[3]
    if (candidate / "pyproject.toml").is_file():
        return candidate / "web" / "dist"
    return Path.cwd() / "web" / "dist"


app = create_app()
