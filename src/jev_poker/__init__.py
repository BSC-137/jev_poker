"""Local play-money No-Limit Texas Hold'em."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def load_repo_env(root: Path | None = None) -> None:
    """Load the repo-root ``.env`` without overriding variables already set."""
    repo = _repo_root() if root is None else root
    if repo is None:
        return
    load_dotenv(repo / ".env", override=False)


def _repo_root() -> Path | None:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "jev_poker").is_dir():
            return parent
    return None


load_repo_env()
