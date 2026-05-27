from datetime import datetime
import typer
from pathlib import Path

app = typer.Typer(help="交易日历查询")


@app.command("show")
def show(date: str = typer.Argument(None, help="日期 (YYYYMMDD)，默认今天")):
    """查看指定日期是否为交易日"""
    if date is None:
        date = datetime.now().strftime("%Y%m%d")

    import duckdb
    data_dir = Path("data")
    trade_cal_dir = data_dir / "trade_cal"

    if not trade_cal_dir.exists() or not any(trade_cal_dir.glob("*.parquet")):
        typer.echo("交易日历数据尚未同步。请先运行: astock data sync --table trade_cal")
        raise typer.Exit(1)

    db_path = data_dir / "astock.duckdb"
    conn = duckdb.connect(str(db_path))
    result = conn.execute(
        f"SELECT exchange, cal_date, is_open, pretrade_date "
        f"FROM read_parquet('{trade_cal_dir}/*.parquet') "
        f"WHERE cal_date = '{date}'"
    ).fetchall()

    if not result:
        typer.echo(f"{date}: 无交易日历记录")
    else:
        for row in result:
            status = "交易日" if row[2] == "1" else "休市日"
            typer.echo(f"{row[0]} | {row[1]} | {status} | 前一交易日: {row[3]}")

    conn.close()
