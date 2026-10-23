"""Repo-root dotenv loading does not override the process environment."""

import os

from jev_poker import load_repo_env


def test_dotenv_does_not_override_existing_variables(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "from-process")
    monkeypatch.delenv("JEV_POKER_DOTENV_PROBE", raising=False)
    (tmp_path / ".env").write_text(
        "OPENROUTER_API_KEY=from-file\nJEV_POKER_DOTENV_PROBE=from-file\n",
        encoding="utf-8",
    )
    load_repo_env(tmp_path)
    assert os.environ["OPENROUTER_API_KEY"] == "from-process"
    assert os.environ["JEV_POKER_DOTENV_PROBE"] == "from-file"
