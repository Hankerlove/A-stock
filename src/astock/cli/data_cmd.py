import typer
from pathlib import Path

app = typer.Typer(help="数据同步与管理")


def _get_sync_manager():
    from astock.core.config import Config
    from astock.core.logging import setup_logging
    from astock.data.source.client import TushareClient
    from astock.data.store.db import DataStore
    from astock.data.sync.manager import SyncManager

    cfg = Config.from_yaml("config.yaml")
    setup_logging(cfg.log)

    client = TushareClient(token=cfg.tushare.token)
    store = DataStore(db_path=cfg.storage.db_path, data_dir=cfg.storage.data_dir)
    return SyncManager(client=client, store=store, config=cfg.sync)


@app.command("sync")
def sync(
    table: str = typer.Option(None, "--table", "-t", help="指定表名，不指定则同步全部"),
    mode: str = typer.Option("inc", "--mode", "-m", help="同步模式: full | inc"),
):
    """同步数据（默认增量）"""
    mgr = _get_sync_manager()

    if table:
        if table not in ["stock_basic", "trade_cal", "daily", "adj_factor", "daily_basic", "suspend_d", "tech_indicator"]:
            typer.echo(f"无效表名: {table}")
            typer.echo("有效表名: stock_basic, trade_cal, daily, adj_factor, daily_basic, suspend_d, tech_indicator")
            raise typer.Exit(1)
        result = mgr.sync_table(table, mode=mode)
        _print_result(result)
    else:
        results = mgr.sync_all()
        total = 0
        for r in results:
            _print_result(r)
            total += r.rows
        typer.echo(f"\n总计同步 {total} 条记录")


def _print_result(r):
    icon = "OK" if r.status == "success" else "FAIL"
    if r.status == "success" and r.rows == 0:
        typer.echo(f"[{icon}] {r.table}: 已是最新 (0 行)")
    elif r.status == "success":
        typer.echo(f"[{icon}] {r.table}: 同步 {r.rows} 行 ({r.mode})")
    else:
        typer.echo(f"[{icon}] {r.table}: 失败 — {r.error}")


@app.command("status")
def status():
    """查看各表数据状态"""
    from astock.core.config import Config
    from astock.data.store.db import DataStore

    cfg = Config.from_yaml("config.yaml")
    store = DataStore(db_path=cfg.storage.db_path, data_dir=cfg.storage.data_dir)

    tables = ["stock_basic", "trade_cal", "daily", "adj_factor", "daily_basic", "suspend_d", "tech_indicator"]
    date_cols = {
        "stock_basic": None, "trade_cal": "cal_date",
        "daily": "trade_date", "adj_factor": "trade_date",
        "daily_basic": "trade_date", "suspend_d": "trade_date",
        "tech_indicator": "trade_date",
    }

    typer.echo(f"{'表名':<16} {'行数':>10} {'最新日期':<12} {'状态'}")
    typer.echo("-" * 52)
    for t in tables:
        exists = store.table_exists(t)
        rows = store.row_count(t)
        if exists and date_cols[t]:
            latest = store.get_latest_date(t, date_cols[t])
        else:
            latest = "-"
        state = "有数据" if exists else "空"
        typer.echo(f"{t:<16} {rows:>10} {latest:<12} {state}")


@app.command("query")
def query(
    table: str = typer.Argument(..., help="表名"),
    filter_str: str = typer.Option(None, "--filter", "-f", help="过滤条件，如 ts_code=000001.SZ"),
    limit: int = typer.Option(10, "--limit", "-l", help="返回行数"),
    export: str = typer.Option(None, "--export", "-e", help="导出到 CSV 文件路径"),
):
    """查询数据"""
    from astock.core.config import Config
    from astock.data.store.db import DataStore

    cfg = Config.from_yaml("config.yaml")
    store = DataStore(db_path=cfg.storage.db_path, data_dir=cfg.storage.data_dir)

    if not store.table_exists(table):
        typer.echo(f"表 '{table}' 不存在或为空。")
        raise typer.Exit(1)

    filters = {}
    if filter_str:
        for pair in filter_str.split(","):
            k, v = pair.split("=")
            filters[k.strip()] = v.strip()

    df = store.load(table, **filters)
    if limit:
        df = df.head(limit)

    if export:
        df.to_csv(export, index=False)
        typer.echo(f"已导出 {len(df)} 行到 {export}")
    else:
        typer.echo(df.to_string(index=False))
        typer.echo(f"\n显示 {len(df)} 行")


@app.command("clean")
def clean(
    table: str = typer.Option(..., "--table", "-t", help="指定表名"),
    force: bool = typer.Option(False, "--force", "-f", help="跳过确认"),
):
    """清理指定表数据"""
    from astock.core.config import Config

    cfg = Config.from_yaml("config.yaml")
    table_dir = Path(cfg.storage.data_dir) / table

    if not table_dir.exists():
        typer.echo(f"表 '{table}' 无数据。")
        return

    if not force:
        confirm = typer.confirm(f"确认删除表 '{table}' 的所有数据？")
        if not confirm:
            typer.echo("已取消。")
            return

    import shutil
    shutil.rmtree(table_dir)
    typer.echo(f"已清理表 '{table}'。")
