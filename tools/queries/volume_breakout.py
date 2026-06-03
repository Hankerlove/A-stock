"""查询今日较前一交易日成交量放大 2 倍及以上的股票。

用法: python tools/queries/volume_breakout.py [倍数阈值] [输出行数]
示例: python tools/queries/volume_breakout.py          # 默认 2 倍，全部输出
      python tools/queries/volume_breakout.py 3.0 20   # 3 倍，最多 20 条
"""
import sys
from pathlib import Path

import duckdb

# 项目根目录 (从 tools/queries/ 往上两级)
ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data"

THRESHOLD = float(sys.argv[1]) if len(sys.argv) > 1 else 2.0
MAX_ROWS = int(sys.argv[2]) if len(sys.argv) > 2 else 0


def main():
    conn = duckdb.connect(str(DATA_DIR / "astock.duckdb"))

    # 先确定全市场最新的两个交易日（排除停牌股各自不同的最新日期问题）
    dates = conn.execute(f"""
        SELECT DISTINCT trade_date
        FROM read_parquet('{DATA_DIR}/daily/*.parquet', union_by_name=true)
        ORDER BY trade_date DESC
        LIMIT 2
    """).fetchall()
    if len(dates) < 2:
        print("数据不足，需要至少两个交易日的日线数据。")
        conn.close()
        return
    latest_date, prev_date = dates[0][0], dates[1][0]

    query = f"""
        WITH latest AS (
            SELECT ts_code, trade_date, vol, close, pct_chg
            FROM read_parquet('{DATA_DIR}/daily/*.parquet', union_by_name=true)
            WHERE trade_date = '{latest_date}'
        ),
        previous AS (
            SELECT ts_code, trade_date, vol, close, pct_chg
            FROM read_parquet('{DATA_DIR}/daily/*.parquet', union_by_name=true)
            WHERE trade_date = '{prev_date}'
        )
        SELECT
            l.ts_code,
            COALESCE(s.name, '') AS name,
            l.vol::BIGINT AS vol_today,
            p.vol::BIGINT AS vol_prev,
            ROUND(l.vol::DOUBLE / NULLIF(p.vol::DOUBLE, 0), 2) AS vol_ratio,
            ROUND(l.close, 2) AS close,
            ROUND(l.pct_chg, 2) AS pct_chg
        FROM latest l
        INNER JOIN previous p ON l.ts_code = p.ts_code
        LEFT JOIN read_parquet('{DATA_DIR}/stock_basic/*.parquet', union_by_name=true) s
            ON l.ts_code = s.ts_code
        WHERE l.vol::DOUBLE / NULLIF(p.vol::DOUBLE, 0) >= {THRESHOLD}
          AND l.pct_chg > 0
        ORDER BY vol_ratio DESC
    """
    if MAX_ROWS > 0:
        query += f" LIMIT {MAX_ROWS}"

    df = conn.execute(query).df()

    if df.empty:
        print(f"未找到 {latest_date} vs {prev_date} 成交量放大 ≥ {THRESHOLD:.0f} 倍的股票。")
        conn.close()
        return

    print(f"\n成交量放大 ≥ {THRESHOLD:.0f} 倍  (共 {len(df)} 只)")
    print(f"对比日期: {latest_date} vs {prev_date}")
    print("=" * 85)
    print(f"{'代码':<12} {'名称':<10} {'今日量':>12} {'前日量':>12} {'倍数':>8} {'收盘价':>8} {'涨跌幅':>8}")
    print("-" * 85)

    for _, row in df.iterrows():
        name = row['name'] if row['name'] else ''
        print(f"{row.ts_code:<12} {name:<10.10} {row.vol_today:>12,} {row.vol_prev:>12,} "
              f"{row.vol_ratio:>8.1f} {row.close:>8.2f} {row.pct_chg:>7.2f}%")

    stock_count = conn.execute(
        f"SELECT COUNT(DISTINCT ts_code) FROM read_parquet('{DATA_DIR}/daily/*.parquet', union_by_name=true) WHERE trade_date = '{latest_date}'"
    ).fetchone()[0]
    conn.close()
    print("-" * 85)
    print(f"{latest_date} 交易股票数: {stock_count:,}  |  触发占比: {len(df) / stock_count * 100:.2f}%")


if __name__ == "__main__":
    main()
