from pathlib import Path
import re
import webbrowser

import typer

from astock.visualization.kline import (
    KLineChartError,
    default_kline_date_range,
    load_kline_data,
    render_kline_html,
)

app = typer.Typer(help="可视化图表命令")


@app.command("kline")
def kline(
    query: str = typer.Argument(..., help="股票代码或股票名称，如 000001.SZ、000001、平安银行"),
    start: str | None = typer.Option(None, "--start", help="开始日期，格式 YYYYMMDD；未传 start/end 时默认当前交易日前两年"),
    end: str | None = typer.Option(None, "--end", help="结束日期，格式 YYYYMMDD；未传 start/end 时默认当前交易日"),
    limit: int = typer.Option(500, "--limit", help="最多绘制最近 N 条 K 线，<=0 表示不限制"),
    output: Path | None = typer.Option(None, "--output", "-o", help="输出 HTML 文件路径"),
    config: Path = typer.Option(Path("config.yaml"), "--config", "-c", help="配置文件路径"),
    open_browser: bool = typer.Option(False, "--open", help="生成后用默认浏览器打开"),
):
    """生成交互式 K 线图 HTML。"""
    from astock.core.config import Config
    from astock.data.store.db import DataStore

    try:
        cfg = Config.from_yaml(str(config))
        store = DataStore(db_path=cfg.storage.db_path, data_dir=cfg.storage.data_dir)
        resolved_start, resolved_end = start, end
        if start is None and end is None:
            resolved_start, resolved_end = default_kline_date_range(store)
        identity, frame = load_kline_data(
            store,
            query,
            start=resolved_start,
            end=resolved_end,
            limit=None if limit <= 0 else limit,
        )
        html = render_kline_html(identity, frame)
        output_path = output or _default_output_path(identity.ts_code, resolved_start, resolved_end)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(html, encoding="utf-8")
    except KLineChartError as exc:
        typer.echo(f"生成 K 线图失败: {exc}")
        raise typer.Exit(1) from exc
    except Exception as exc:
        typer.echo(f"生成 K 线图失败: {exc}")
        raise typer.Exit(1) from exc

    typer.echo(f"已生成 K 线图: {output_path}")
    typer.echo(f"股票: {identity.name or identity.ts_code} ({identity.ts_code})")
    typer.echo(f"数据: {frame.iloc[0]['trade_date']} - {frame.iloc[-1]['trade_date']}，共 {len(frame)} 条")
    if open_browser:
        webbrowser.open(output_path.resolve().as_uri())


def _default_output_path(ts_code: str, start: str | None, end: str | None) -> Path:
    parts = ["kline", _safe_name(ts_code)]
    if start:
        parts.append(start)
    if end:
        parts.append(end)
    return Path("charts") / ("_".join(parts) + ".html")


def _safe_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)
