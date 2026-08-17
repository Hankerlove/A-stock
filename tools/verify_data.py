"""数据完整性校验脚本。检查本地数据库是否存在缺失、重复、异常等问题。"""
import sys
from datetime import datetime, timedelta
from pathlib import Path

import duckdb


DATA_DIR = Path("data")
MIN_CHECK_DATE = "20000101"
RECENT_DAYS = 60


class Reporter:
    def __init__(self) -> None:
        self.errors = 0
        self.warnings = 0

    def error(self, message: str) -> None:
        self.errors += 1
        print(f"  ERROR: {message}")

    def warn(self, message: str) -> None:
        self.warnings += 1
        print(f"  WARN: {message}")

    def info(self, message: str) -> None:
        print(f"  INFO: {message}")


TABLES = {
    "stock_basic": ("ts_code", None),
    "trade_cal": ("cal_date, exchange", "cal_date"),
    "daily": ("ts_code, trade_date", "trade_date"),
    "adj_factor": ("ts_code, trade_date", "trade_date"),
    "daily_basic": ("ts_code, trade_date", "trade_date"),
    "suspend_d": ("ts_code, trade_date, suspend_type", "trade_date"),
    "tech_indicator": ("ts_code, trade_date", "trade_date"),
}


def pq(table: str) -> str:
    return f"read_parquet('{DATA_DIR / table}/*.parquet', union_by_name=true)"


def _query_scalar(conn, query: str):
    row = conn.execute(query).fetchone()
    return row[0] if row else None


def _print_samples(conn, query: str, limit: int = 10) -> None:
    rows = conn.execute(query).fetchmany(limit)
    for row in rows:
        print(f"    {row}")


def _date_range_start(latest_str: str | None) -> tuple[str, str]:
    if not latest_str:
        return MIN_CHECK_DATE, "全部"
    latest_dt = datetime.strptime(latest_str, "%Y%m%d")
    recent_start = (latest_dt - timedelta(days=RECENT_DAYS)).strftime("%Y%m%d")
    start_date = max(MIN_CHECK_DATE, recent_start)
    return start_date, f"{start_date} ~ {latest_str}"


def _open_day_ranges(days: list[str]) -> list[tuple[str, str]]:
    if not days:
        return []
    ranges: list[tuple[str, str]] = []
    start = prev = days[0]
    for day in days[1:]:
        prev_dt = datetime.strptime(prev, "%Y%m%d")
        day_dt = datetime.strptime(day, "%Y%m%d")
        if (day_dt - prev_dt).days > 4:
            ranges.append((start, prev))
            start = day
        prev = day
    ranges.append((start, prev))
    return ranges


def _describe_columns(conn, table: str) -> set[str]:
    try:
        return {row[0] for row in conn.execute(f"DESCRIBE SELECT * FROM {pq(table)} LIMIT 1").fetchall()}
    except Exception:
        return set()


def verify(conn):
    reporter = Reporter()

    # ---- 1. 各表行数与日期范围 ----
    print("=" * 60)
    print("1. 各表概览")
    print("=" * 60)
    for tbl, (keys, date_col) in TABLES.items():
        try:
            total = _query_scalar(conn, f"SELECT COUNT(*) FROM {pq(tbl)}")
            unique = _query_scalar(conn, f"SELECT COUNT(DISTINCT ({keys})) FROM {pq(tbl)}")
            dupes = total - unique
            dup_flag = " ⚠️ 重复!" if dupes > 0 else ""
            date_info = ""
            if date_col:
                mn, mx = conn.execute(f"SELECT MIN({date_col}), MAX({date_col}) FROM {pq(tbl)}").fetchone()
                date_info = f" 日期范围: {mn} ~ {mx}"
            print(f"  {tbl:<16} {unique:>10,} 行  重复: {dupes:>8,}{dup_flag}{date_info}")
            if dupes > 0:
                reporter.error(f"{tbl} 主键重复 {dupes:,} 行")
        except Exception as e:
            print(f"  {tbl:<16} 读取失败: {e}")
            reporter.error(f"{tbl} 读取失败")

    # ---- 2. 检查 daily 日期连续性（与 trade_cal 对比） ----
    print()
    print("=" * 60)
    print("2. daily 日期连续性（与 trade_cal 对比）")
    print("=" * 60)
    try:
        missing = conn.execute(f"""
            SELECT DISTINCT c.cal_date
            FROM {pq('trade_cal')} c
            WHERE CAST(c.is_open AS VARCHAR) = '1'
              AND c.cal_date >= '{MIN_CHECK_DATE}'
              AND c.cal_date NOT IN (
                SELECT DISTINCT trade_date FROM {pq('daily')}
              )
            ORDER BY c.cal_date
        """).fetchall()
        if missing:
            dates = [r[0] for r in missing]
            print(f"  缺失交易日: {len(dates)} 个")
            print(f"  最近缺失: {dates[-20:]}")
            ranges = _open_day_ranges(dates)
            large_ranges = [(s, e) for s, e in ranges if s != e]
            if large_ranges:
                print("  大段缺失区间 (起始~结束):")
                for s, e in large_ranges[:5]:
                    print(f"    {s} ~ {e}")
            reporter.error(f"daily 缺失交易日 {len(dates)} 个")
        else:
            print("  无缺失交易日 ✓")
    except Exception as e:
        print(f"  检查失败: {e}")
        reporter.error("daily 日期连续性检查失败")

    # ---- 3. 检查每日股票数量是否合理 ----
    print()
    print("=" * 60)
    print("3. daily 每日股票数量抽样")
    print("=" * 60)
    latest_str = None
    try:
        samples = conn.execute(f"""
            SELECT trade_date, COUNT(DISTINCT ts_code) as n
            FROM {pq('daily')}
            WHERE trade_date >= '{MIN_CHECK_DATE}'
            GROUP BY trade_date
            ORDER BY trade_date
        """).fetchall()
        if samples:
            yearly = {}
            for d, n in samples:
                year = d[:4]
                if year not in yearly:
                    yearly[year] = (d, n)
            print(f"  {'年份':<6} {'日期':<12} {'股票数':>8}")
            for year in sorted(yearly.keys()):
                d, n = yearly[year]
                print(f"  {year:<6} {d:<12} {n:>8}")
            latest_date, latest_n = samples[-1]
            latest_str = latest_date
            print(f"  最新日期: {latest_date}, 股票数: {latest_n}")
            recent = samples[-6:-1]
            if len(recent) >= 3:
                avg_n = sum(n for _, n in recent) / len(recent)
                if latest_n < avg_n * 0.8:
                    reporter.error(f"最新日期股票数 ({latest_n:,}) 明显低于近 5 日均值 ({avg_n:,.0f})")
                elif latest_n < avg_n * 0.95:
                    reporter.warn(f"最新日期股票数 ({latest_n:,}) 略低于近 5 日均值 ({avg_n:,.0f})")
            else:
                reporter.info("近 5 日数据不足，无法做趋势对比")
    except Exception as e:
        print(f"  检查失败: {e}")
        reporter.error("daily 每日股票数量检查失败")

    if latest_str is None:
        try:
            latest_str = _query_scalar(conn, f"SELECT MAX(trade_date) FROM {pq('daily')}")
        except Exception:
            latest_str = None
    start_date, range_label = _date_range_start(latest_str)

    # ---- 4. 检查 adj_factor / daily_basic / tech_indicator 是否与 daily 日期对齐 ----
    print()
    print("=" * 60)
    print(f"4. 其他表与 daily 日期对齐检查（{range_label}）")
    print("=" * 60)
    for tbl in ["adj_factor", "daily_basic", "tech_indicator"]:
        try:
            missing = conn.execute(f"""
                SELECT d.trade_date
                FROM (SELECT DISTINCT trade_date FROM {pq('daily')}) d
                WHERE d.trade_date >= '{start_date}'
                  AND d.trade_date NOT IN (
                    SELECT DISTINCT trade_date FROM {pq(tbl)}
                  )
                ORDER BY d.trade_date
            """).fetchall()
            if missing:
                dates = [r[0] for r in missing]
                print(f"  {tbl}: 缺失 {len(missing)} 个日期: {dates}")
                reporter.error(f"{tbl} 缺失 daily 中的 {len(missing)} 个日期")
            else:
                print(f"  {tbl}: 与 daily 对齐 ✓")
            extra = conn.execute(f"""
                SELECT t.trade_date
                FROM (SELECT DISTINCT trade_date FROM {pq(tbl)}) t
                WHERE t.trade_date >= '{start_date}'
                  AND t.trade_date NOT IN (
                    SELECT DISTINCT trade_date FROM {pq('daily')}
                  )
                ORDER BY t.trade_date
            """).fetchall()
            if extra:
                extra_dates = [r[0] for r in extra]
                print(f"    ↳ 反向: {tbl} 多出 {len(extra)} 个 daily 没有的日期: {extra_dates}")
                reporter.error(f"{tbl} 多出 daily 中不存在的 {len(extra)} 个日期")
        except Exception as e:
            print(f"  {tbl}: 检查失败: {e}")
            reporter.error(f"{tbl} 日期对齐检查失败")

    # ---- 5. 业务完整可用日期 ----
    print()
    print("=" * 60)
    print("5. 完整可用日期")
    print("=" * 60)
    try:
        usable = _query_scalar(conn, f"""
            WITH d AS (SELECT DISTINCT trade_date FROM {pq('daily')} WHERE trade_date >= '{MIN_CHECK_DATE}'),
                 a AS (SELECT DISTINCT trade_date FROM {pq('adj_factor')} WHERE trade_date >= '{MIN_CHECK_DATE}'),
                 b AS (SELECT DISTINCT trade_date FROM {pq('daily_basic')} WHERE trade_date >= '{MIN_CHECK_DATE}'),
                 t AS (SELECT DISTINCT trade_date FROM {pq('tech_indicator')} WHERE trade_date >= '{MIN_CHECK_DATE}')
            SELECT MAX(d.trade_date)
            FROM d
            JOIN a USING(trade_date)
            JOIN b USING(trade_date)
            JOIN t USING(trade_date)
        """)
        if usable:
            print(f"  完整可用日期: {usable}")
        else:
            reporter.error("无法找到 daily/adj_factor/daily_basic/tech_indicator 共同可用日期")
    except Exception as e:
        print(f"  检查失败: {e}")
        reporter.error("完整可用日期检查失败")

    # ---- 6. 核心字段空值与 OHLC 合法性 ----
    print()
    print("=" * 60)
    print(f"6. 核心字段空值与 OHLC 检查（{MIN_CHECK_DATE} 以后）")
    print("=" * 60)
    try:
        daily_nulls = _query_scalar(conn, f"""
            SELECT COUNT(*)
            FROM {pq('daily')}
            WHERE trade_date >= '{MIN_CHECK_DATE}'
              AND (
                ts_code IS NULL OR trade_date IS NULL OR open IS NULL OR high IS NULL
                OR low IS NULL OR close IS NULL OR vol IS NULL OR amount IS NULL
              )
        """)
        if daily_nulls:
            reporter.error(f"daily 核心字段空值 {daily_nulls:,} 行")
            _print_samples(conn, f"""
                SELECT ts_code, trade_date, open, high, low, close, vol, amount
                FROM {pq('daily')}
                WHERE trade_date >= '{MIN_CHECK_DATE}'
                  AND (
                    ts_code IS NULL OR trade_date IS NULL OR open IS NULL OR high IS NULL
                    OR low IS NULL OR close IS NULL OR vol IS NULL OR amount IS NULL
                  )
                ORDER BY trade_date DESC, ts_code
            """)
        else:
            print("  daily 核心字段无空值 ✓")

        bad_ohlc = _query_scalar(conn, f"""
            SELECT COUNT(*)
            FROM {pq('daily')}
            WHERE trade_date >= '{MIN_CHECK_DATE}'
              AND (
                high < low OR open < low OR open > high OR close < low OR close > high
                OR open <= 0 OR high <= 0 OR low <= 0 OR close <= 0
              )
        """)
        if bad_ohlc:
            reporter.error(f"daily OHLC 异常 {bad_ohlc:,} 行")
            _print_samples(conn, f"""
                SELECT ts_code, trade_date, open, high, low, close
                FROM {pq('daily')}
                WHERE trade_date >= '{MIN_CHECK_DATE}'
                  AND (
                    high < low OR open < low OR open > high OR close < low OR close > high
                    OR open <= 0 OR high <= 0 OR low <= 0 OR close <= 0
                  )
                ORDER BY trade_date DESC, ts_code
            """)
        else:
            print("  daily OHLC 合法 ✓")

        adj_bad = _query_scalar(conn, f"""
            SELECT COUNT(*)
            FROM {pq('adj_factor')}
            WHERE trade_date >= '{MIN_CHECK_DATE}'
              AND (ts_code IS NULL OR trade_date IS NULL OR adj_factor IS NULL OR adj_factor <= 0)
        """)
        if adj_bad:
            reporter.error(f"adj_factor 空值或非正复权因子 {adj_bad:,} 行")
        else:
            print("  adj_factor 复权因子合法 ✓")

        for tbl in ["daily_basic", "tech_indicator"]:
            bad_keys = _query_scalar(conn, f"""
                SELECT COUNT(*)
                FROM {pq(tbl)}
                WHERE trade_date >= '{MIN_CHECK_DATE}'
                  AND (ts_code IS NULL OR trade_date IS NULL)
            """)
            if bad_keys:
                reporter.error(f"{tbl} 主键空值 {bad_keys:,} 行")
            else:
                print(f"  {tbl} 主键无空值 ✓")
    except Exception as e:
        print(f"  检查失败: {e}")
        reporter.error("核心字段质量检查失败")

    # ---- 7. 最近窗口内键级别对齐 ----
    print()
    print("=" * 60)
    print(f"7. 股票-日期键级别对齐检查（{range_label}）")
    print("=" * 60)
    key_checks = [
        ("adj_factor", "ERROR"),
        ("daily_basic", "ERROR"),
        ("tech_indicator", "WARN"),
    ]
    for tbl, level in key_checks:
        try:
            missing = _query_scalar(conn, f"""
                SELECT COUNT(*)
                FROM {pq('daily')} d
                LEFT JOIN {pq(tbl)} t
                  ON d.ts_code = t.ts_code
                 AND d.trade_date = t.trade_date
                WHERE d.trade_date >= '{start_date}'
                  AND t.ts_code IS NULL
            """)
            if missing:
                message = f"daily -> {tbl} 缺失键 {missing:,} 个"
                if level == "ERROR":
                    reporter.error(message)
                else:
                    reporter.warn(message)
                _print_samples(conn, f"""
                    SELECT d.ts_code, d.trade_date
                    FROM {pq('daily')} d
                    LEFT JOIN {pq(tbl)} t
                      ON d.ts_code = t.ts_code
                     AND d.trade_date = t.trade_date
                    WHERE d.trade_date >= '{start_date}'
                      AND t.ts_code IS NULL
                    ORDER BY d.trade_date DESC, d.ts_code
                """)
            else:
                print(f"  daily -> {tbl}: 键级别对齐 ✓")
        except Exception as e:
            print(f"  daily -> {tbl}: 检查失败: {e}")
            reporter.error(f"daily -> {tbl} 键级别对齐检查失败")

    # ---- 8. 技术指标质量 ----
    print()
    print("=" * 60)
    print(f"8. 技术指标质量检查（{range_label}）")
    print("=" * 60)
    try:
        cols = _describe_columns(conn, "tech_indicator")
        for col in ["rsi6", "rsi14", "rsi24"]:
            if col in cols:
                cnt = _query_scalar(conn, f"""
                    SELECT COUNT(*)
                    FROM {pq('tech_indicator')}
                    WHERE trade_date >= '{start_date}'
                      AND ({col} < 0 OR {col} > 100)
                """)
                if cnt:
                    reporter.error(f"{col} 越界 {cnt:,} 行")
        if "atr14" in cols:
            cnt = _query_scalar(conn, f"""
                SELECT COUNT(*)
                FROM {pq('tech_indicator')}
                WHERE trade_date >= '{start_date}'
                  AND atr14 < 0
            """)
            if cnt:
                reporter.error(f"atr14 为负 {cnt:,} 行")
        core = [c for c in ["ma5", "ma10", "ma20", "ma60", "dif", "dea", "macd_hist", "rsi6", "rsi14", "rsi24", "atr14"] if c in cols]
        if core:
            cond = " AND ".join(f"{c} IS NULL" for c in core)
            all_null = _query_scalar(conn, f"""
                SELECT COUNT(*)
                FROM {pq('tech_indicator')}
                WHERE trade_date >= '{start_date}'
                  AND {cond}
            """)
            if all_null:
                reporter.warn(f"tech_indicator 核心指标全空 {all_null:,} 行")
                _print_samples(conn, f"""
                    SELECT ts_code, trade_date
                    FROM {pq('tech_indicator')}
                    WHERE trade_date >= '{start_date}'
                      AND {cond}
                    ORDER BY trade_date DESC, ts_code
                """)
            else:
                print("  tech_indicator 核心指标无全空行 ✓")
    except Exception as e:
        print(f"  检查失败: {e}")
        reporter.error("技术指标质量检查失败")

    # ---- 9. 检查异常涨跌幅（作为 WARN，不直接判失败） ----
    print()
    print("=" * 60)
    print(f"9. 异常涨跌幅检查（{range_label}）")
    print("=" * 60)
    try:
        anomalies = conn.execute(f"""
            SELECT ts_code, trade_date, pct_chg
            FROM {pq('daily')}
            WHERE trade_date >= '{start_date}'
              AND (
                (SUBSTR(ts_code, 1, 2) IN ('60', '00') AND ABS(pct_chg) > 10.5)
                OR
                (SUBSTR(ts_code, 1, 2) IN ('30', '68') AND ABS(pct_chg) > 20.5)
              )
            ORDER BY trade_date DESC
            LIMIT 20
        """).fetchall()
        if anomalies:
            reporter.warn(f"异常涨跌幅样本 {len(anomalies)} 条（可能含新股/复牌/除权）")
            for ts_code, trade_date, pct_chg in anomalies[:10]:
                print(f"    {trade_date} {ts_code} pct_chg={pct_chg}%")
        else:
            print("  无异常涨跌幅 ✓")
    except Exception as e:
        print(f"  检查失败: {e}")
        reporter.warn("异常涨跌幅检查失败")

    # ---- 总结 ----
    print()
    print("=" * 60)
    print("校验总结")
    print("=" * 60)
    print(f"  ERROR: {reporter.errors}")
    print(f"  WARN : {reporter.warnings}")
    if reporter.errors == 0:
        if reporter.warnings == 0:
            print("✅ 数据校验通过，未发现 ERROR/WARN")
        else:
            print("✅ 数据校验通过，但存在 WARN，建议关注")
        return True
    print("❌ 数据校验未通过，存在 ERROR，建议处理")
    return False


if __name__ == "__main__":
    db_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/astock.duckdb")
    conn = duckdb.connect(str(db_path))
    try:
        ok = verify(conn)
        sys.exit(0 if ok else 1)
    finally:
        conn.close()
