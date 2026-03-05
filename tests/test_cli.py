"""Tests for the CLI module."""

from typer.testing import CliRunner

from andalus.cli import app

runner = CliRunner()


def test_main_command():
    """Test the main CLI command."""
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Replace this message" in result.stdout
    assert "Typer documentation" in result.stdout


def test_main_command_help():
    """Test the main CLI command with --help flag."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Console script for andalus" in result.stdout
