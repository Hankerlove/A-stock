import typer
from astock.cli import config_cmd, data_cmd, cal_cmd, strategy_cmd, backtest_cmd, chart_cmd

app = typer.Typer(
    name="astock",
    help="A-Stock 量化交易数据系统",
    no_args_is_help=True,
)

app.add_typer(config_cmd.app, name="config")
app.add_typer(data_cmd.app, name="data")
app.add_typer(cal_cmd.app, name="cal")
app.add_typer(strategy_cmd.app, name="strategy")
app.add_typer(backtest_cmd.app, name="backtest")
app.add_typer(chart_cmd.app, name="chart")


@app.callback()
def main():
    """A-Stock: A股量化交易数据系统。管理本地股票数据库的同步、查询与分析。"""
    pass


if __name__ == "__main__":
    app()
