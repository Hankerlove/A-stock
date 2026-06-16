from dataclasses import dataclass
from datetime import date
import html
import json

import pandas as pd

from astock.data.store.db import DataStore


@dataclass(frozen=True)
class StockIdentity:
    ts_code: str
    symbol: str
    name: str = ""


class KLineChartError(ValueError):
    """Raised when a K-line chart cannot be built from local data."""


def default_kline_date_range(store: DataStore, today: date | None = None) -> tuple[str, str]:
    """Return the default two-year window ending at the current local trading day."""
    today = today or date.today()
    end = _latest_trade_day_on_or_before(store, today.strftime("%Y%m%d"))
    if end is None:
        end = today.strftime("%Y%m%d")
    start = _subtract_years(_parse_yyyymmdd(end), 2).strftime("%Y%m%d")
    return start, end


def load_kline_data(
    store: DataStore,
    query: str,
    start: str | None = None,
    end: str | None = None,
    limit: int | None = 500,
) -> tuple[StockIdentity, pd.DataFrame]:
    """Resolve a stock code/name and load daily OHLC data for charting."""
    identity = resolve_stock(store, query)
    if not store.table_exists("daily"):
        raise KLineChartError("daily 表不存在，请先运行 astock data sync 同步行情数据")

    frame = store.load("daily", ts_code=identity.ts_code)
    if frame.empty:
        raise KLineChartError(f"没有找到 {identity.ts_code} 的日线行情")

    required = {"trade_date", "open", "high", "low", "close"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise KLineChartError(f"daily 表缺少 K 线字段: {', '.join(missing)}")

    frame = frame.copy()
    frame["trade_date"] = frame["trade_date"].astype(str)
    if start:
        frame = frame[frame["trade_date"] >= start]
    if end:
        frame = frame[frame["trade_date"] <= end]

    numeric_cols = ["open", "high", "low", "close", "vol", "amount"]
    for col in numeric_cols:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")
    if "vol" not in frame.columns:
        frame["vol"] = 0.0

    frame = (
        frame.dropna(subset=["trade_date", "open", "high", "low", "close"])
        .sort_values("trade_date")
        .drop_duplicates(subset=["trade_date"], keep="last")
        .reset_index(drop=True)
    )
    if frame.empty:
        raise KLineChartError(f"{identity.ts_code} 在指定日期范围内没有可绘制行情")
    if limit is not None and limit > 0 and len(frame) > limit:
        frame = frame.tail(limit).reset_index(drop=True)
    return identity, frame


def resolve_stock(store: DataStore, query: str) -> StockIdentity:
    q = query.strip()
    if not q:
        raise KLineChartError("请输入股票代码或股票名称")

    stocks = _load_stock_basic(store)
    if not stocks.empty:
        match = _match_stock_basic(stocks, q)
        if match is not None:
            return match

    if "." in q:
        ts_code = q.upper()
        return StockIdentity(ts_code=ts_code, symbol=ts_code.split(".")[0])

    raise KLineChartError(f"未找到股票: {query}")


def render_kline_html(identity: StockIdentity, frame: pd.DataFrame) -> str:
    rows = _chart_rows(frame)
    if not rows:
        raise KLineChartError("没有可渲染的 K 线数据")

    title = f"{identity.name} ({identity.ts_code})" if identity.name else identity.ts_code
    title_html = html.escape(title)
    rows_json = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title_html} K 线图</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fa;
      --panel: #ffffff;
      --text: #1f2937;
      --muted: #667085;
      --grid: #e6e8ef;
      --up: #d92d20;
      --down: #039855;
      --accent: #2563eb;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    .shell {{
      width: min(1280px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 20px 0;
    }}
    header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      margin-bottom: 12px;
    }}
    h1 {{
      margin: 0;
      font-size: 22px;
      line-height: 1.3;
      font-weight: 700;
    }}
    .stats {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      color: var(--muted);
      font-size: 13px;
    }}
    .stats strong {{
      color: var(--text);
      font-variant-numeric: tabular-nums;
    }}
    .toolbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
      color: var(--muted);
      font-size: 13px;
    }}
    .buttons {{
      display: flex;
      gap: 8px;
    }}
    button {{
      border: 1px solid #d0d5dd;
      background: #fff;
      border-radius: 6px;
      color: var(--text);
      cursor: pointer;
      font-size: 13px;
      height: 32px;
      padding: 0 10px;
    }}
    button:hover {{ border-color: var(--accent); }}
    .chart-wrap {{
      position: relative;
      height: min(720px, calc(100vh - 148px));
      min-height: 460px;
      border: 1px solid #d8dce6;
      border-radius: 8px;
      background: var(--panel);
      overflow: hidden;
    }}
    canvas {{
      display: block;
      width: 100%;
      height: 100%;
      cursor: crosshair;
    }}
    .tooltip {{
      position: absolute;
      left: 12px;
      top: 12px;
      min-width: 210px;
      padding: 9px 10px;
      border: 1px solid #d8dce6;
      border-radius: 6px;
      background: rgba(255,255,255,0.95);
      box-shadow: 0 10px 30px rgba(15, 23, 42, 0.10);
      color: var(--text);
      font-size: 12px;
      line-height: 1.55;
      pointer-events: none;
      opacity: 0;
      transition: opacity 120ms ease;
    }}
    .tooltip.visible {{ opacity: 1; }}
    .tooltip .date {{ font-weight: 700; margin-bottom: 2px; }}
    .tooltip span {{
      display: inline-block;
      min-width: 48px;
      color: var(--muted);
    }}
    @media (max-width: 720px) {{
      .shell {{ width: calc(100vw - 20px); padding: 12px 0; }}
      header, .toolbar {{ align-items: flex-start; flex-direction: column; }}
      .chart-wrap {{ height: calc(100vh - 188px); min-height: 390px; }}
    }}
  </style>
</head>
<body>
  <main class="shell">
    <header>
      <h1>{title_html} K 线图</h1>
      <div class="stats">
        <div>可视最高: <strong id="visibleHigh">-</strong></div>
        <div>可视最低: <strong id="visibleLow">-</strong></div>
        <div>区间: <strong id="visibleRange">-</strong></div>
      </div>
    </header>
    <div class="toolbar">
      <div>拖拽左右移动，滚轮缩放，悬停查看单日开高低收。</div>
      <div class="buttons">
        <button id="zoomIn" type="button">放大</button>
        <button id="zoomOut" type="button">缩小</button>
        <button id="reset" type="button">重置</button>
      </div>
    </div>
    <section class="chart-wrap">
      <canvas id="klineCanvas"></canvas>
      <div id="tooltip" class="tooltip"></div>
    </section>
  </main>
  <script>
    const rows = {rows_json};
    const canvas = document.getElementById("klineCanvas");
    const ctx = canvas.getContext("2d");
    const tooltip = document.getElementById("tooltip");
    const colors = {{
      text: "#1f2937",
      muted: "#667085",
      grid: "#e6e8ef",
      up: "#d92d20",
      down: "#039855",
      cross: "#344054",
      volume: "rgba(37, 99, 235, 0.26)"
    }};
    let start = Math.max(0, rows.length - Math.min(120, rows.length));
    let end = rows.length;
    let hoverIndex = null;
    let dragging = false;
    let dragStartX = 0;
    let dragStartStart = 0;
    let dragStartEnd = 0;

    function clamp(value, min, max) {{
      return Math.min(Math.max(value, min), max);
    }}

    function setWindow(nextStart, nextEnd) {{
      const size = Math.max(5, nextEnd - nextStart);
      if (size >= rows.length) {{
        start = 0;
        end = rows.length;
        return;
      }}
      start = clamp(nextStart, 0, rows.length - size);
      end = start + size;
    }}

    function resizeCanvas() {{
      const rect = canvas.getBoundingClientRect();
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.floor(rect.width * ratio));
      canvas.height = Math.max(1, Math.floor(rect.height * ratio));
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      draw();
    }}

    function chartBounds() {{
      const width = canvas.clientWidth;
      const height = canvas.clientHeight;
      return {{
        width,
        height,
        left: 64,
        right: 22,
        top: 24,
        bottom: 72,
        volumeHeight: 58,
        gap: 18
      }};
    }}

    function visibleRows() {{
      return rows.slice(start, end);
    }}

    function priceToY(price, low, high, top, height) {{
      if (high === low) return top + height / 2;
      return top + (high - price) / (high - low) * height;
    }}

    function fmt(value) {{
      if (!Number.isFinite(value)) return "-";
      return value.toFixed(2);
    }}

    function drawGrid(bounds, low, high, priceTop, priceHeight) {{
      ctx.strokeStyle = colors.grid;
      ctx.lineWidth = 1;
      ctx.fillStyle = colors.muted;
      ctx.font = "12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
      ctx.textAlign = "right";
      ctx.textBaseline = "middle";
      for (let i = 0; i <= 4; i += 1) {{
        const y = priceTop + priceHeight * i / 4;
        ctx.beginPath();
        ctx.moveTo(bounds.left, y);
        ctx.lineTo(bounds.width - bounds.right, y);
        ctx.stroke();
        const value = high - (high - low) * i / 4;
        ctx.fillText(fmt(value), bounds.left - 8, y);
      }}
    }}

    function drawArrow(fromX, fromY, toX, toY, color) {{
      const angle = Math.atan2(toY - fromY, toX - fromX);
      const headLength = 8;
      ctx.strokeStyle = color;
      ctx.fillStyle = color;
      ctx.lineWidth = 1.4;
      ctx.beginPath();
      ctx.moveTo(fromX, fromY);
      ctx.lineTo(toX, toY);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(toX, toY);
      ctx.lineTo(toX - headLength * Math.cos(angle - Math.PI / 6), toY - headLength * Math.sin(angle - Math.PI / 6));
      ctx.lineTo(toX - headLength * Math.cos(angle + Math.PI / 6), toY - headLength * Math.sin(angle + Math.PI / 6));
      ctx.closePath();
      ctx.fill();
    }}

    function drawAnnotation(label, value, index, direction, bounds, priceLow, priceHigh, priceTop, priceHeight, barWidth) {{
      const pointX = bounds.left + index * barWidth + barWidth / 2;
      const pointY = priceToY(value, priceLow, priceHigh, priceTop, priceHeight);
      const color = direction === "high" ? colors.up : colors.down;
      const labelWidth = 76;
      const labelHeight = 22;
      const labelX = clamp(
        pointX + (pointX > bounds.width * 0.72 ? -labelWidth - 12 : 12),
        bounds.left + 4,
        bounds.width - bounds.right - labelWidth - 4
      );
      const rawLabelY = direction === "high" ? pointY - 34 : pointY + 12;
      const labelY = clamp(rawLabelY, bounds.top + 4, priceTop + priceHeight - labelHeight - 4);

      ctx.fillStyle = "rgba(255, 255, 255, 0.92)";
      ctx.strokeStyle = color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.roundRect(labelX, labelY, labelWidth, labelHeight, 5);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = color;
      ctx.font = "12px -apple-system, BlinkMacSystemFont, Segoe UI, sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(`${{label}} ${{fmt(value)}}`, labelX + labelWidth / 2, labelY + labelHeight / 2);

      const fromX = labelX + (pointX < labelX ? 0 : labelWidth);
      const fromY = labelY + labelHeight / 2;
      drawArrow(fromX, fromY, pointX, pointY, color);
    }}

    function drawExtremaAnnotations(data, bounds, priceLow, priceHigh, priceTop, priceHeight, barWidth, visibleHigh, visibleLow) {{
      const visibleHighPoint = data.findIndex(row => row.high === visibleHigh);
      const visibleLowPoint = data.findIndex(row => row.low === visibleLow);
      if (visibleHighPoint >= 0) {{
        drawAnnotation("最高", visibleHigh, visibleHighPoint, "high", bounds, priceLow, priceHigh, priceTop, priceHeight, barWidth);
      }}
      if (visibleLowPoint >= 0 && visibleLowPoint !== visibleHighPoint) {{
        drawAnnotation("最低", visibleLow, visibleLowPoint, "low", bounds, priceLow, priceHigh, priceTop, priceHeight, barWidth);
      }}
    }}

    function draw() {{
      const bounds = chartBounds();
      ctx.clearRect(0, 0, bounds.width, bounds.height);
      const data = visibleRows();
      if (!data.length) return;

      const visibleHigh = Math.max(...data.map(row => row.high));
      const visibleLow = Math.min(...data.map(row => row.low));
      const padding = Math.max((visibleHigh - visibleLow) * 0.06, visibleHigh * 0.002, 0.01);
      const priceHigh = visibleHigh + padding;
      const priceLow = visibleLow - padding;
      const plotWidth = bounds.width - bounds.left - bounds.right;
      const priceTop = bounds.top;
      const priceHeight = bounds.height - bounds.top - bounds.bottom - bounds.volumeHeight - bounds.gap;
      const volumeTop = priceTop + priceHeight + bounds.gap;
      const barWidth = plotWidth / data.length;
      const candleWidth = clamp(barWidth * 0.62, 2, 14);
      const maxVol = Math.max(...data.map(row => row.vol || 0), 1);

      document.getElementById("visibleHigh").textContent = fmt(visibleHigh);
      document.getElementById("visibleLow").textContent = fmt(visibleLow);
      document.getElementById("visibleRange").textContent = `${{data[0].trade_date}} - ${{data[data.length - 1].trade_date}}`;

      drawGrid(bounds, priceLow, priceHigh, priceTop, priceHeight);

      data.forEach((row, i) => {{
        const x = bounds.left + i * barWidth + barWidth / 2;
        const yOpen = priceToY(row.open, priceLow, priceHigh, priceTop, priceHeight);
        const yClose = priceToY(row.close, priceLow, priceHigh, priceTop, priceHeight);
        const yHigh = priceToY(row.high, priceLow, priceHigh, priceTop, priceHeight);
        const yLow = priceToY(row.low, priceLow, priceHigh, priceTop, priceHeight);
        const up = row.close >= row.open;
        ctx.strokeStyle = up ? colors.up : colors.down;
        ctx.fillStyle = up ? colors.up : colors.down;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(x, yHigh);
        ctx.lineTo(x, yLow);
        ctx.stroke();
        const bodyTop = Math.min(yOpen, yClose);
        const bodyHeight = Math.max(Math.abs(yClose - yOpen), 1);
        ctx.fillRect(x - candleWidth / 2, bodyTop, candleWidth, bodyHeight);

        const volHeight = (row.vol || 0) / maxVol * bounds.volumeHeight;
        ctx.fillStyle = up ? "rgba(217,45,32,0.22)" : "rgba(3,152,85,0.22)";
        ctx.fillRect(x - candleWidth / 2, volumeTop + bounds.volumeHeight - volHeight, candleWidth, volHeight);
      }});

      drawExtremaAnnotations(data, bounds, priceLow, priceHigh, priceTop, priceHeight, barWidth, visibleHigh, visibleLow);

      ctx.fillStyle = colors.muted;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      const labelCount = Math.min(6, data.length);
      for (let i = 0; i < labelCount; i += 1) {{
        const idx = Math.round(i * (data.length - 1) / Math.max(1, labelCount - 1));
        const x = bounds.left + idx * barWidth + barWidth / 2;
        ctx.fillText(data[idx].trade_date, x, bounds.height - 44);
      }}

      if (hoverIndex !== null && hoverIndex >= start && hoverIndex < end) {{
        const local = hoverIndex - start;
        const row = rows[hoverIndex];
        const x = bounds.left + local * barWidth + barWidth / 2;
        const y = priceToY(row.close, priceLow, priceHigh, priceTop, priceHeight);
        ctx.strokeStyle = colors.cross;
        ctx.setLineDash([4, 4]);
        ctx.beginPath();
        ctx.moveTo(x, bounds.top);
        ctx.lineTo(x, volumeTop + bounds.volumeHeight);
        ctx.moveTo(bounds.left, y);
        ctx.lineTo(bounds.width - bounds.right, y);
        ctx.stroke();
        ctx.setLineDash([]);
      }}
    }}

    function updateTooltip(event) {{
      const bounds = chartBounds();
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const data = visibleRows();
      const plotWidth = bounds.width - bounds.left - bounds.right;
      if (x < bounds.left || x > bounds.width - bounds.right || !data.length) {{
        hoverIndex = null;
        tooltip.classList.remove("visible");
        draw();
        return;
      }}
      const barWidth = plotWidth / data.length;
      const localIndex = clamp(Math.floor((x - bounds.left) / barWidth), 0, data.length - 1);
      hoverIndex = start + localIndex;
      const row = rows[hoverIndex];
      tooltip.innerHTML = `
        <div class="date">${{row.trade_date}}</div>
        <div><span>开盘</span>${{fmt(row.open)}} <span>最高</span>${{fmt(row.high)}}</div>
        <div><span>最低</span>${{fmt(row.low)}} <span>收盘</span>${{fmt(row.close)}}</div>
        <div><span>成交量</span>${{Number(row.vol || 0).toLocaleString("zh-CN")}}</div>
      `;
      tooltip.style.left = `${{Math.min(event.clientX - rect.left + 14, rect.width - 230)}}px`;
      tooltip.style.top = `${{Math.max(10, event.clientY - rect.top - 14)}}px`;
      tooltip.classList.add("visible");
      draw();
    }}

    canvas.addEventListener("wheel", event => {{
      event.preventDefault();
      const bounds = chartBounds();
      const rect = canvas.getBoundingClientRect();
      const x = event.clientX - rect.left;
      const count = end - start;
      const ratio = clamp((x - bounds.left) / (bounds.width - bounds.left - bounds.right), 0, 1);
      const center = start + count * ratio;
      const factor = event.deltaY > 0 ? 1.18 : 0.84;
      const nextCount = clamp(Math.round(count * factor), Math.min(12, rows.length), rows.length);
      const nextStart = Math.round(center - nextCount * ratio);
      setWindow(nextStart, nextStart + nextCount);
      updateTooltip(event);
    }}, {{ passive: false }});

    canvas.addEventListener("mousedown", event => {{
      dragging = true;
      dragStartX = event.clientX;
      dragStartStart = start;
      dragStartEnd = end;
      canvas.style.cursor = "grabbing";
    }});

    window.addEventListener("mouseup", () => {{
      dragging = false;
      canvas.style.cursor = "crosshair";
    }});

    canvas.addEventListener("mousemove", event => {{
      if (dragging) {{
        const bounds = chartBounds();
        const count = dragStartEnd - dragStartStart;
        const barWidth = (bounds.width - bounds.left - bounds.right) / Math.max(1, count);
        const shift = Math.round((dragStartX - event.clientX) / Math.max(1, barWidth));
        setWindow(dragStartStart + shift, dragStartEnd + shift);
      }}
      updateTooltip(event);
    }});

    canvas.addEventListener("mouseleave", () => {{
      hoverIndex = null;
      tooltip.classList.remove("visible");
      draw();
    }});

    document.getElementById("zoomIn").addEventListener("click", () => {{
      const count = end - start;
      const nextCount = clamp(Math.round(count * 0.75), Math.min(12, rows.length), rows.length);
      const center = start + count / 2;
      setWindow(Math.round(center - nextCount / 2), Math.round(center + nextCount / 2));
      draw();
    }});

    document.getElementById("zoomOut").addEventListener("click", () => {{
      const count = end - start;
      const nextCount = clamp(Math.round(count * 1.35), Math.min(12, rows.length), rows.length);
      const center = start + count / 2;
      setWindow(Math.round(center - nextCount / 2), Math.round(center + nextCount / 2));
      draw();
    }});

    document.getElementById("reset").addEventListener("click", () => {{
      start = Math.max(0, rows.length - Math.min(120, rows.length));
      end = rows.length;
      hoverIndex = null;
      tooltip.classList.remove("visible");
      draw();
    }});

    window.addEventListener("resize", resizeCanvas);
    resizeCanvas();
  </script>
</body>
</html>
"""


def _load_stock_basic(store: DataStore) -> pd.DataFrame:
    if not store.table_exists("stock_basic"):
        return pd.DataFrame()
    frame = store.load("stock_basic")
    expected = {"ts_code", "symbol", "name"}
    if not expected.issubset(frame.columns):
        return pd.DataFrame()
    frame = frame.copy()
    for col in expected:
        frame[col] = frame[col].fillna("").astype(str)
    return frame


def _match_stock_basic(stocks: pd.DataFrame, query: str) -> StockIdentity | None:
    q_upper = query.upper()
    exact = stocks[
        (stocks["ts_code"].str.upper() == q_upper)
        | (stocks["symbol"] == query)
        | (stocks["name"] == query)
    ]
    if exact.empty:
        exact = stocks[stocks["name"].str.contains(query, regex=False)]
    if exact.empty:
        return None

    exact = exact.drop_duplicates(subset=["ts_code"])
    if len(exact) > 1:
        choices = ", ".join(f"{row.ts_code}({row.name})" for row in exact.itertuples())
        raise KLineChartError(f"股票名称匹配到多只股票，请输入更精确的代码或名称: {choices}")
    row = exact.iloc[0]
    return StockIdentity(
        ts_code=str(row["ts_code"]).upper(),
        symbol=str(row["symbol"]),
        name=str(row["name"]),
    )


def _latest_trade_day_on_or_before(store: DataStore, today_text: str) -> str | None:
    if not store.table_exists("trade_cal"):
        return None
    frame = store.load("trade_cal")
    if frame.empty or "cal_date" not in frame.columns or "is_open" not in frame.columns:
        return None
    frame = frame.copy()
    frame["cal_date"] = frame["cal_date"].astype(str)
    is_open = frame["is_open"].astype(str).isin({"1", "1.0", "True", "true"})
    candidates = frame[(frame["cal_date"] <= today_text) & is_open]["cal_date"]
    if candidates.empty:
        return None
    return str(candidates.max())


def _parse_yyyymmdd(value: str) -> date:
    return date(int(value[:4]), int(value[4:6]), int(value[6:8]))


def _subtract_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year - years)
    except ValueError:
        return value.replace(year=value.year - years, day=28)


def _chart_rows(frame: pd.DataFrame) -> list[dict[str, float | str]]:
    rows: list[dict[str, float | str]] = []
    for row in frame.itertuples(index=False):
        rows.append(
            {
                "trade_date": str(row.trade_date),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "vol": float(getattr(row, "vol", 0.0) or 0.0),
            }
        )
    return rows
