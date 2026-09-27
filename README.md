# jev_poker

Local play-money 4-handed No-Limit Texas Hold'em engine for simulating our own bots.
No networking, no accounts, and no real-money play.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Tests

```powershell
pytest
```

Pass `seed` to `Game` for a deterministic deck shuffle across hands.
