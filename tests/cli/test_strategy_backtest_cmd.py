from typer.testing import CliRunner

from astock.cli.main import app


runner = CliRunner()


def test_strategy_list_command_shows_builtin_strategies():
    result = runner.invoke(app, ["strategy", "list"])

    assert result.exit_code == 0
    assert "dividend-low-vol" in result.output
    assert "value-low-vol" in result.output


def test_strategy_explain_command_shows_parameters():
    result = runner.invoke(app, ["strategy", "explain", "dividend-low-vol"])

    assert result.exit_code == 0
    assert "top_n" in result.output
    assert "lookback_days" in result.output
    assert "持仓股票数量" in result.output


def test_strategy_explain_command_shows_new_strategy_parameter_descriptions():
    result = runner.invoke(app, ["strategy", "explain", "momentum-reversal"])

    assert result.exit_code == 0
    assert "momentum_window" in result.output
    assert "中期动量窗口" in result.output
    assert "reversal_window" in result.output
    assert "短期反转窗口" in result.output


def test_strategy_signals_help_exposes_weight_parameters():
    result = runner.invoke(app, ["strategy", "signals", "--help"])

    assert result.exit_code == 0
    assert "--momentum-weight" in result.output
    assert "--price-breakout-weight" in result.output


def test_backtest_run_requires_dates():
    result = runner.invoke(app, ["backtest", "run", "--strategy", "dividend-low-vol"])

    assert result.exit_code != 0
    assert "start" in result.output or "Missing" in result.output
