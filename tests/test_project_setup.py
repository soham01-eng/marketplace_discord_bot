"""Smoke tests for the initial project scaffold."""

import pytest

from main import main


def test_application_entry_point_runs(capsys: pytest.CaptureFixture[str]) -> None:
    """The placeholder entry point should run before bot features are added."""
    main()

    captured = capsys.readouterr()
    assert captured.out == "Marketplace Discord Bot project initialized.\n"
