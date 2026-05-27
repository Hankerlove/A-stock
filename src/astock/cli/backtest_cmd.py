import typer

app = typer.Typer(help="回测命令（待实现）")


@app.command("run")
def run_backtest():
    """运行回测"""
    typer.echo("回测引擎尚未实现。")


if __name__ == "__main__":
    app()
