import typer

app = typer.Typer(help="选股策略命令（待实现）")


@app.command("list")
def list_strategies():
    """列出可用策略"""
    typer.echo("暂无可用策略。策略引擎尚未实现。")


if __name__ == "__main__":
    app()
