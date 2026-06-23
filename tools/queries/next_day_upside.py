"""筛选下一个交易日存在上涨空间的股票。

信号名称: 趋势回踩再启动

核心思路:
1. 中期趋势仍向上: 收盘价在 20 日线上方，且 20 日线高于 60 日线。
2. 近期有回踩空间: 近 5 日最低价触及 20 日线附近，且距离近 20 日高点仍有空间。
3. 当日重新转强: 阳线收涨、重新站上短均线、量能温和放大。
4. 动能不过热: RSI 处于中性偏强区间，MACD 柱体改善。

用法: python tools/queries/next_day_upside.py [最低评分] [输出行数]
示例: python tools/queries/next_day_upside.py          # 默认评分 70，输出 30 条
      python tools/queries/next_day_upside.py 75 20   # 评分至少 75，最多 20 条
      python tools/queries/next_day_upside.py 65 0    # 评分至少 65，全部输出
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Sequence

import duckdb
import pandas as pd


ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data"

REQUIRED_TABLES = ("daily", "stock_basic", "daily_basic", "tech_indicator")


def _parquet_glob(data_dir: Path, table: str) -> str:
    return str(data_dir / table / "*.parquet").replace("'", "''")


def _validate_tables(data_dir: Path) -> None:
    missing = [
        table
        for table in REQUIRED_TABLES
        if not any((data_dir / table).glob("*.parquet"))
    ]
    if missing:
        missing_text = ", ".join(missing)
        raise FileNotFoundError(f"缺少必要数据表: {missing_text}")


def _empty_result(latest_date: str | None = None, prev_date: str | None = None) -> pd.DataFrame:
    df = pd.DataFrame(columns=[
        "ts_code",
        "name",
        "trade_date",
        "signal_score",
        "close",
        "pct_chg",
        "upside_room_pct",
        "ma20_gap_pct",
        "vol_ratio_5",
        "volume_ratio",
        "turnover_rate",
        "rsi6",
        "rsi14",
        "macd_hist",
        "signal_reason",
    ])
    df.attrs["latest_date"] = latest_date
    df.attrs["prev_date"] = prev_date
    return df


def _signal_reason(row: pd.Series) -> str:
    reasons = []

    ma20_gap = row.get("ma20_gap_pct")
    if pd.notna(ma20_gap) and -0.5 <= ma20_gap <= 8:
        reasons.append("20线")

    upside_room = row.get("upside_room_pct")
    if pd.notna(upside_room) and upside_room >= 2:
        reasons.append("空间")

    vol_ratio_5 = row.get("vol_ratio_5")
    if pd.notna(vol_ratio_5) and 1.05 <= vol_ratio_5 <= 2.6:
        reasons.append("放量")

    rsi6 = row.get("rsi6")
    rsi14 = row.get("rsi14")
    if pd.notna(rsi6) and pd.notna(rsi14) and rsi6 > rsi14:
        reasons.append("动能")

    macd_hist = row.get("macd_hist")
    if pd.notna(macd_hist) and macd_hist > 0:
        reasons.append("MACD+")

    return "/".join(reasons)


def find_candidates(data_dir: str | Path = DATA_DIR, min_score: float = 70, max_rows: int = 30) -> pd.DataFrame:
    """Return stocks matching the trend-pullback-rebound signal."""
    data_path = Path(data_dir)
    _validate_tables(data_path)

    daily_path = _parquet_glob(data_path, "daily")
    daily_basic_path = _parquet_glob(data_path, "daily_basic")
    stock_basic_path = _parquet_glob(data_path, "stock_basic")
    tech_path = _parquet_glob(data_path, "tech_indicator")
    min_score = float(min_score)
    max_rows = int(max_rows)

    conn = duckdb.connect()
    try:
        dates = conn.execute(f"""
            SELECT DISTINCT trade_date
            FROM read_parquet('{daily_path}', union_by_name=true)
            ORDER BY trade_date DESC
            LIMIT 2
        """).fetchall()
        if len(dates) < 2:
            return _empty_result()

        latest_date, prev_date = dates[0][0], dates[1][0]

        query = f"""
            WITH daily_src AS (
                SELECT
                    ts_code,
                    trade_date,
                    open,
                    high,
                    low,
                    close,
                    pct_chg,
                    vol,
                    amount
                FROM read_parquet('{daily_path}', union_by_name=true)
                WHERE close > 0
                  AND vol > 0
            ),
            daily_features AS (
                SELECT
                    *,
                    AVG(vol) OVER (
                        PARTITION BY ts_code
                        ORDER BY trade_date
                        ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
                    ) AS avg_vol_5,
                    AVG(vol) OVER (
                        PARTITION BY ts_code
                        ORDER BY trade_date
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                    ) AS avg_vol_20,
                    MAX(high) OVER (
                        PARTITION BY ts_code
                        ORDER BY trade_date
                        ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
                    ) AS high_20,
                    MIN(low) OVER (
                        PARTITION BY ts_code
                        ORDER BY trade_date
                        ROWS BETWEEN 4 PRECEDING AND CURRENT ROW
                    ) AS low_5,
                    COUNT(*) OVER (
                        PARTITION BY ts_code
                        ORDER BY trade_date
                        ROWS BETWEEN 59 PRECEDING AND CURRENT ROW
                    ) AS obs_60
                FROM daily_src
            ),
            stock_names AS (
                SELECT
                    ts_code,
                    ANY_VALUE(name) AS name,
                    ANY_VALUE(list_status) AS list_status
                FROM read_parquet('{stock_basic_path}', union_by_name=true)
                GROUP BY ts_code
            ),
            features AS (
                SELECT
                    l.ts_code,
                    COALESCE(s.name, '') AS name,
                    l.trade_date,
                    l.open,
                    l.high,
                    l.low,
                    l.close,
                    l.pct_chg,
                    l.vol,
                    l.amount,
                    p.close AS prev_close,
                    l.avg_vol_5,
                    l.avg_vol_20,
                    l.high_20,
                    l.low_5,
                    l.obs_60,
                    ROUND(l.vol::DOUBLE / NULLIF(l.avg_vol_5::DOUBLE, 0), 2) AS vol_ratio_5,
                    ROUND(l.vol::DOUBLE / NULLIF(l.avg_vol_20::DOUBLE, 0), 2) AS vol_ratio_20,
                    ROUND((l.high_20::DOUBLE / NULLIF(l.close::DOUBLE, 0) - 1) * 100, 2) AS upside_room_pct,
                    ROUND((l.close::DOUBLE / NULLIF(t.ma20::DOUBLE, 0) - 1) * 100, 2) AS ma20_gap_pct,
                    t.ma5,
                    t.ma10,
                    t.ma20,
                    t.ma60,
                    t.rsi6,
                    t.rsi14,
                    t.dif,
                    t.dea,
                    t.macd_hist,
                    pt.ma5 AS prev_ma5,
                    pt.macd_hist AS prev_macd_hist,
                    db.turnover_rate,
                    db.volume_ratio,
                    COALESCE(s.list_status, '') AS list_status
                FROM daily_features l
                INNER JOIN daily_features p
                    ON l.ts_code = p.ts_code
                   AND p.trade_date = '{prev_date}'
                INNER JOIN read_parquet('{tech_path}', union_by_name=true) t
                    ON l.ts_code = t.ts_code
                   AND l.trade_date = t.trade_date
                LEFT JOIN read_parquet('{tech_path}', union_by_name=true) pt
                    ON l.ts_code = pt.ts_code
                   AND pt.trade_date = '{prev_date}'
                LEFT JOIN read_parquet('{daily_basic_path}', union_by_name=true) db
                    ON l.ts_code = db.ts_code
                   AND l.trade_date = db.trade_date
                LEFT JOIN stock_names s
                    ON l.ts_code = s.ts_code
                WHERE l.trade_date = '{latest_date}'
            ),
            scored AS (
                SELECT
                    *,
                    (
                        CASE WHEN ma20 > ma60 AND close > ma20 THEN 20 ELSE 0 END
                      + CASE WHEN close BETWEEN ma20 * 0.995 AND ma20 * 1.08 THEN 15 ELSE 0 END
                      + CASE WHEN low_5 <= ma20 * 1.025 AND close <= high_20 * 0.98 THEN 15 ELSE 0 END
                      + CASE WHEN close > open AND pct_chg BETWEEN 0.2 AND 5.5 THEN 15 ELSE 0 END
                      + CASE WHEN close > ma5 AND prev_close <= prev_ma5 THEN 10 ELSE 0 END
                      + CASE WHEN vol_ratio_5 BETWEEN 1.05 AND 2.6 THEN 10 ELSE 0 END
                      + CASE WHEN rsi14 BETWEEN 45 AND 70 AND rsi6 > rsi14 THEN 10 ELSE 0 END
                      + CASE WHEN macd_hist > COALESCE(prev_macd_hist, -999999) AND dif >= dea THEN 5 ELSE 0 END
                    ) AS signal_score
                FROM features
                WHERE obs_60 >= 60
                  AND ma5 IS NOT NULL
                  AND ma20 IS NOT NULL
                  AND ma60 IS NOT NULL
                  AND rsi6 IS NOT NULL
                  AND rsi14 IS NOT NULL
                  AND macd_hist IS NOT NULL
                  AND name NOT LIKE '%ST%'
                  AND list_status IN ('', 'L')
            )
            SELECT
                ts_code,
                name,
                trade_date,
                signal_score,
                ROUND(close, 2) AS close,
                ROUND(pct_chg, 2) AS pct_chg,
                upside_room_pct,
                ma20_gap_pct,
                vol_ratio_5,
                volume_ratio,
                turnover_rate,
                ROUND(rsi6, 2) AS rsi6,
                ROUND(rsi14, 2) AS rsi14,
                ROUND(macd_hist, 4) AS macd_hist
            FROM scored
            WHERE signal_score >= {min_score}
              AND close > ma20
              AND ma20 > ma60
              AND low_5 <= ma20 * 1.04
              AND close <= high_20 * 0.985
            ORDER BY signal_score DESC, upside_room_pct DESC, vol_ratio_5 DESC
        """
        if max_rows > 0:
            query += f" LIMIT {max_rows}"

        df = conn.execute(query).df()
        if df.empty:
            result = _empty_result(latest_date=latest_date, prev_date=prev_date)
        else:
            df["signal_reason"] = df.apply(_signal_reason, axis=1)
            df.attrs["latest_date"] = latest_date
            df.attrs["prev_date"] = prev_date
            result = df
    finally:
        conn.close()

    return result


def print_report(df: pd.DataFrame, min_score: float) -> None:
    latest_date = df.attrs.get("latest_date")
    prev_date = df.attrs.get("prev_date")

    if latest_date is None or prev_date is None:
        print("数据不足，需要至少两个交易日的日线数据。")
        return

    if df.empty:
        print(f"未找到 {latest_date} 评分 ≥ {min_score:.0f} 的趋势回踩再启动股票。")
        return

    print(f"\n趋势回踩再启动信号  (共 {len(df)} 只)")
    print(f"信号日期: {latest_date}  |  前一交易日: {prev_date}  |  最低评分: {min_score:.0f}")
    print("逻辑: 中期趋势向上 + 近期回踩20日线 + 今日放量转强 + 动能未过热")
    print("=" * 136)
    print(
        f"{'代码':<12} {'名称':<10} {'评分':>6} {'收盘价':>8} {'涨跌幅':>8} "
        f"{'距20日高点':>10} {'离20日线':>9} {'5日量比':>8} {'RSI6/14':>12} {'信号说明':<24}"
    )
    print("-" * 136)

    for _, row in df.iterrows():
        name = row["name"] if row["name"] else ""
        print(
            f"{row.ts_code:<12} {name:<10.10} {row.signal_score:>6.0f} "
            f"{row.close:>8.2f} {row.pct_chg:>7.2f}% "
            f"{row.upside_room_pct:>9.2f}% {row.ma20_gap_pct:>8.2f}% "
            f"{row.vol_ratio_5:>8.2f} {row.rsi6:>5.1f}/{row.rsi14:<5.1f} "
            f"{row.signal_reason:<32.32}"
        )

    print("-" * 136)
    print("说明: 该信号是基于已有日线、日线基础指标和技术指标的条件筛选，不构成收益保证。")


def parse_args(argv: Sequence[str]) -> tuple[float, int]:
    min_score = float(argv[0]) if len(argv) > 0 else 70.0
    max_rows = int(argv[1]) if len(argv) > 1 else 30
    return min_score, max_rows


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    min_score, max_rows = parse_args(args)
    try:
        df = find_candidates(DATA_DIR, min_score=min_score, max_rows=max_rows)
    except FileNotFoundError as exc:
        print(str(exc))
        return 1

    print_report(df, min_score=min_score)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
